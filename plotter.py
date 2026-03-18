"""
plotter.py
──────────
Plotly chart builder for Session Volume Profile.
Renders candlestick chart + volume profile histogram + key levels.
Matches TradingView SVP HD style exactly.
"""

import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from typing import List, Optional
from volume_profile import SessionProfile, get_key_levels, get_weekly_poc

# ─── Color Scheme (matches TradingView SVP HD settings) ───────────────────────
COLORS = {
    "up_candle":       "#26a69a",   # teal green
    "down_candle":     "#ef5350",   # red
    "up_vol_va":       "#00bcd4",   # teal (value area up)
    "down_vol_va":     "#f06292",   # pink (value area down)
    "up_vol_outside":  "#90a4ae",   # grey (outside value area)
    "down_vol_outside":"#90a4ae",   # grey (outside value area)
    "poc_line":        "#ff1744",   # red
    "vah_line":        "#1565c0",   # blue
    "val_line":        "#1565c0",   # blue
    "weekly_poc":      "#00e676",   # green
    "prev_high":       "#ff6f00",   # orange
    "prev_low":        "#ff6f00",   # orange
    "bg":              "#131722",   # dark background
    "grid":            "#1e2130",   # dark grid
    "text":            "#d1d4dc",   # light text
}


def build_chart(
    df: pd.DataFrame,
    profiles: List[SessionProfile],
    symbol: str = "NIFTY",
    show_weekly_poc: bool = True,
    show_prev_levels: bool = True,
    profile_width_pct: float = 0.3,
    show_candles: bool = True,
) -> go.Figure:
    """
    Build full chart: candlesticks + volume profile + key levels.

    Parameters:
        df                : Full OHLCV DataFrame (3m candles)
        profiles          : List of SessionProfile objects
        symbol            : "NIFTY" or "BANKNIFTY"
        show_weekly_poc   : Show weekly POC line
        show_prev_levels  : Show prev day POC/VAH/VAL lines
        profile_width_pct : Profile bar width as fraction of session time

    Returns:
        plotly Figure object
    """

    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        row_heights=[0.80, 0.20],
        vertical_spacing=0.02,
    )

    # ─── Prepare DataFrame ────────────────────────────────────────────────────
    df_plot = df.copy()
    df_plot.index = pd.to_datetime(df_plot.index, utc=True).tz_convert("Asia/Kolkata")

    # ─── Candlestick Chart ────────────────────────────────────────────────────
    if show_candles:
        fig.add_trace(
            go.Candlestick(
                x          = df_plot.index,
                open       = df_plot["open"],
                high       = df_plot["high"],
                low        = df_plot["low"],
                close      = df_plot["close"],
                name       = f"{symbol} FUT",
                increasing = dict(line=dict(color=COLORS["up_candle"]),   fillcolor=COLORS["up_candle"]),
                decreasing = dict(line=dict(color=COLORS["down_candle"]), fillcolor=COLORS["down_candle"]),
                showlegend = False,
            ),
            row=1, col=1
        )
    else:
        # Just plot a line so chart still shows price range
        fig.add_trace(
            go.Scatter(
                x          = df_plot.index,
                y          = df_plot["close"],
                mode       = "lines",
                line       = dict(color=COLORS["up_candle"], width=1),
                name       = f"{symbol} FUT",
                showlegend = False,
            ),
            row=1, col=1
        )

    # ─── Volume Bars (bottom panel) ───────────────────────────────────────────
    colors_vol = [
        COLORS["up_candle"] if c >= o else COLORS["down_candle"]
        for c, o in zip(df_plot["close"], df_plot["open"])
    ]
    fig.add_trace(
        go.Bar(
            x          = df_plot.index,
            y          = df_plot["volume"],
            name       = "Volume",
            marker_color = colors_vol,
            showlegend = False,
        ),
        row=2, col=1
    )

    # ─── Volume Profile Histograms (per session) ──────────────────────────────
    for profile in profiles:
        _add_profile_bars(fig, profile, df_plot, profile_width_pct)

    # ─── Key Levels (prev day) ────────────────────────────────────────────────
    if show_prev_levels and len(profiles) >= 2:
        # Use second-to-last session as "previous day"
        prev = profiles[-2]
        last = profiles[-1]

        x_start = df_plot.index[0]
        x_end   = df_plot.index[-1]

        # Previous day POC
        _add_hline(fig, prev.poc,  COLORS["poc_line"],  "Prev POC",  x_start, x_end, dash="solid",  width=1.5)
        # Previous day VAH
        _add_hline(fig, prev.vah,  COLORS["vah_line"],  "Prev VAH",  x_start, x_end, dash="dash",   width=1.0)
        # Previous day VAL
        _add_hline(fig, prev.val,  COLORS["val_line"],  "Prev VAL",  x_start, x_end, dash="dash",   width=1.0)
        # Previous day High/Low
        _add_hline(fig, prev.day_high, COLORS["prev_high"], "Prev High", x_start, x_end, dash="dot", width=1.0)
        _add_hline(fig, prev.day_low,  COLORS["prev_low"],  "Prev Low",  x_start, x_end, dash="dot", width=1.0)

    # ─── Weekly POC ───────────────────────────────────────────────────────────
    if show_weekly_poc:
        weekly_poc = get_weekly_poc(profiles)
        x_start    = df_plot.index[0]
        x_end      = df_plot.index[-1]
        _add_hline(fig, weekly_poc, COLORS["weekly_poc"], "Weekly POC", x_start, x_end, dash="dashdot", width=2.0)

    # ─── Layout ───────────────────────────────────────────────────────────────
    fig.update_layout(
        title      = dict(
            text   = f"<b>{symbol} — Session Volume Profile</b>",
            x      = 0.01,
            font   = dict(color=COLORS["text"], size=16),
        ),
        paper_bgcolor = COLORS["bg"],
        plot_bgcolor  = COLORS["bg"],
        font          = dict(color=COLORS["text"], size=12),
        xaxis_rangeslider_visible = False,
        hovermode     = "x unified",
        margin        = dict(l=60, r=80, t=50, b=40),
        legend        = dict(
            bgcolor     = "#1e2130",
            bordercolor = "#2a2e39",
            borderwidth = 1,
            font        = dict(color=COLORS["text"]),
        ),
        height = 750,
    )

    # Grid styling
    for axis in ["xaxis", "yaxis", "xaxis2", "yaxis2"]:
        fig.update_layout(**{
            axis: dict(
                gridcolor    = COLORS["grid"],
                zerolinecolor= COLORS["grid"],
                color        = COLORS["text"],
            )
        })

    # Hide x-axis labels on top panel
    fig.update_xaxes(showticklabels=False, row=1, col=1)
    fig.update_xaxes(row=2, col=1)
    fig.update_yaxes(title_text=f"{symbol}", row=1, col=1, side="right", tickformat=",.0f")
    fig.update_yaxes(title_text="Volume",    row=2, col=1, side="right", tickformat=",.0f")

    return fig


