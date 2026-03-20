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
ZONE_BODY_PCT    = 0.007   # Candle body must be > 0.7% of price to create zone
ZONE_LOOKBACK    = 120     # Days of daily candles to fetch
ZONE_EXTEND_DAYS = 30      # How many days to extend zone to the right


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
        if self.zone_type == "SUPPLY":
            return "rgba(239,83,80,0.20)"      # pink
        elif self.zone_type == "DEMAND":
            return "rgba(38,166,154,0.20)"     # teal
        elif self.zone_type == "SUPPLY_TARGET":
            return "rgba(239,83,80,0.10)"      # light pink
        else:
            return "rgba(38,166,154,0.10)"     # light teal

    @property
    def color_border(self) -> str:
        if self.zone_type == "SUPPLY":
            return "rgba(239,83,80,0.80)"
        elif self.zone_type == "DEMAND":
            return "rgba(38,166,154,0.80)"
        elif self.zone_type == "SUPPLY_TARGET":
            return "rgba(239,83,80,0.40)"
        else:
            return "rgba(38,166,154,0.40)"

    @property
    def label(self) -> str:
        labels = {
            "SUPPLY":         "D  Supply Zone",
            "DEMAND":         "D  Demand Zone",
            "SUPPLY_TARGET":  "D  Supply Target Zone",
            "DEMAND_TARGET":  "D  Demand Target Zone",
        }
        return labels.get(self.zone_type, self.zone_type)

    @property
    def label_color(self) -> str:
        if "SUPPLY" in self.zone_type:
            return "#ef5350"
        return "#26a69a"

    @property
    def mid_price(self) -> float:
        return (self.price_high + self.price_low) / 2


def fetch_daily_candles(
    obj: SmartConnect,
    symbol: str,
    days: int = ZONE_LOOKBACK,
) -> pd.DataFrame:
    """Fetch daily candles for zone calculation."""
    from fetcher import get_futures_token, get_stock_token, is_index, INTERVALS

    IST       = timezone(timedelta(hours=5, minutes=30))
    to_date   = datetime.now(IST)
    from_date = to_date - timedelta(days=days)

    from_str = from_date.strftime("%Y-%m-%d %H:%M")
    to_str   = to_date.strftime("%Y-%m-%d %H:%M")

    if is_index(symbol):
        info     = get_futures_token(symbol)
        token    = info["token"]
        exchange = "NFO"
    else:
        info     = get_stock_token(symbol)
        token    = info["token"]
        exchange = "NSE"

    params = {
        "exchange":    exchange,
        "symboltoken": token,
        "interval":    "ONE_DAY",
        "fromdate":    from_str,
        "todate":      to_str,
    }

    print(f"📡 Fetching {symbol} daily candles for zone calculation...")
    response = obj.getCandleData(params)

    if response["status"] == False:
        raise RuntimeError(f"❌ Daily data fetch failed: {response['message']}")

    raw = response["data"]
    if not raw:
        raise RuntimeError("❌ No daily data returned!")

    df = pd.DataFrame(raw, columns=["datetime","open","high","low","close","volume"])
    df["datetime"] = pd.to_datetime(df["datetime"])
    df.set_index("datetime", inplace=True)
    df = df.sort_index()

    print(f"✅ Got {len(df)} daily candles for zone calculation")
    return df


def calculate_zones(df_daily: pd.DataFrame, current_price: float) -> List[Zone]:
    """
    Calculate Supply and Demand zones from daily candles.

    Rules:
    - Big candle body > 0.7% of price = zone creator
    - Red big candle falling from area = SUPPLY zone
    - Green big candle rising from area = DEMAND zone
    - Zone = body of the base candle (open to close)
    - Target zones = next supply/demand in direction
    - Fresh zones = price hasn't re-entered since creation
    - Show max 3 supply + 3 demand zones
    """
    zones = []

    for i in range(2, len(df_daily) - 1):
        candle  = df_daily.iloc[i]
        prev    = df_daily.iloc[i-1]
        next_c  = df_daily.iloc[i+1]

        body    = abs(candle["close"] - candle["open"])
        price   = candle["close"]
        body_pct = body / price

        if body_pct < ZONE_BODY_PCT:
            continue

        is_bearish = candle["close"] < candle["open"]
        is_bullish = candle["close"] > candle["open"]

        # Strength based on body size
        strength = 1
        if body_pct > 0.015:
            strength = 3
        elif body_pct > 0.010:
            strength = 2

        zone_date = str(df_daily.index[i].date())

        # ── SUPPLY ZONE ───────────────────────────────────────────────────────
        # Big bearish candle = supply zone at top of candle body
        if is_bearish:
            zone_high = max(candle["open"], candle["close"])
            zone_low  = min(candle["open"], candle["close"])

            # Check if price has re-entered zone (not fresh)
            future_prices = df_daily.iloc[i+1:]["high"]
            fresh = not any(p >= zone_low for p in future_prices)

            zones.append(Zone(
                zone_type  = "SUPPLY",
                price_high = round(zone_high, 2),
                price_low  = round(zone_low,  2),
                date       = zone_date,
                fresh      = fresh,
                strength   = strength,
            ))

        # ── DEMAND ZONE ───────────────────────────────────────────────────────
        # Big bullish candle = demand zone at bottom of candle body
        if is_bullish:
            zone_high = max(candle["open"], candle["close"])
            zone_low  = min(candle["open"], candle["close"])

            # Check if fresh
            future_prices = df_daily.iloc[i+1:]["low"]
            fresh = not any(p <= zone_high for p in future_prices)

            zones.append(Zone(
                zone_type  = "DEMAND",
                price_high = round(zone_high, 2),
                price_low  = round(zone_low,  2),
                date       = zone_date,
                fresh      = fresh,
                strength   = strength,
            ))

    # ── Filter relevant zones ─────────────────────────────────────────────────
    # Supply zones ABOVE current price
    supply_zones = [z for z in zones
                    if z.zone_type == "SUPPLY"
                    and z.price_low > current_price * 0.995]
    supply_zones.sort(key=lambda z: z.price_low)  # nearest first
    supply_zones = supply_zones[:3]  # max 3

    # Demand zones BELOW current price
    demand_zones = [z for z in zones
                    if z.zone_type == "DEMAND"
                    and z.price_high < current_price * 1.005]
    demand_zones.sort(key=lambda z: z.price_high, reverse=True)  # nearest first
    demand_zones = demand_zones[:3]  # max 3

    # ── Add Target zones ──────────────────────────────────────────────────────
    # Supply target = highest supply zone (furthest above)
    if len(supply_zones) > 1:
        target_supply         = supply_zones[-1]  # furthest supply
        target_supply.zone_type = "SUPPLY_TARGET"

    # Demand target = lowest demand zone (furthest below)
    if len(demand_zones) > 1:
        target_demand         = demand_zones[-1]  # furthest demand
        target_demand.zone_type = "DEMAND_TARGET"

    final_zones = supply_zones + demand_zones
    print(f"✅ Found {len(supply_zones)} supply + {len(demand_zones)} demand zones")
    return final_zones


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
