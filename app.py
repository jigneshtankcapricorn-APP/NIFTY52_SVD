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

    /* Scanner cards */
    .scan-card { transition: all 0.2s; }
    .scan-card:hover { transform: translateY(-2px); }
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
        if st.button("Login →", width="stretch", type="primary"):
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
    from fetcher        import login, fetch_candles, get_available_expiries, INDICES, STOCKS, is_index
    from volume_profile import calculate_all_sessions, get_key_levels
    from plotter        import build_levels_table
    from chart_renderer import render_chart_html
    import streamlit.components.v1 as components

    # ─── Build instrument dropdown ─────────────────────────────────────────────
    instrument_options = {}
    for idx in INDICES:
        instrument_options[f"📊 {idx}"] = idx
    for sym, name in STOCKS.items():
        instrument_options[f"🏢 {name} ({sym})"] = sym

    # ─── Top Controls Bar ─────────────────────────────────────────────────────
    c1, c2, c3, c4, c5, c6, c7 = st.columns([2, 1, 1.2, 0.8, 0.8, 1.2, 0.7])

    with c1:
        selected_label = st.selectbox("Instrument", list(instrument_options.keys()), index=0, label_visibility="collapsed")
        symbol = instrument_options[selected_label]
    with c2:
        timeframe = st.selectbox("Timeframe", ["3m", "30m"], label_visibility="collapsed")
    with c3:
        if is_index(symbol):
            expiries      = get_available_expiries(symbol)
            expiry_labels = [e["label"] for e in expiries]
            expiry_label  = st.selectbox("Expiry Month", expiry_labels, index=0, label_visibility="collapsed")
        else:
            st.markdown("<div style='padding:8px 0;color:#4a5568;font-size:12px;'>NSE Cash</div>", unsafe_allow_html=True)
            expiry_label = None
    with c4:
        show_candles = st.checkbox("Candles", value=True)
    with c5:
        show_prev = st.checkbox("Prev Levels", value=True)
    with c6:
        refresh = st.button("🔄 Refresh Data", width="stretch", type="primary")
    with c7:
        if st.button("🚪 Logout", width="stretch"):
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

    # ─── CHART — Lightweight Charts ───────────────────────────────────────────
    from chart_renderer import render_chart_html
    import streamlit.components.v1 as components

    chart_html = render_chart_html(df, profiles, symbol=symbol)
    components.html(chart_html, height=720, scrolling=False)

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
        st.dataframe(lvl_df, width="stretch", hide_index=True, height=245)

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
        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True, height=245)

    st.caption(f"Last updated: {datetime.now().strftime('%d %b %Y %H:%M')} IST")

    # ─── Auto refresh every 3 min during market hours ─────────────────────────
    now_ist = datetime.now()
    hour, minute = now_ist.hour, now_ist.minute
    total_mins = hour * 60 + minute
    if 555 <= total_mins <= 930:  # 9:15 to 15:30
        import time
        time.sleep(180)
        st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# SCANNER PAGE