def _add_profile_bars(
    fig: go.Figure,
    profile: SessionProfile,
    df_plot: pd.DataFrame,
    width_pct: float = 0.3,
) -> None:
    """
    Add horizontal volume profile bars for one session.
    Bars are drawn LEFT side of the session (matching TradingView placement=Left).
    """
    # Get session candles
    session_mask = df_plot.index.date == pd.to_datetime(profile.date).date()
    session_df   = df_plot[session_mask]

    if session_df.empty:
        return

    session_start = session_df.index[0]
    session_end   = session_df.index[-1]

    # Time duration of session in seconds
    session_duration = (session_end - session_start).total_seconds()
    max_bar_seconds  = session_duration * width_pct

    # Max volume for normalizing bar width
    max_vol = max(bar.total_vol for bar in profile.bars) if profile.bars else 1

    for bar in profile.bars:
        if bar.total_vol <= 0:
            continue

        # Bar width proportional to volume
        bar_seconds  = (bar.total_vol / max_vol) * max_bar_seconds
        bar_end_time = session_start + pd.Timedelta(seconds=bar_seconds)

        # Up volume width
        up_seconds   = (bar.up_vol / max_vol) * max_bar_seconds
        up_end_time  = session_start + pd.Timedelta(seconds=up_seconds)

        # Down volume width
        dn_seconds   = (bar.down_vol / max_vol) * max_bar_seconds
        dn_end_time  = session_start + pd.Timedelta(seconds=dn_seconds)

        if bar.is_poc:
            # POC bin — full red
            fig.add_shape(
                type="rect",
                x0=session_start, x1=bar_end_time,
                y0=bar.price_low,  y1=bar.price_high,
                fillcolor=COLORS["poc_line"], opacity=0.85,
                line=dict(width=0), row=1, col=1,
            )
        elif bar.in_value_area:
            # Value area — draw grey base first, then teal up on top, pink down on top
            fig.add_shape(
                type="rect",
                x0=session_start, x1=bar_end_time,
                y0=bar.price_low,  y1=bar.price_high,
                fillcolor=COLORS["up_vol_outside"], opacity=0.25,
                line=dict(width=0), row=1, col=1,
            )
            # Teal up volume
            if bar.up_vol > 0:
                fig.add_shape(
                    type="rect",
                    x0=session_start, x1=up_end_time,
                    y0=bar.price_low,  y1=bar.price_high,
                    fillcolor=COLORS["up_vol_va"], opacity=0.80,
                    line=dict(width=0), row=1, col=1,
                )
            # Pink down volume (stacked after up)
            if bar.down_vol > 0:
                fig.add_shape(
                    type="rect",
                    x0=up_end_time, x1=bar_end_time,
                    y0=bar.price_low, y1=bar.price_high,
                    fillcolor=COLORS["down_vol_va"], opacity=0.80,
                    line=dict(width=0), row=1, col=1,
                )
        else:
            # Outside value area — grey only
            fig.add_shape(
                type="rect",
                x0=session_start, x1=bar_end_time,
                y0=bar.price_low,  y1=bar.price_high,
                fillcolor=COLORS["up_vol_outside"], opacity=0.40,
                line=dict(width=0), row=1, col=1,
            )

    # ─── POC Line (extends across session) ────────────────────────────────────
    fig.add_shape(
        type      = "line",
        x0        = session_start,
        x1        = session_end,
        y0        = profile.poc,
        y1        = profile.poc,
        line      = dict(color=COLORS["poc_line"], width=1.5, dash="solid"),
        row=1, col=1,
    )

    # ─── VAH Line ─────────────────────────────────────────────────────────────
    fig.add_shape(
        type  = "line",
        x0    = session_start,
        x1    = session_end,
        y0    = profile.vah,
        y1    = profile.vah,
        line  = dict(color=COLORS["vah_line"], width=1, dash="solid"),
        row=1, col=1,
    )

    # ─── VAL Line ─────────────────────────────────────────────────────────────
    fig.add_shape(
        type  = "line",
        x0    = session_start,
        x1    = session_end,
        y0    = profile.val,
        y1    = profile.val,
        line  = dict(color=COLORS["val_line"], width=1, dash="solid"),
        row=1, col=1,
    )

    # ─── POC Label ────────────────────────────────────────────────────────────
    fig.add_annotation(
        x         = session_end,
        y         = profile.poc,
        text      = f"POC {profile.poc:.0f}",
        showarrow = False,
        xanchor   = "left",
        font      = dict(color=COLORS["poc_line"], size=9),
        row=1, col=1,
    )


