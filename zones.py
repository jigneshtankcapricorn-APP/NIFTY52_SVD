"""
zones.py
────────
Supply and Demand Zone Calculator
Based on Daily candles — institutional levels
3 zone types: Supply, Demand, Target
"""

import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from typing import List
from datetime import datetime, timedelta, timezone
from SmartApi import SmartConnect


# ─── Zone Config ──────────────────────────────────────────────────────────────
ZONE_BODY_PCT        = 0.003   # 0.3% candle body minimum
ZONE_LOOKBACK_INDEX  = 45      # 1.5 months for indices (spot)
ZONE_LOOKBACK_STOCK  = 120     # 4 months for stocks
ZONE_EXTEND_DAYS     = 30

# ─── Spot index tokens for zone daily data ────────────────────────────────────
INDEX_SPOT_TOKENS = {
    "NIFTY":     "99926000",
    "BANKNIFTY": "99926009",
}


@dataclass
class Zone:
    """Single Supply or Demand zone."""
    zone_type:  str    # "SUPPLY" / "DEMAND" / "SUPPLY_TARGET" / "DEMAND_TARGET"
    price_high: float  # Top of zone
    price_low:  float  # Bottom of zone
    date:       str    # Date zone was created
    fresh:      bool   # Never touched after creation = True
    strength:   int    # 1=weak, 2=medium, 3=strong

    @property
    def color_fill(self) -> str:
        if self.zone_type in ["SUPPLY", "SUPPLY_TARGET"]:
            return "rgba(239,83,80,0.15)"      # red
        else:
            return "rgba(38,166,154,0.15)"     # green

    @property
    def color_border(self) -> str:
        if self.zone_type in ["SUPPLY", "SUPPLY_TARGET"]:
            return "rgba(239,83,80,0.70)"
        else:
            return "rgba(38,166,154,0.70)"

    @property
    def label(self) -> str:
        if self.zone_type in ["SUPPLY", "SUPPLY_TARGET"]:
            return "SELL ZONE"
        else:
            return "BUY ZONE"

    @property
    def label_color(self) -> str:
        if self.zone_type in ["SUPPLY", "SUPPLY_TARGET"]:
            return "#ef5350"
        return "#26a69a"

    @property
    def mid_price(self) -> float:
        return (self.price_high + self.price_low) / 2


def fetch_daily_candles(
    obj: SmartConnect,
    symbol: str,
) -> pd.DataFrame:
    """
    Fetch daily candles for zone calculation.
    Indices → spot token, 1.5 months
    Stocks  → NSE cash token, 4 months
    """
    from fetcher import get_stock_token, is_index

    IST = timezone(timedelta(hours=5, minutes=30))
    to_date = datetime.now(IST)

    if is_index(symbol):
        # Use spot index token for continuous daily data
        token    = INDEX_SPOT_TOKENS[symbol]
        exchange = "NSE"
        days     = ZONE_LOOKBACK_INDEX
    else:
        # Use NSE cash stock token
        info     = get_stock_token(symbol)
        token    = info["token"]
        exchange = "NSE"
        days     = ZONE_LOOKBACK_STOCK

    from_date = to_date - timedelta(days=days)
    from_str  = from_date.strftime("%Y-%m-%d %H:%M")
    to_str    = to_date.strftime("%Y-%m-%d %H:%M")

    params = {
        "exchange":    exchange,
        "symboltoken": token,
        "interval":    "ONE_DAY",
        "fromdate":    from_str,
        "todate":      to_str,
    }

    print(f"📡 Fetching {symbol} daily candles (spot/cash, {days} days)...")
    response = obj.getCandleData(params)

    if response["status"] == False:
        raise RuntimeError(f"❌ Daily fetch failed: {response['message']}")

    raw = response["data"]
    if not raw:
        raise RuntimeError("❌ No daily data returned!")

    df = pd.DataFrame(raw, columns=["datetime","open","high","low","close","volume"])
    df["datetime"] = pd.to_datetime(df["datetime"])
    df.set_index("datetime", inplace=True)
    df = df[df.index.dayofweek < 5]
    df = df.sort_index()

    print(f"✅ Got {len(df)} daily candles | {df.index[0].date()} → {df.index[-1].date()}")
    return df