# ══════════════════════════════════════════════════════════════════════════════
def show_scanner():
    from scanner import scan_instrument, is_scanner_time, is_market_hours, MAX_SCORE
    from fetcher import STOCKS, INDICES, login

    st.markdown("## 🔍 Morning Scanner — All 47 Instruments")

    now_time = datetime.now()
    if is_scanner_time():
        st.success("✅ Best time to scan! Market has opened — 9:30 AM window active")
    elif is_market_hours():
        st.info("ℹ️ Scanner works best at 9:30 AM — results still useful anytime")
    else:
        st.warning("⚠️ Market closed — showing analysis based on last available data")

    c1, c2, c3 = st.columns([2, 2, 1])
    with c1:
        run_btn   = st.button("🔍 Run Full Scan (All 47)", type="primary", width="stretch")
    with c2:
        quick_btn = st.button("⚡ Quick Scan (Indices + Top 10)", width="stretch")
    with c3:
        if st.button("🚪 Logout", width="stretch"):
            st.session_state["logged_in"] = False
            st.rerun()

    st.divider()

    scan_key = "scanner_results"

    if run_btn or quick_btn:
        instruments = [(s, f"{s} Index") for s in INDICES]
        if quick_btn:
            instruments += [(s, n) for s, n in list(STOCKS.items())[:10]]
        else:
            instruments += [(s, n) for s, n in STOCKS.items()]

        progress_bar = st.progress(0)
        status_text  = st.empty()
        results      = []
        obj          = login()
        total        = len(instruments)

        for i, (symbol, name) in enumerate(instruments):
            status_text.markdown(f"📡 Scanning **{name}** ({i+1}/{total})...")
            progress_bar.progress((i+1) / total)
            result = scan_instrument(obj, symbol, name)
            results.append(result)

        progress_bar.empty()
        status_text.empty()

        order = {"TRADE": 0, "WATCH": 1, "SKIP": 2}
        results.sort(key=lambda r: (order.get(r.recommendation, 3), -r.score))
        st.session_state[scan_key]    = results
        st.session_state["scan_time"] = datetime.now().strftime("%d %b %Y %H:%M")

    if scan_key not in st.session_state:
        st.markdown("""
        <div style="text-align:center;padding:60px;color:#4a5568;">
            <div style="font-size:48px;">🔍</div>
            <div style="font-size:18px;margin-top:12px;">Click Run Scan to analyze all 47 instruments</div>
            <div style="font-size:13px;margin-top:8px;color:#718096;">Best time: 9:30 AM after market opens</div>
        </div>
        """, unsafe_allow_html=True)
        return

    results   = st.session_state[scan_key]
    scan_time = st.session_state.get("scan_time", "")

    trade_count = sum(1 for r in results if r.recommendation == "TRADE")
    watch_count = sum(1 for r in results if r.recommendation == "WATCH")
    skip_count  = sum(1 for r in results if r.recommendation == "SKIP")

    gap_down_count = sum(1 for r in results if r.gap_type == "GAP DOWN" and abs(r.gap_pct) > 1)
    gap_up_count   = sum(1 for r in results if r.gap_type == "GAP UP"   and abs(r.gap_pct) > 1)

    if gap_down_count > 10:
        st.error(f"⚠️ HIGH GAP DOWN DAY — {gap_down_count} stocks gapped down! Reduce position size!")
    elif gap_up_count > 10:
        st.warning(f"⚠️ HIGH GAP UP DAY — {gap_up_count} stocks gapped up! Watch for reversal!")

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("✅ Trade",  trade_count)
    m2.metric("👀 Watch",  watch_count)
    m3.metric("❌ Skip",   skip_count)
    m4.metric("🕐 Scanned", scan_time)

    st.divider()

    tab1, tab2, tab3 = st.tabs([
        f"✅ TRADE ({trade_count})",
        f"👀 WATCH ({watch_count})",
        f"❌ SKIP ({skip_count})"
    ])

    def render_cards(filtered):
        if not filtered:
            st.info("No instruments in this category")
            return
        for r in filtered:
            if r.error:
                continue
            if r.recommendation == "TRADE":
                border = "#00c853" if r.signal == "BULLISH" else "#ff1744"
                bg     = "#0d2b1d" if r.signal == "BULLISH" else "#2b0d0d"
            elif r.recommendation == "WATCH":
                border, bg = "#ffd600", "#1d1d0d"
            else:
                border, bg = "#4a5568", "#1a1a1a"

            score_bar = "█" * r.score + "░" * (MAX_SCORE - r.score)
            gap_color = "#00c853" if r.gap_pct > 0 else "#ff1744" if r.gap_pct < 0 else "#a0aec0"

            st.markdown(f"""
            <div style="background:{bg};border-left:4px solid {border};
                        border-radius:8px;padding:16px 20px;margin-bottom:12px;">
                <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;">
                    <div>
                        <span style="font-size:18px;font-weight:700;color:{border}">
                            {r.bias_emoji} {r.name}
                        </span>
                        <span style="font-size:12px;color:#718096;margin-left:8px">({r.symbol})</span>
                    </div>
                    <div style="display:flex;gap:12px;align-items:center;">
                        <span style="background:{border};color:#fff;padding:2px 10px;
                              border-radius:4px;font-size:12px;font-weight:700">{r.recommendation}</span>
                        <span style="font-size:12px;color:#a0aec0">
                            Score: <b style="color:{border}">{r.score}/{MAX_SCORE}</b> {score_bar}
                        </span>
                    </div>
                </div>
                <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));
                            gap:8px;margin-top:12px;">
                    <div style="background:rgba(255,255,255,0.05);border-radius:6px;padding:8px 12px;">
                        <div style="font-size:10px;color:#718096;">PRICE</div>
                        <div style="font-size:14px;font-weight:600;color:#e2e8f0;">₹{r.price:.1f}</div>
                    </div>
                    <div style="background:rgba(255,255,255,0.05);border-radius:6px;padding:8px 12px;">
                        <div style="font-size:10px;color:#718096;">GAP</div>
                        <div style="font-size:14px;font-weight:600;color:{gap_color}">
                            {r.gap_pct:+.2f}% {r.gap_type}</div>
                    </div>
                    <div style="background:rgba(255,255,255,0.05);border-radius:6px;padding:8px 12px;">
                        <div style="font-size:10px;color:#718096;">PREV POC</div>
                        <div style="font-size:14px;font-weight:600;color:#ff1744;">₹{r.prev_poc:.1f}</div>
                        <div style="font-size:10px;color:#718096;">Price: {r.poc_position}</div>
                    </div>
                    <div style="background:rgba(255,255,255,0.05);border-radius:6px;padding:8px 12px;">
                        <div style="font-size:10px;color:#718096;">VAH / VAL</div>
                        <div style="font-size:13px;font-weight:600;color:#1e88e5;">
                            ₹{r.prev_vah:.1f} / ₹{r.prev_val:.1f}</div>
                    </div>
                    <div style="background:rgba(255,255,255,0.05);border-radius:6px;padding:8px 12px;">
                        <div style="font-size:10px;color:#718096;">WEEKLY POC</div>
                        <div style="font-size:14px;font-weight:600;color:#00c853;">₹{r.weekly_poc:.1f}</div>
                    </div>
                    <div style="background:rgba(255,255,255,0.05);border-radius:6px;padding:8px 12px;">
                        <div style="font-size:10px;color:#718096;">OPENING SURGE</div>
                        <div style="font-size:14px;font-weight:600;color:{'#ff6d00' if r.opening_surge else '#4a5568'}">
                            {'⚡ ' + str(r.max_surge) + 'x' if r.opening_surge else 'None'}</div>
                    </div>
                </div>
                <div style="margin-top:10px;padding:8px 12px;background:rgba(255,255,255,0.05);
                            border-radius:6px;font-size:12px;color:#a0aec0;">
                    💡 {r.reason}
                </div>
            </div>
            """, unsafe_allow_html=True)

            if st.button(f"📊 View {r.symbol} Chart", key=f"goto_{r.symbol}"):
                st.session_state["selected_symbol"] = r.symbol
                st.session_state["active_page"]     = "chart"
                st.rerun()

    with tab1:
        render_cards([r for r in results if r.recommendation == "TRADE"])
    with tab2:
        render_cards([r for r in results if r.recommendation == "WATCH"])
    with tab3:
        render_cards([r for r in results if r.recommendation == "SKIP"])


# ══════════════════════════════════════════════════════════════════════════════
# ENTRY
# ══════════════════════════════════════════════════════════════════════════════
if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False
if "active_page" not in st.session_state:
    st.session_state["active_page"] = "chart"

if not st.session_state["logged_in"]:
    show_login()
else:
    # ── Navigation ────────────────────────────────────────────────────────────
    nav1, nav2, nav3 = st.columns([1, 1, 8])
    with nav1:
        if st.button("📊 Chart", width="stretch",
                     type="primary" if st.session_state["active_page"] == "chart" else "secondary"):
            st.session_state["active_page"] = "chart"
            st.rerun()
    with nav2:
        if st.button("🔍 Scanner", width="stretch",
                     type="primary" if st.session_state["active_page"] == "scanner" else "secondary"):
            st.session_state["active_page"] = "scanner"
            st.rerun()

    st.divider()

    if st.session_state["active_page"] == "chart":
        show_app()
    else:
        show_scanner()

