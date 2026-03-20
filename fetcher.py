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

# ─── Indices (futures) ────────────────────────────────────────────────────────
INDICES = ["NIFTY", "BANKNIFTY"]

# ─── Top 45 NSE Stocks by Market Cap ─────────────────────────────────────────
STOCKS = {
    "RELIANCE":    "Reliance Industries",
    "HDFCBANK":    "HDFC Bank",
    "BHARTIARTL":  "Bharti Airtel",
    "SBIN":        "SBI",
    "ICICIBANK":   "ICICI Bank",
    "TCS":         "TCS",
    "BAJFINANCE":  "Bajaj Finance",
    "INFY":        "Infosys",
    "HINDUNILVR":  "HUL",
    "LICI":        "Life Insurance",
    "LT":          "L&T",
    "SUNPHARMA":   "Sun Pharma",
    "MARUTI":      "Maruti Suzuki",
    "M&M":         "M&M",
    "AXISBANK":    "Axis Bank",
    "ITC":         "ITC",
    "KOTAKBANK":   "Kotak Mah. Bank",
    "NTPC":        "NTPC",
    "TITAN":       "Titan Company",
    "HCLTECH":     "HCL Technologies",
    "ONGC":        "ONGC",
    "ULTRACEMCO":  "UltraTech Cem.",
    "BEL":         "Bharat Electron",
    "ADANIPORTS":  "Adani Ports",
    "ADANIPOWER":  "Adani Power",
    "COALINDIA":   "Coal India",
    "JSWSTEEL":    "JSW Steel",
    "POWERGRID":   "Power Grid Corp",
    "BAJAJFINSV":  "Bajaj Finserv",
    "VEDL":        "Vedanta",
    "HAL":         "Hind. Aeronautics",
    "BAJAJ-AUTO":  "Bajaj Auto",
    "AVENUESUPRA": "Avenue Super.",
    "TATASTEEL":   "Tata Steel",
    "NESTLEIND":   "Nestle India",
    "ADANIENT":    "Adani Enterp.",
    "ETERNAL":     "Eternal",
    "HINDZINC":    "Hindustan Zinc",
    "ASIANPAINT":  "Asian Paints",
    "HINDALCO":    "Hindalco Inds.",
    "IOC":         "IOCL",
    "WIPRO":       "Wipro",
    "SBILIFE":     "SBI Life Insuran",
    "EICHERMOT":   "Eicher Motors",
    "SHRIRAMFIN":  "Shriram Finance",
}

# ─── Cache for scrip master (load once per session) ───────────────────────────
_SCRIP_MASTER_CACHE = None

def get_scrip_master() -> pd.DataFrame:
    """Load scrip master once and cache it."""
    global _SCRIP_MASTER_CACHE
    if _SCRIP_MASTER_CACHE is None:
        print("📥 Loading scrip master...")
        resp = requests.get(SCRIP_MASTER_URL, timeout=15)
        resp.raise_for_status()
        _SCRIP_MASTER_CACHE = pd.DataFrame(resp.json())
        print(f"✅ Scrip master loaded: {len(_SCRIP_MASTER_CACHE)} instruments")
    return _SCRIP_MASTER_CACHE


def get_totp(totp_key: str) -> str:
    """Generate current TOTP code from secret key."""
    return pyotp.TOTP(totp_key).now()


def login() -> SmartConnect:
    """
    Login to Angel One SmartAPI using Streamlit secrets.
    Retries once if session fails.
    Returns authenticated SmartConnect object.
    """
    try:
        api_key   = st.secrets["API_KEY"]
        client_id = st.secrets["CLIENT_ID"]
        password  = st.secrets["PASSWORD"]
        totp_key  = st.secrets["TOTP_KEY"]
    except Exception as e:
        raise ValueError(f"❌ Could not read secrets: {e}")

    import time
    for attempt in range(3):  # retry up to 3 times
        try:
            totp = get_totp(totp_key)
            obj  = SmartConnect(api_key=api_key)
            data = obj.generateSession(client_id, password, totp)

            if data["status"] == False:
                raise ConnectionError(f"❌ Login failed: {data['message']}")

            print(f"✅ Login successful!")
            return obj
        except Exception as e:
            if attempt < 2:
                print(f"⚠️ Login attempt {attempt+1} failed: {e} — retrying in 2s...")
                time.sleep(2)
            else:
                raise ConnectionError(f"❌ Login failed after 3 attempts: {e}")


