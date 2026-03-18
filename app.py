"""
app.py
──────
Volume Profile App — Main Streamlit Application
Login protected. Nifty 50 + BankNifty Session Volume Profile.
"""

import streamlit as st
import pandas as pd
from datetime import datetime

# ─── Page Config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title = "Volume Profile Dashboard",
    page_icon  = "📊",
    layout     = "wide",
    initial_sidebar_state = "collapsed",
)

# ─── Custom CSS ───────────────────────────────────────────────────────────────
st.markdown("""
<style>
    .stApp { background-color: #f0f3fa; }
    .block-container { padding-top: 1rem; padding-bottom: 1rem; }

    /* Login card */
    .login-card {
        background: #1a2035;
        border-radius: 14px;
        padding: 40px 44px 36px 44px;
        max-width: 440px;
        margin: 60px auto 28px auto;
        box-shadow: 0 4px 32px rgba(0,0,0,0.45);
        text-align: center;
    }
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
        background: #1e2538; color: #7a8499;
        font-size: 11px; padding: 5px 14px;
        border-radius: 20px; margin-top: 18px;
        border: 1px solid #2a3050;
    }

    /* Top controls bar */
    .controls-bar {
        background: #1a2035;
        border-radius: 10px;
        padding: 10px 20px;
        margin-bottom: 12px;
        display: flex;
        align-items: center;
        gap: 20px;
    }

    /* Signal cards */
    .sig-bull { background:#e8f5e9; border-left:4px solid #00c853; padding:10px 16px; border-radius:6px; }
    .sig-bear { background:#fce4e4; border-left:4px solid #f44336; padding:10px 16px; border-radius:6px; }
    .sig-side { background:#fff8e1; border-left:4px solid #ffc107; padding:10px 16px; border-radius:6px; }

    /* Section headers */
    .sec-title {
        font-size: 13px; font-weight: 600;
        color: #4a5568; text-transform: uppercase;
        letter-spacing: 0.5px; margin-bottom: 6px;
    }

    /* Hide streamlit default elements */
    #MainMenu {visibility:hidden;}
    footer {visibility:hidden;}
    header {visibility:hidden;}
    [data-testid="collapsedControl"] {display:none;}
</style>
""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# AUTH
# ══════════════════════════════════════════════════════════════════════════════
def check_login(username: str, password: str) -> bool:
    return (username == st.secrets.get("APP_USERNAME", "") and
            password == st.secrets.get("APP_PASSWORD", ""))


def show_login():
    st.markdown("""
    <div class="login-card">
        <div style="font-size:52px;">📊</div>
        <div class="login-title">Volume Profile Dashboard</div>
        <div class="login-sub">
            Nifty 50 · Bank Nifty · Session Volume Profile<br>
            Scalping · Intraday · Key Levels
        </div>
    </div>
    """, unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 1.4, 1])
    with col2:
        username = st.text_input("Username", placeholder="Enter username")
        password = st.text_input("Password", placeholder="Enter password", type="password")
        if st.button("Login →", use_container_width=True, type="primary"):
            if check_login(username, password):
                st.session_state["logged_in"] = True
                st.rerun()
            else:
                st.error("❌ Invalid username or password")
        st.markdown('<div style="text-align:center"><span class="login-badge">🔒 Secured · Volume Profile Dashboard</span></div>', unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# MAIN APP
# ══════════════════════════════════════════════════════════════════════════════
def show_app():
    from fetcher        import login, fetch_candles
    from volume_profile import calculate_all_sessions, get_key_levels
    from plotter        import build_chart, build_levels_table

    # ─── Top Controls Bar ─────────────────────────────────────────────────────
    c1, c2, c3, c4, c5, c6, c7 = st.columns([1, 1, 1.2, 0.8, 0.8, 1.2, 0.7])

    with c1:
        symbol = st.selectbox("Instrument", ["NIFTY", "BANKNIFTY"], label_visibility="collapsed")
    with c2:
        timeframe = st.selectbox("Timeframe", ["3m", "30m"], label_visibility="collapsed")
    with c3:
        # Month dropdown — load available expiries
        from fetcher import get_available_expiries
        expiries     = get_available_expiries(symbol)
        expiry_labels = [e["label"] for e in expiries]
        expiry_label  = st.selectbox("Expiry Month", expiry_labels, index=0, label_visibility="collapsed")
    with c4:
        show_candles = st.checkbox("Candles", value=True)
    with c5:
        show_prev = st.checkbox("Prev Levels", value=True)
    with c6:
        refresh = st.button("🔄 Refresh Data", use_container_width=True, type="primary")
    with c7:
        if st.button("🚪 Logout", use_container_width=True):
            st.session_state["logged_in"] = False
            st.rerun()

    st.divider()

    # ─── Load Data ────────────────────────────────────────────────────────────
    cache_key = f"data_{symbol}_{timeframe}_{expiry_label}"

    if cache_key not in st.session_state or refresh:
        with st.spinner(f"📡 Fetching {symbol} {expiry_label} {timeframe} data..."):
            try:
                obj = login()
                df  = fetch_candles(obj, symbol=symbol, interval=timeframe, days=7, expiry_label=expiry_label)
                st.session_state[cache_key] = df
                st.session_state[f"profiles_{cache_key}"] = calculate_all_sessions(df, symbol=symbol)
            except Exception as e:
                st.error(f"❌ {e}")
                st.stop()

    df       = st.session_state[cache_key]
    prof_key = f"profiles_{cache_key}"
    if prof_key not in st.session_state:
        st.session_state[prof_key] = calculate_all_sessions(df, symbol=symbol)

    profiles = st.session_state[prof_key]
    levels   = get_key_levels(profiles)

    # ─── CHART FIRST ──────────────────────────────────────────────────────────
    fig = build_chart(
        df           = df,
        profiles     = profiles,
        symbol       = symbol,
        show_candles = show_candles,
        show_prev_levels = show_prev,
    )
    st.plotly_chart(fig, use_container_width=True)

    st.divider()

    # ─── Details Below Chart ──────────────────────────────────────────────────
    col_sig, col_lvl, col_hist = st.columns([1, 1, 1.4])

    with col_sig:
        st.markdown('<div class="sec-title">🎯 Signal</div>', unsafe_allow_html=True)
        bias  = levels.get("bias", "SIDEWAYS")
        emoji = levels.get("bias_emoji", "🟡")
        detail= levels.get("bias_detail", "")
        css   = {"BULLISH":"sig-bull","BEARISH":"sig-bear","SIDEWAYS":"sig-side"}.get(bias,"sig-side")
        st.markdown(f'<div class="{css}"><b>{emoji} {bias} — {symbol}</b><br><small>{detail}</small></div>', unsafe_allow_html=True)

    with col_lvl:
        st.markdown('<div class="sec-title">📋 Key Levels for Tomorrow</div>', unsafe_allow_html=True)
        lvl_df = build_levels_table(levels)
        st.dataframe(lvl_df, use_container_width=True, hide_index=True, height=245)

    with col_hist:
        st.markdown('<div class="sec-title">📅 Session History</div>', unsafe_allow_html=True)
        rows = []
        for p in reversed(profiles):
            rows.append({
                "Date":  p.date,
                "POC":   f"{p.poc:.0f}",
                "VAH":   f"{p.vah:.0f}",
                "VAL":   f"{p.val:.0f}",
                "High":  f"{p.day_high:.0f}",
                "Low":   f"{p.day_low:.0f}",
                "Close": f"{p.day_close:.0f}",
                "Bias":  f"{p.bias_emoji} {p.bias}",
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True, height=245)

    st.caption(f"Last updated: {datetime.now().strftime('%d %b %Y %H:%M')} IST")


# ══════════════════════════════════════════════════════════════════════════════
# ENTRY
# ══════════════════════════════════════════════════════════════════════════════
if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False

if not st.session_state["logged_in"]:
    show_login()
else:
    show_app()

