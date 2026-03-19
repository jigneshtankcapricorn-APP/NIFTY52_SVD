"""
scanner.py
──────────
Morning Scanner — scans all 47 instruments and scores them for tradability.
Runs at 9:30 AM or on manual refresh.
"""

import pandas as pd
import numpy as np
from datetime import datetime, time
from dataclasses import dataclass, field
from typing import List, Optional
from SmartApi import SmartConnect

from fetcher import fetch_candles, STOCKS, INDICES, login
from volume_profile import calculate_all_sessions, get_key_levels


# ─── Score weights ────────────────────────────────────────────────────────────
SCORE_WEIGHTS = {
    "signal":          2,   # BULLISH or BEARISH (not sideways)
    "poc_position":    2,   # Price clearly above/below Prev POC
    "opening_surge":   2,   # First 30min had surge 3x+
    "level_spacing":   1,   # Prev levels well spaced (room to move)
    "gap_ok":          1,   # Gap not too extreme (< 1.5%)
}
MAX_SCORE = sum(SCORE_WEIGHTS.values())  # 8


@dataclass
class ScanResult:
    """Scan result for one instrument."""
    symbol:        str
    name:          str
    score:         int
    signal:        str       # BULLISH / BEARISH / SIDEWAYS
    bias_emoji:    str
    gap_pct:       float     # Gap % from prev close
    gap_type:      str       # GAP UP / GAP DOWN / FLAT
    price:         float     # Current/last price
    prev_poc:      float
    prev_vah:      float
    prev_val:      float
    prev_high:     float
    prev_low:      float
    weekly_poc:    float
    poc_position:  str       # ABOVE / BELOW / AT
    level_spacing: float     # VAH - VAL range
    opening_surge: bool
    max_surge:     float     # Highest surge multiplier today
    recommendation: str      # TRADE / WATCH / SKIP
    reason:        str       # Plain English explanation
    error:         str = ""


def score_instrument(result: ScanResult) -> int:
    """Calculate score 0-8 for an instrument."""
    score = 0

    # Signal not sideways
    if result.signal in ["BULLISH", "BEARISH"]:
        score += SCORE_WEIGHTS["signal"]

    # Price clearly above/below POC
    if result.poc_position in ["ABOVE", "BELOW"]:
        score += SCORE_WEIGHTS["poc_position"]

    # Opening surge
    if result.opening_surge:
        score += SCORE_WEIGHTS["opening_surge"]

    # Level spacing — good if VAH-VAL > 0.3% of price
    if result.level_spacing > result.price * 0.003:
        score += SCORE_WEIGHTS["level_spacing"]

    # Gap not too extreme
    if abs(result.gap_pct) < 1.5:
        score += SCORE_WEIGHTS["gap_ok"]

    return score


def get_recommendation(score: int, gap_pct: float, signal: str) -> tuple:
    """Get recommendation and reason based on score."""
    if abs(gap_pct) > 2.0:
        return "SKIP", f"Gap too large ({gap_pct:+.1f}%) — unpredictable, wait"

    if signal == "SIDEWAYS":
        return "SKIP", "Sideways market — no clear direction, price stuck near POC"

    if score >= 7:
        direction = "LONG" if signal == "BULLISH" else "SHORT"
        return "TRADE", f"Strong {direction} setup — {score}/8 score, all conditions met"

    if score >= 5:
        direction = "long" if signal == "BULLISH" else "short"
        return "WATCH", f"Possible {direction} — wait for surge confirmation at key level"

    return "SKIP", f"Low confidence ({score}/8) — not enough confirmation"