def get_available_expiries(symbol: str = "NIFTY") -> list:
    """
    Get all available future expiries for a symbol.
    Returns list of dicts: [{label, token, symbol, expiry, expiry_dt}]
    """
    resp = requests.get(SCRIP_MASTER_URL, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    df   = pd.DataFrame(data)

    fut = df[
        (df["name"] == symbol) &
        (df["instrumenttype"] == "FUTIDX")
    ].copy()

    if fut.empty:
        return []

    fut["expiry_dt"] = pd.to_datetime(fut["expiry"], format="%d%b%Y", errors="coerce")
    today = pd.Timestamp(datetime.now().date())
    fut   = fut[fut["expiry_dt"] >= today].sort_values("expiry_dt")

    results = []
    for _, row in fut.iterrows():
        label = row["expiry_dt"].strftime("%b %Y").upper()
        results.append({
            "label":     label,
            "token":     row["token"],
            "symbol":    row["symbol"],
            "expiry":    row["expiry"],
            "expiry_dt": row["expiry_dt"],
        })

    return results


def get_futures_token(symbol: str = "NIFTY", expiry_label: str = None) -> dict:
    """
    Get futures token for a symbol. Optionally specify expiry month label like 'MAR 2026'.
    If no label given, picks nearest expiry automatically.

    Parameters:
        symbol       : "NIFTY" or "BANKNIFTY"
        expiry_label : e.g. "MAR 2026", "APR 2026" — if None picks nearest

    Returns:
        dict with token, trading symbol, expiry date
    """
    print(f"🔍 Fetching scrip master for {symbol} futures token...")

    expiries = get_available_expiries(symbol)

    if not expiries:
        raise ValueError(f"❌ No futures found for {symbol}!")

    if expiry_label:
        # Find matching expiry
        matched = [e for e in expiries if e["label"] == expiry_label]
        if not matched:
            raise ValueError(f"❌ Expiry '{expiry_label}' not found! Available: {[e['label'] for e in expiries]}")
        nearest = matched[0]
    else:
        # Auto pick nearest
        nearest = expiries[0]

    result = {
        "token":    nearest["token"],
        "symbol":   nearest["symbol"],
        "expiry":   nearest["expiry"],
        "exchange": "NFO",
        "label":    nearest["label"],
    }

    print(f"✅ Found: {result['symbol']} | Expiry: {result['expiry']} | Token: {result['token']}")
    return result


def get_stock_token(symbol: str) -> dict:
    """
    Get NSE cash token for a stock from scrip master.
    Parameters:
        symbol : e.g. "RELIANCE", "TCS", "HDFCBANK"
    Returns:
        dict with token, symbol, exchange
    """
    print(f"🔍 Looking up NSE cash token for {symbol}...")
    df = get_scrip_master()

    # Try exact name match in NSE cash segment
    match = df[
        (df["name"] == symbol) &
        (df["exch_seg"] == "NSE") &
        (df["instrumenttype"] == "")
    ]

    if match.empty:
        # Try symbol match
        match = df[
            (df["symbol"] == f"{symbol}-EQ") &
            (df["exch_seg"] == "NSE")
        ]

    if match.empty:
        raise ValueError(f"❌ Token not found for {symbol}! Check symbol name.")

    row = match.iloc[0]
    print(f"✅ Found: {row['symbol']} | Token: {row['token']}")
    return {
        "token":    str(row["token"]),
        "symbol":   row["symbol"],
        "exchange": "NSE",
    }


def is_index(symbol: str) -> bool:
    """Check if symbol is an index or a stock."""
    return symbol in INDICES


def fetch_candles(
    obj: SmartConnect,
    symbol: str = "NIFTY",
    interval: str = "3m",
    days: int = 7,
    expiry_label: str = None,
) -> pd.DataFrame:
    """
    Fetch historical candle data.
    Automatically handles both indices (futures) and stocks (NSE cash).

    Parameters:
        obj          : Authenticated SmartConnect object
        symbol       : Index: "NIFTY"/"BANKNIFTY" | Stock: "RELIANCE"/"TCS" etc
        interval     : "3m", "15m", "30m", "1h", "1d"
        days         : Number of calendar days (default 7)
        expiry_label : For indices only e.g. "MAR 2026" — None = auto nearest
    """
    if interval not in INTERVALS:
        raise ValueError(f"❌ Unknown interval. Choose from {list(INTERVALS.keys())}")

    ang_interval = INTERVALS[interval]

    # ── Get token based on type ───────────────────────────────────────────────
    if is_index(symbol):
        # Index → use futures token
        fut_info = get_futures_token(symbol, expiry_label=expiry_label)
        token    = fut_info["token"]
        exchange = fut_info["exchange"]
        label    = f"{symbol} FUT"
    else:
        # Stock → use NSE cash token
        stk_info = get_stock_token(symbol)
        token    = stk_info["token"]
        exchange = stk_info["exchange"]
        label    = f"{symbol} ({STOCKS.get(symbol, symbol)})"

    # ── Date range ────────────────────────────────────────────────────────────
    to_date   = datetime.now()
    from_date = to_date - timedelta(days=days)
    from_str  = from_date.strftime("%Y-%m-%d %H:%M")
    to_str    = to_date.strftime("%Y-%m-%d %H:%M")

    print(f"📡 Fetching {label} | {interval} | {from_str} → {to_str}")

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

    # ── Build DataFrame ───────────────────────────────────────────────────────
    df = pd.DataFrame(raw, columns=["datetime","open","high","low","close","volume"])
    df["datetime"] = pd.to_datetime(df["datetime"])
    df.set_index("datetime", inplace=True)
    df = df.between_time("09:15", "15:30")
    df = df[df.index.dayofweek < 5]
    df = df.sort_index()

    print(f"✅ Got {len(df)} candles | Volume: {df['volume'].sum():,}")
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
