"""
volume_profile.py
─────────────────
Core Volume Profile calculation engine.
Calculates POC, VAH, VAL, Value Area, Up/Down volume splits per session.
"""

import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from typing import List, Dict


# ─── Config ───────────────────────────────────────────────────────────────────
BIN_SIZE = {
    "NIFTY":      10,   # 10 points per bin
    "BANKNIFTY":  20,   # 20 points per bin
    # Stocks — auto calculated based on price range if not listed
}
DEFAULT_STOCK_BIN_RATIO = 0.001  # 0.1% of price = bin size
VALUE_AREA_PCT = 0.70


# ─── Data Structures ──────────────────────────────────────────────────────────
@dataclass
class VolumeProfileBar:
    """Single horizontal bar in the volume profile histogram."""
    price_low:   float
    price_high:  float
    price_mid:   float
    total_vol:   float
    up_vol:      float
    down_vol:    float
    in_value_area: bool = False
    is_poc:        bool = False


@dataclass
class SessionProfile:
    """Complete volume profile for one trading session."""
    date:        str
    symbol:      str
    poc:         float          # Point of Control
    vah:         float          # Value Area High
    val:         float          # Value Area Low
    total_vol:   float
    day_high:    float
    day_low:     float
    day_open:    float
    day_close:   float
    bars:        List[VolumeProfileBar] = field(default_factory=list)

    @property
    def bias(self) -> str:
        """
        Simple Bull/Bear/Sideways bias based on close vs POC and VA.
        """
        close = self.day_close
        va_range = self.vah - self.val

        if close > self.vah:
            return "BULLISH"
        elif close < self.val:
            return "BEARISH"
        elif close > self.poc + (va_range * 0.1):
            return "BULLISH"
        elif close < self.poc - (va_range * 0.1):
            return "BEARISH"
        else:
            return "SIDEWAYS"

    @property
    def bias_emoji(self) -> str:
        mapping = {"BULLISH": "🟢", "BEARISH": "🔴", "SIDEWAYS": "🟡"}
        return mapping.get(self.bias, "🟡")

    @property
    def bias_detail(self) -> str:
        """Plain language explanation of bias."""
        close = self.day_close
        if self.bias == "BULLISH":
            if close > self.vah:
                return f"Price closed ABOVE VAH ({self.vah:.1f}) — strong bullish breakout. Watch for continuation above VAH."
            else:
                return f"Price closed above POC ({self.poc:.1f}) — bullish bias. VAH ({self.vah:.1f}) is next target."
        elif self.bias == "BEARISH":
            if close < self.val:
                return f"Price closed BELOW VAL ({self.val:.1f}) — strong bearish breakdown. Watch for continuation below VAL."
            else:
                return f"Price closed below POC ({self.poc:.1f}) — bearish bias. VAL ({self.val:.1f}) is next target."
        else:
            return f"Price closed near POC ({self.poc:.1f}) — market in balance. Wait for breakout above VAH ({self.vah:.1f}) or below VAL ({self.val:.1f})."