def _add_hline(
    fig: go.Figure,
    price: float,
    color: str,
    label: str,
    x_start,
    x_end,
    dash: str = "dash",
    width: float = 1.0,
) -> None:
    """Add a horizontal level line with label across the full chart."""
    fig.add_shape(
        type  = "line",
        x0    = x_start,
        x1    = x_end,
        y0    = price,
        y1    = price,
        line  = dict(color=color, width=width, dash=dash),
        row=1, col=1,
    )
    fig.add_annotation(
        x         = x_end,
        y         = price,
        text      = f"{label} {price:.0f}",
        showarrow = False,
        xanchor   = "left",
        font      = dict(color=color, size=9),
        row=1, col=1,
    )


def build_signal_card(levels: dict, symbol: str) -> str:
    """
    Build HTML signal card string for Streamlit display.
    """
    bias        = levels.get("bias", "SIDEWAYS")
    emoji       = levels.get("bias_emoji", "🟡")
    detail      = levels.get("bias_detail", "")
    bg_color    = {"BULLISH": "#0d2b1d", "BEARISH": "#2b0d0d", "SIDEWAYS": "#1d1d0d"}.get(bias, "#1d1d0d")
    border_color= {"BULLISH": "#00c853", "BEARISH": "#ff1744",  "SIDEWAYS": "#ffd600"}.get(bias, "#ffd600")

    return f"""
    <div style="
        background:{bg_color};
        border-left: 4px solid {border_color};
        padding: 14px 18px;
        border-radius: 6px;
        margin-bottom: 12px;
    ">
        <div style="font-size:22px; font-weight:bold; color:{border_color};">
            {emoji} {bias} — {symbol}
        </div>
        <div style="font-size:13px; color:#d1d4dc; margin-top:6px;">
            {detail}
        </div>
    </div>
    """


def build_levels_table(levels: dict) -> pd.DataFrame:
    """Build a clean key levels DataFrame for display."""
    rows = [
        {"Level": "🔴 Prev POC",   "Price": f"{levels['prev_poc']:.1f}",   "Note": "Most important — watch reaction here"},
        {"Level": "🔵 Prev VAH",   "Price": f"{levels['prev_vah']:.1f}",   "Note": "Breakout above = bullish continuation"},
        {"Level": "🔵 Prev VAL",   "Price": f"{levels['prev_val']:.1f}",   "Note": "Breakdown below = bearish continuation"},
        {"Level": "🟠 Prev High",  "Price": f"{levels['prev_high']:.1f}",  "Note": "Classical resistance"},
        {"Level": "🟠 Prev Low",   "Price": f"{levels['prev_low']:.1f}",   "Note": "Classical support"},
        {"Level": "🟣 Weekly POC", "Price": f"{levels['weekly_poc']:.1f}", "Note": "Big level — strong S/R all week"},
    ]
    return pd.DataFrame(rows)