def scan_instrument(
    obj: SmartConnect,
    symbol: str,
    name: str,
) -> ScanResult:
    """Scan a single instrument and return scored result."""

    try:
        # Fetch 1 week 3m data
        df = fetch_candles(obj, symbol=symbol, interval="3m", days=7)

        if df.empty or len(df) < 20:
            return ScanResult(
                symbol=symbol, name=name, score=0,
                signal="SIDEWAYS", bias_emoji="🟡",
                gap_pct=0, gap_type="FLAT", price=0,
                prev_poc=0, prev_vah=0, prev_val=0,
                prev_high=0, prev_low=0, weekly_poc=0,
                poc_position="AT", level_spacing=0,
                opening_surge=False, max_surge=0,
                recommendation="SKIP", reason="Insufficient data",
                error="No data"
            )

        # Calculate profiles
        profiles = calculate_all_sessions(df, symbol=symbol)
        if len(profiles) < 2:
            raise ValueError("Need at least 2 sessions")

        levels = get_key_levels(profiles)

        # Current price = last close
        price = float(df["close"].iloc[-1])

        # Gap calculation
        df_ist = df.copy()
        df_ist.index = pd.to_datetime(df_ist.index, utc=True).tz_convert("Asia/Kolkata")
        df_ist["date"] = df_ist.index.date
        dates = sorted(df_ist["date"].unique())

        gap_pct  = 0.0
        gap_type = "FLAT"
        if len(dates) >= 2:
            prev_day_close = float(df_ist[df_ist["date"] == dates[-2]]["close"].iloc[-1])
            today_open     = float(df_ist[df_ist["date"] == dates[-1]]["open"].iloc[0])
            gap_pct  = ((today_open - prev_day_close) / prev_day_close) * 100
            gap_type = "GAP UP" if gap_pct > 0.2 else "GAP DOWN" if gap_pct < -0.2 else "FLAT"

        # POC position
        prev_poc = levels["prev_poc"]
        if price > prev_poc * 1.001:
            poc_position = "ABOVE"
        elif price < prev_poc * 0.999:
            poc_position = "BELOW"
        else:
            poc_position = "AT"

        # Level spacing
        level_spacing = levels["prev_vah"] - levels["prev_val"]

        # Opening surge — check first 30 min of today
        today_df = df_ist[df_ist["date"] == dates[-1]]
        opening_df = today_df.between_time("09:15", "09:45")

        opening_surge = False
        max_surge     = 0.0

        if len(today_df) >= 20:
            vol_values  = list(df_ist["volume"])
            today_start = df_ist[df_ist["date"] == dates[-1]].index[0]
            today_idx   = df_ist.index.get_loc(today_start)

            for i, (ts, row) in enumerate(today_df.iterrows()):
                global_i = today_idx + i
                if global_i < 20:
                    continue
                avg = np.mean(vol_values[global_i-20:global_i])
                if avg > 0:
                    mult = row["volume"] / avg
                    if mult > max_surge:
                        max_surge = mult
                    if mult >= 3.0 and ts in opening_df.index:
                        opening_surge = True

        # Build result
        result = ScanResult(
            symbol        = symbol,
            name          = name,
            score         = 0,
            signal        = levels["bias"],
            bias_emoji    = levels["bias_emoji"],
            gap_pct       = round(gap_pct, 2),
            gap_type      = gap_type,
            price         = price,
            prev_poc      = levels["prev_poc"],
            prev_vah      = levels["prev_vah"],
            prev_val      = levels["prev_val"],
            prev_high     = levels["prev_high"],
            prev_low      = levels["prev_low"],
            weekly_poc    = levels["weekly_poc"],
            poc_position  = poc_position,
            level_spacing = round(level_spacing, 2),
            opening_surge = opening_surge,
            max_surge     = round(max_surge, 1),
            recommendation= "SKIP",
            reason        = "",
        )

        # Score it
        result.score = score_instrument(result)
        rec, reason  = get_recommendation(result.score, gap_pct, result.signal)
        result.recommendation = rec
        result.reason         = reason

        return result

    except Exception as e:
        return ScanResult(
            symbol=symbol, name=name, score=0,
            signal="SIDEWAYS", bias_emoji="🟡",
            gap_pct=0, gap_type="FLAT", price=0,
            prev_poc=0, prev_vah=0, prev_val=0,
            prev_high=0, prev_low=0, weekly_poc=0,
            poc_position="AT", level_spacing=0,
            opening_surge=False, max_surge=0,
            recommendation="SKIP", reason="Error fetching data",
            error=str(e)
        )


def run_scanner(progress_callback=None) -> List[ScanResult]:
    """
    Run full morning scan on all 47 instruments.
    Returns sorted list of ScanResult objects.
    """
    obj = login()

    # Build full instrument list
    instruments = []
    for idx in INDICES:
        instruments.append((idx, f"{idx} Index"))
    for sym, name in STOCKS.items():
        instruments.append((sym, name))

    results = []
    total   = len(instruments)

    for i, (symbol, name) in enumerate(instruments):
        if progress_callback:
            progress_callback(i, total, symbol)

        result = scan_instrument(obj, symbol, name)
        results.append(result)

    # Sort: TRADE first, then WATCH, then SKIP
    # Within each group, sort by score descending
    order = {"TRADE": 0, "WATCH": 1, "SKIP": 2}
    results.sort(key=lambda r: (order.get(r.recommendation, 3), -r.score))

    return results


def is_market_hours() -> bool:
    """Check if currently in NSE market hours."""
    now  = datetime.now()
    h, m = now.hour, now.minute
    mins = h * 60 + m
    return 555 <= mins <= 930  # 9:15 to 15:30


def is_scanner_time() -> bool:
    """Best time to run scanner = 9:30 to 10:00 AM."""
    now  = datetime.now()
    h, m = now.hour, now.minute
    mins = h * 60 + m
    return 570 <= mins <= 600  # 9:30 to 10:00