# ─── Core Calculator ──────────────────────────────────────────────────────────
def calculate_session_profile(
    df_session: pd.DataFrame,
    symbol: str = "NIFTY",
    date_str: str = "",
    value_area_pct: float = VALUE_AREA_PCT,
) -> SessionProfile:
    """
    Calculate volume profile for a single trading session.

    Parameters:
        df_session      : DataFrame with OHLCV for one day (3m candles)
        symbol          : "NIFTY" or "BANKNIFTY"
        date_str        : Date label string
        value_area_pct  : Value area percentage (default 0.70)

    Returns:
        SessionProfile object with all levels and bars
    """
    # Auto bin size — fixed for indices, dynamic for stocks
    if symbol in BIN_SIZE:
        bin_size = BIN_SIZE[symbol]
    else:
        # For stocks: 0.1% of average price gives clean bins
        avg_price = (df_session["high"].max() + df_session["low"].min()) / 2
        raw_bin   = avg_price * DEFAULT_STOCK_BIN_RATIO
        # Round to nearest clean number: 0.5, 1, 2, 5, 10, 25, 50 etc
        for clean in [0.5, 1, 2, 5, 10, 25, 50, 100]:
            if raw_bin <= clean:
                bin_size = clean
                break
        else:
            bin_size = 100

    if df_session.empty:
        raise ValueError(f"Empty session data for {date_str}")

    day_low   = df_session["low"].min()
    day_high  = df_session["high"].max()
    day_open  = df_session["open"].iloc[0]
    day_close = df_session["close"].iloc[-1]

    # ─── Create price bins ────────────────────────────────────────────────────
    bin_low  = np.floor(day_low / bin_size) * bin_size
    bin_high = np.ceil(day_high / bin_size) * bin_size
    bins     = np.arange(bin_low, bin_high + bin_size, bin_size)

    # ─── Distribute volume into bins ──────────────────────────────────────────
    vol_bins    = np.zeros(len(bins) - 1)
    up_vol_bins = np.zeros(len(bins) - 1)
    dn_vol_bins = np.zeros(len(bins) - 1)

    for _, candle in df_session.iterrows():
        c_low   = candle["low"]
        c_high  = candle["high"]
        c_vol   = candle["volume"]
        is_up   = candle["close"] >= candle["open"]

        # Find which bins this candle spans
        c_bin_low  = int(np.floor(c_low  / bin_size) * bin_size)
        c_bin_high = int(np.ceil(c_high  / bin_size) * bin_size)

        candle_range = c_high - c_low
        if candle_range <= 0:
            candle_range = bin_size  # avoid divide by zero

        for i in range(len(bins) - 1):
            b_low  = bins[i]
            b_high = bins[i + 1]

            # Overlap between candle range and this bin
            overlap = min(c_high, b_high) - max(c_low, b_low)
            if overlap <= 0:
                continue

            # Volume proportional to overlap
            vol_share = (overlap / candle_range) * c_vol
            vol_bins[i] += vol_share

            if is_up:
                up_vol_bins[i] += vol_share
            else:
                dn_vol_bins[i] += vol_share

    # ─── Find POC ─────────────────────────────────────────────────────────────
    poc_idx   = int(np.argmax(vol_bins))
    poc_price = bins[poc_idx] + bin_size / 2  # midpoint of POC bin

    # ─── Calculate Value Area (70%) ───────────────────────────────────────────
    total_vol    = vol_bins.sum()
    target_vol   = total_vol * value_area_pct

    va_indices   = [poc_idx]
    accumulated  = vol_bins[poc_idx]

    # Expand outward from POC until we reach 70%
    lo = poc_idx - 1
    hi = poc_idx + 1
    n  = len(vol_bins)

    while accumulated < target_vol:
        vol_lo = vol_bins[lo] if lo >= 0 else -1
        vol_hi = vol_bins[hi] if hi < n  else -1

        if vol_lo < 0 and vol_hi < 0:
            break

        if vol_hi >= vol_lo:
            accumulated += vol_hi
            va_indices.append(hi)
            hi += 1
        else:
            accumulated += vol_lo
            va_indices.append(lo)
            lo -= 1

    va_indices.sort()
    vah_idx = max(va_indices)
    val_idx = min(va_indices)

    vah = bins[vah_idx + 1]  # top of highest VA bin
    val = bins[val_idx]       # bottom of lowest VA bin

    # ─── Build profile bars ───────────────────────────────────────────────────
    bars = []
    for i in range(len(bins) - 1):
        if vol_bins[i] <= 0:
            continue
        bar = VolumeProfileBar(
            price_low    = bins[i],
            price_high   = bins[i + 1],
            price_mid    = bins[i] + bin_size / 2,
            total_vol    = vol_bins[i],
            up_vol       = up_vol_bins[i],
            down_vol     = dn_vol_bins[i],
            in_value_area= i in va_indices,
            is_poc        = i == poc_idx,
        )
        bars.append(bar)

    return SessionProfile(
        date      = date_str,
        symbol    = symbol,
        poc       = poc_price,
        vah       = vah,
        val       = val,
        total_vol = total_vol,
        day_high  = day_high,
        day_low   = day_low,
        day_open  = day_open,
        day_close = day_close,
        bars      = bars,
    )


def calculate_all_sessions(
    df: pd.DataFrame,
    symbol: str = "NIFTY",
) -> List[SessionProfile]:
    """
    Calculate volume profiles for all sessions in the DataFrame.

    Parameters:
        df     : Full DataFrame with OHLCV (multiple days, 3m candles)
        symbol : "NIFTY" or "BANKNIFTY"

    Returns:
        List of SessionProfile objects, one per trading day
    """
    profiles = []

    # Group by date
    df_copy = df.copy()
    df_copy.index = pd.to_datetime(df_copy.index, utc=True).tz_convert("Asia/Kolkata")
    df_copy["date"] = df_copy.index.date

    for date, group in df_copy.groupby("date"):
        try:
            profile = calculate_session_profile(
                df_session = group,
                symbol     = symbol,
                date_str   = str(date),
            )
            profiles.append(profile)
            print(f"✅ {date} | POC: {profile.poc:.1f} | VAH: {profile.vah:.1f} | VAL: {profile.val:.1f} | {profile.bias_emoji} {profile.bias}")
        except Exception as e:
            print(f"⚠️  Skipping {date}: {e}")

    return profiles


def get_weekly_poc(profiles: List[SessionProfile]) -> float:
    """
    Calculate weekly POC = price level with highest total volume across all sessions.
    """
    if not profiles:
        return 0.0

    # Collect all bars across all sessions
    all_bins: Dict[float, float] = {}

    for p in profiles:
        for bar in p.bars:
            key = bar.price_mid
            all_bins[key] = all_bins.get(key, 0) + bar.total_vol

    weekly_poc = max(all_bins, key=all_bins.get)
    return weekly_poc


def get_key_levels(profiles: List[SessionProfile]) -> dict:
    """
    Extract all key levels for next day trading from the latest session.

    Returns dict with all important price levels.
    """
    if not profiles:
        return {}

    latest  = profiles[-1]
    weekly_poc = get_weekly_poc(profiles)

    return {
        "prev_poc":      latest.poc,
        "prev_vah":      latest.vah,
        "prev_val":      latest.val,
        "prev_high":     latest.day_high,
        "prev_low":      latest.day_low,
        "prev_close":    latest.day_close,
        "weekly_poc":    weekly_poc,
        "bias":          latest.bias,
        "bias_emoji":    latest.bias_emoji,
        "bias_detail":   latest.bias_detail,
    }
