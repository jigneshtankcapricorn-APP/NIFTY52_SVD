import pyotp
import pandas as pd
import requests
from datetime import datetime, timedelta
from SmartApi import SmartConnect
import streamlit as st

# ─── Angel One Scrip Master URL ───────────────────────────────────────────────
SCRIP_MASTER_URL = "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json"

# ─── Interval Mapping ─────────────────────────────────────────────────────────
INTERVALS = {
    "3m":  "THREE_MINUTE",
    "15m": "FIFTEEN_MINUTE",
    "30m": "THIRTY_MINUTE",
    "1h":  "ONE_HOUR",
    "1d":  "ONE_DAY",
}


def get_totp(totp_key: str) -> str:
    """Generate current TOTP code from secret key."""
    return pyotp.TOTP(totp_key).now()


def login() -> SmartConnect:
    """
    Login to Angel One SmartAPI using Streamlit secrets.
    Returns authenticated SmartConnect object.
    """
    try:
        api_key   = st.secrets["API_KEY"]
        client_id = st.secrets["CLIENT_ID"]
        password  = st.secrets["PASSWORD"]
        totp_key  = st.secrets["TOTP_KEY"]
    except Exception as e:
        raise ValueError(f"❌ Could not read secrets: {e}")

    totp = get_totp(totp_key)
    obj  = SmartConnect(api_key=api_key)
    data = obj.generateSession(client_id, password, totp)

    if data["status"] == False:
        raise ConnectionError(f"❌ Login failed: {data['message']}")

    print(f"✅ Login successful!")
    return obj


def get_futures_token(symbol: str = "NIFTY") -> dict:
    """
    Auto-detect the nearest expiry futures token from Angel One scrip master.

    Parameters:
        symbol : "NIFTY" or "BANKNIFTY"

    Returns:
        dict with token, trading symbol, expiry date
    """
    print(f"🔍 Fetching scrip master for {symbol} futures token...")

    resp = requests.get(SCRIP_MASTER_URL, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    df = pd.DataFrame(data)

    # For indices like NIFTY, BANKNIFTY → FUTIDX
    fut = df[
        (df["name"] == symbol) &
        (df["instrumenttype"] == "FUTIDX")
    ].copy()

    if fut.empty:
        raise ValueError(f"❌ No futures found for {symbol} in scrip master!")

    # Parse expiry dates
    fut["expiry_dt"] = pd.to_datetime(fut["expiry"], format="%d%b%Y", errors="coerce")

    # Only future or today expiries
    today = pd.Timestamp(datetime.now().date())
    fut   = fut[fut["expiry_dt"] >= today]

    if fut.empty:
        raise ValueError(f"❌ No valid upcoming expiry found for {symbol}!")

    # Pick nearest expiry
    nearest = fut.sort_values("expiry_dt").iloc[0]

    result = {
        "token":    nearest["token"],
        "symbol":   nearest["symbol"],
        "expiry":   nearest["expiry"],
        "exchange": "NFO",
    }

    print(f"✅ Found: {result['symbol']} | Expiry: {result['expiry']} | Token: {result['token']}")
    return result


def fetch_candles(
    obj: SmartConnect,
    symbol: str = "NIFTY",
    interval: str = "3m",
    days: int = 7
) -> pd.DataFrame:
    """
    Fetch historical candle data using futures token.

    Parameters:
        obj      : Authenticated SmartConnect object
        symbol   : "NIFTY" or "BANKNIFTY"
        interval : "3m", "15m", "30m", "1h", "1d"
        days     : Number of calendar days to fetch (default 7)

    Returns:
        pd.DataFrame with columns: datetime, open, high, low, close, volume
    """
    if interval not in INTERVALS:
        raise ValueError(f"❌ Unknown interval. Choose from {list(INTERVALS.keys())}")

    # Auto-detect futures token
    fut_info     = get_futures_token(symbol)
    token        = fut_info["token"]
    exchange     = fut_info["exchange"]
    ang_interval = INTERVALS[interval]

    # Date range
    to_date   = datetime.now()
    from_date = to_date - timedelta(days=days)

    from_str = from_date.strftime("%Y-%m-%d %H:%M")
    to_str   = to_date.strftime("%Y-%m-%d %H:%M")

    print(f"📡 Fetching {symbol} FUT | {interval} | {from_str} → {to_str}")

    params = {
        "exchange":    exchange,
        "symboltoken": token,
        "interval":    ang_interval,
        "fromdate":    from_str,
        "todate":      to_str,
    }

    response = obj.getCandleData(params)

    if response["status"] == False:
        raise RuntimeError(f"❌ Data fetch failed: {response['message']}")

    raw = response["data"]

    if not raw:
        raise RuntimeError("❌ No data returned!")

    # ─── Build DataFrame ──────────────────────────────────────────────────────
    df = pd.DataFrame(raw, columns=["datetime", "open", "high", "low", "close", "volume"])
    df["datetime"] = pd.to_datetime(df["datetime"])
    df.set_index("datetime", inplace=True)

    # Filter market hours: 9:15 AM to 3:30 PM
    df = df.between_time("09:15", "15:30")

    # Remove weekends
    df = df[df.index.dayofweek < 5]

    df = df.sort_index()

    print(f"✅ Got {len(df)} candles | Volume check: {df['volume'].sum():,} total volume")
    print(f"   From: {df.index[0]}  →  To: {df.index[-1]}")

    return df


def fetch_all(days: int = 7) -> dict:
    """
    Fetch 3m futures candles for both Nifty and BankNifty.
    Returns dict with DataFrames.
    """
    obj  = login()
    data = {}

    for symbol in ["NIFTY", "BANKNIFTY"]:
        df = fetch_candles(obj, symbol=symbol, interval="3m", days=days)
        data[symbol] = df

    return data