# ─── Zone Config ──────────────────────────────────────────────────────────────
ZONE_BODY_PCT = 0.005  # 0.5% body threshold for 30m candles
MAX_ZONES     = 1      # Only nearest 1 sell + 1 buy zone


def calculate_zones_from_3m(df_3m: pd.DataFrame, current_price: float) -> List[Zone]:
    """
    Calculate SELL/BUY zones from existing 3m data resampled to 30m.
    No extra API call needed!
    """
    # ── Resample 3m → 30m ─────────────────────────────────────────────────────
    df = df_3m.copy()
    df.index = pd.to_datetime(df.index, utc=True).tz_convert("Asia/Kolkata")

    df_30m = df.resample("30min").agg({
        "open":   "first",
        "high":   "max",
        "low":    "min",
        "close":  "last",
        "volume": "sum",
    }).dropna()

    # Market hours only
    df_30m = df_30m.between_time("09:15", "15:30")
    df_30m = df_30m[df_30m.index.dayofweek < 5]

    raw_zones = []

    for i in range(1, len(df_30m)):
        candle   = df_30m.iloc[i]
        body     = abs(candle["close"] - candle["open"])
        body_pct = body / candle["close"]

        if body_pct < ZONE_BODY_PCT:
            continue

        is_bearish = candle["close"] < candle["open"]
        is_bullish = candle["close"] > candle["open"]

        # Strength
        strength = 1
        if body_pct > 0.012: strength = 3
        elif body_pct > 0.008: strength = 2

        zone_date = str(df_30m.index[i].date())
        zone_time = df_30m.index[i].strftime("%H:%M")

        # ── SELL ZONE — big bearish 30m candle ───────────────────────────────
        if is_bearish:
            zone_high = round(candle["open"],  2)
            zone_low  = round(candle["close"], 2)

            # Check freshness — did price re-enter after?
            future = df_30m.iloc[i+1:]
            fresh  = not any(future["high"] >= zone_low * 0.999)

            raw_zones.append(Zone(
                zone_type  = "SUPPLY",
                price_high = zone_high,
                price_low  = zone_low,
                date       = f"{zone_date} {zone_time}",
                fresh      = fresh,
                strength   = strength,
            ))

        # ── BUY ZONE — big bullish 30m candle ────────────────────────────────
        if is_bullish:
            zone_high = round(candle["close"], 2)
            zone_low  = round(candle["open"],  2)

            # Check freshness
            future = df_30m.iloc[i+1:]
            fresh  = not any(future["low"] <= zone_high * 1.001)

            raw_zones.append(Zone(
                zone_type  = "DEMAND",
                price_high = zone_high,
                price_low  = zone_low,
                date       = f"{zone_date} {zone_time}",
                fresh      = fresh,
                strength   = strength,
            ))

    # ── Filter: sell above price, buy below price ─────────────────────────────
    sell_zones = [z for z in raw_zones
                  if z.zone_type == "SUPPLY"
                  and z.price_low > current_price * 0.998]
    sell_zones.sort(key=lambda z: z.price_low)
    sell_zones = _remove_overlapping(sell_zones, current_price)[:MAX_ZONES]

    buy_zones = [z for z in raw_zones
                 if z.zone_type == "DEMAND"
                 and z.price_high < current_price * 1.002]
    buy_zones.sort(key=lambda z: z.price_high, reverse=True)
    buy_zones = _remove_overlapping(buy_zones, current_price)[:MAX_ZONES]

    # With only 1 zone each — no target needed
    final = sell_zones + buy_zones
    print(f"✅ 30m Zones: {len(sell_zones)} SELL + {len(buy_zones)} BUY")
    for z in final:
        print(f"   {z.label}: {z.price_low:.0f}-{z.price_high:.0f} | {z.date}")
    return final
    """
    Calculate Supply and Demand zones from daily candles.
    Zone = candle BODY only (open to close) — tight and clean
    """
    raw_zones = []

    for i in range(1, len(df_daily) - 1):
        candle   = df_daily.iloc[i]
        prev     = df_daily.iloc[i-1]
        nxt      = df_daily.iloc[i+1]

        body     = abs(candle["close"] - candle["open"])
        price    = (candle["high"] + candle["low"]) / 2
        body_pct = body / price

        # Must be a significant candle
        if body_pct < ZONE_BODY_PCT:
            continue

        is_bearish = candle["close"] < candle["open"]
        is_bullish = candle["close"] > candle["open"]

        # Strength
        strength = 1
        if body_pct > 0.015: strength = 3
        elif body_pct > 0.010: strength = 2

        zone_date = str(df_daily.index[i].date())

        # ── SUPPLY ZONE — big bearish candle ─────────────────────────────────
        if is_bearish:
            # Zone = body of candle (open at top, close at bottom)
            zone_high = round(candle["open"],  2)
            zone_low  = round(candle["close"], 2)

            # Check freshness
            future_df = df_daily.iloc[i+1:]
            fresh     = not any(future_df["high"] >= zone_low * 0.999)

            # Only include if zone is above current price
            if zone_low > current_price * 0.990:
                raw_zones.append(Zone(
                    zone_type  = "SUPPLY",
                    price_high = zone_high,
                    price_low  = zone_low,
                    date       = zone_date,
                    fresh      = fresh,
                    strength   = strength,
                ))

        # ── DEMAND ZONE — big bullish candle ─────────────────────────────────
        if is_bullish:
            # Zone = body of candle (close at top, open at bottom)
            zone_high = round(candle["close"], 2)
            zone_low  = round(candle["open"],  2)

            # Check freshness
            future_df = df_daily.iloc[i+1:]
            fresh     = not any(future_df["low"] <= zone_high * 1.001)

            # Only include if zone is below current price
            if zone_high < current_price * 1.020:
                raw_zones.append(Zone(
                    zone_type  = "DEMAND",
                    price_high = zone_high,
                    price_low  = zone_low,
                    date       = zone_date,
                    fresh      = fresh,
                    strength   = strength,
                ))

    # ── Filter Supply zones — above current price, nearest 3 ─────────────────
    supply = [z for z in raw_zones
              if z.zone_type == "SUPPLY"
              and z.price_low > current_price]
    supply.sort(key=lambda z: z.price_low)

    # Remove overlapping zones
    supply = _remove_overlapping(supply, current_price)[:3]

    # ── Filter Demand zones — below current price, nearest 3 ─────────────────
    demand = [z for z in raw_zones
              if z.zone_type == "DEMAND"
              and z.price_high < current_price]
    demand.sort(key=lambda z: z.price_high, reverse=True)

    # Remove overlapping zones
    demand = _remove_overlapping(demand, current_price)[:3]

    # ── Mark target zones (furthest ones) ─────────────────────────────────────
    if len(supply) >= 2:
        supply[-1].zone_type = "SUPPLY_TARGET"
    if len(demand) >= 2:
        demand[-1].zone_type = "DEMAND_TARGET"

    final = supply + demand
    print(f"✅ Zones: {len(supply)} supply + {len(demand)} demand")
    for z in final:
        print(f"   {z.zone_type}: {z.price_low:.0f} - {z.price_high:.0f} | Fresh: {z.fresh}")

    return final


def _remove_overlapping(zones: List[Zone], current_price: float) -> List[Zone]:
    """Remove zones that overlap or are too close together."""
    if not zones:
        return []

    MIN_GAP = current_price * 0.003  # 0.3% minimum gap between zones
    result  = [zones[0]]

    for z in zones[1:]:
        last = result[-1]
        # Check if zones overlap or too close
        gap = abs(z.price_low - last.price_high)
        if gap >= MIN_GAP:
            result.append(z)

    return result


def zones_to_dict(zones: List[Zone]) -> list:
    """Convert zones to JSON-serializable list for chart."""
    result = []
    for z in zones:
        result.append({
            "type":        z.zone_type,
            "high":        z.price_high,
            "low":         z.price_low,
            "mid":         z.mid_price,
            "date":        z.date,
            "fresh":       z.fresh,
            "strength":    z.strength,
            "colorFill":   z.color_fill,
            "colorBorder": z.color_border,
            "label":       z.label,
            "labelColor":  z.label_color,
        })
    return result
