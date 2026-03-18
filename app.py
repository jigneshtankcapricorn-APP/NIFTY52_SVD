"""
app.py
──────
Volume Profile App — Main Streamlit Application
Login protected. Nifty 50 + BankNifty Session Volume Profile.
"""

import streamlit as st
import pandas as pd
from datetime import datetime

# ─── Page Config (must be first) ──────────────────────────────────────────────
st.set_page_config(
    page_title = "Volume Profile Dashboard",
    page_icon  = "📊",
    layout     = "wide",
    initial_sidebar_state = "expanded",
)

# ─── Custom CSS ───────────────────────────────────────────────────────────────
st.markdown("""
<style>
    /* Dark background */
    .stApp { background-color: #0e1117; }

    /* Login card */
    .login-card {
        background: #161b27;
        border-radius: 14px;
        padding: 40px 44px 36px 44px;
        max-width: 440px;
        margin: 60px auto 28px auto;
        box-shadow: 0 4px 32px rgba(0,0,0,0.45);
        text-align: center;
    }
    .login-logo { font-size: 52px; margin-bottom: 6px; }
    .login-title {
        font-size: 26px; font-weight: 700;
        color: #e0e6f0; margin-bottom: 4px;
    }
    .login-sub {
        font-size: 13px; color: #7a8499;
        margin-bottom: 28px; line-height: 1.6;
    }
    .login-badge {
        display: inline-block;
        background: #1e2538;
        color: #7a8499;
        font-size: 11px;
        padding: 5px 14px;
        border-radius: 20px;
        margin-top: 18px;
        border: 1px solid #2a3050;
    }

    /* Hide streamlit branding */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}

    /* Signal cards */
    .signal-bull {
        background: #0d2b1d; border-left: 4px solid #00c853;
        padding: 14px 18px; border-radius: 6px; margin-bottom: 10px;
    }
    .signal-bear {
        background: #2b0d0d; border-left: 4px solid #ff1744;
        padding: 14px 18px; border-radius: 6px; margin-bottom: 10px;
    }
    .signal-side {
        background: #1d1d0d; border-left: 4px solid #ffd600;
        padding: 14px 18px; border-radius: 6px; margin-bottom: 10px;
    }
    .level-box {
        background: #161b27; border-radius: 8px;
        padding: 12px 16px; margin-bottom: 8px;
        border: 1px solid #1e2538;
    }
</style>
""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# AUTH
# ══════════════════════════════════════════════════════════════════════════════
def check_login(username: str, password: str) -> bool:
    correct_user = st.secrets.get("APP_USERNAME", "")
    correct_pass = st.secrets.get("APP_PASSWORD", "")
    return username == correct_user and password == correct_pass


def show_login():
    """Render login page."""
    st.markdown("""
    <div class="login-card">
        <div class="login-logo">📊</div>
        <div class="login-title">Volume Profile Dashboard</div>
        <div class="login-sub">
            Nifty 50 · Bank Nifty · Session Volume Profile<br>
            Scalping · Intraday · Key Levels
        </div>
    </div>
    """, unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 1.4, 1])
    with col2:
        username = st.text_input("Username", placeholder="Enter username", label_visibility="visible")
        password = st.text_input("Password", placeholder="Enter password", type="password", label_visibility="visible")

        if st.button("Login →", use_container_width=True, type="primary"):
            if check_login(username, password):
                st.session_state["logged_in"] = True
                st.rerun()
            else:
                st.error("❌ Invalid username or password")

        st.markdown("""
        <div style="text-align:center;">
            <span class="login-badge">🔒 Secured · Volume Profile Dashboard</span>
        </div>
        """, unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# MAIN APP
# ══════════════════════════════════════════════════════════════════════════════
def show_app():
    from fetcher       import fetch_all, login, fetch_candles
    from volume_profile import calculate_all_sessions, get_key_levels
    from plotter        import build_chart, build_signal_card, build_levels_table

    # ─── Sidebar ──────────────────────────────────────────────────────────────
    with st.sidebar:
        st.markdown("## ⚙️ Settings")

        symbol = st.selectbox(
            "Instrument",
            ["NIFTY", "BANKNIFTY"],
            index=0,
        )

        show_candles = st.checkbox("Show Candles", value=True)

        st.markdown("---")
        st.markdown("### 📅 Data")
        days = st.slider("Days of data", min_value=5, max_value=10, value=7)

        refresh = st.button("🔄 Refresh Data", use_container_width=True, type="primary")

        st.markdown("---")
        if st.button("🚪 Logout", use_container_width=True):
            st.session_state["logged_in"] = False
            st.rerun()

        st.markdown("---")
        st.markdown(
            f"<div style='color:#4a5568;font-size:11px;'>Last updated<br>{datetime.now().strftime('%d %b %Y %H:%M')}</div>",
            unsafe_allow_html=True
        )

    # ─── Load Data ────────────────────────────────────────────────────────────
    cache_key = f"data_{symbol}_{days}"

    if cache_key not in st.session_state or refresh:
        with st.spinner(f"📡 Fetching {symbol} data from Angel One..."):
            try:
                obj = login()
                df  = fetch_candles(obj, symbol=symbol, interval="3m", days=days)
                st.session_state[cache_key]         = df
                st.session_state[f"profiles_{symbol}"] = calculate_all_sessions(df, symbol=symbol)
            except Exception as e:
                st.error(f"❌ Data fetch failed: {e}")
                st.stop()

    df       = st.session_state[cache_key]
    profiles = st.session_state.get(f"profiles_{symbol}", [])

    if not profiles:
        profiles = calculate_all_sessions(df, symbol=symbol)
        st.session_state[f"profiles_{symbol}"] = profiles

    levels = get_key_levels(profiles)

    # ─── Header ───────────────────────────────────────────────────────────────
    st.markdown(f"## 📊 {symbol} — Session Volume Profile")

    # ─── Signal + Key Levels ──────────────────────────────────────────────────
    col_sig, col_lvl = st.columns([1, 1.6])

    with col_sig:
        st.markdown("### 🎯 Signal")
        signal_html = build_signal_card(levels, symbol)
        st.markdown(signal_html, unsafe_allow_html=True)

        st.markdown("### 📋 Key Levels for Tomorrow")
        lvl_df = build_levels_table(levels)
        st.dataframe(
            lvl_df,
            use_container_width=True,
            hide_index=True,
        )

    with col_lvl:
        st.markdown("### 📅 Session History")
        history_rows = []
        for p in reversed(profiles):
            history_rows.append({
                "Date":    p.date,
                "POC":     f"{p.poc:.0f}",
                "VAH":     f"{p.vah:.0f}",
                "VAL":     f"{p.val:.0f}",
                "High":    f"{p.day_high:.0f}",
                "Low":     f"{p.day_low:.0f}",
                "Close":   f"{p.day_close:.0f}",
                "Bias":    f"{p.bias_emoji} {p.bias}",
            })
        st.dataframe(
            pd.DataFrame(history_rows),
            use_container_width=True,
            hide_index=True,
        )

    # ─── Chart ────────────────────────────────────────────────────────────────
    st.markdown("### 📈 Chart")
    fig = build_chart(
        df            = df,
        profiles      = profiles,
        symbol        = symbol,
        show_candles  = show_candles,
    )
    st.plotly_chart(fig, use_container_width=True)


# ══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════
if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False

if not st.session_state["logged_in"]:
    show_login()
else:
    show_app()
