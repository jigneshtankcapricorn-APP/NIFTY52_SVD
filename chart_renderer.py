"""
chart_renderer.py
─────────────────
Generates Lightweight Charts HTML with injected real data.
Used by Streamlit via st.components.v1.html()
"""

import json
import pandas as pd
from typing import List
from volume_profile import SessionProfile, get_weekly_poc


def build_chart_data(df: pd.DataFrame, profiles: List[SessionProfile], market_open: bool = False) -> dict:
    """Convert DataFrame + profiles into JSON-serializable dict for JS chart."""

    df_plot = df.copy()
    df_plot.index = pd.to_datetime(df_plot.index, utc=True).tz_convert("Asia/Kolkata")

    def to_chart_ts(ts):
        naive = ts.replace(tzinfo=None)
        return int(naive.timestamp())

    # ── Smart date filter ─────────────────────────────────────────────────────
    if market_open and len(profiles) >= 2:
        dates      = sorted(set(df_plot.index.date))
        show_dates = set(dates[-2:])
        df_plot    = df_plot[[d in show_dates for d in df_plot.index.date]]
        profiles_to_show = profiles[-2:]
    else:
        profiles_to_show = profiles

    # ── Candles ───────────────────────────────────────────────────────────────
    candles = []
    for ts, row in df_plot.iterrows():
        candles.append({
            "time":  to_chart_ts(ts),
            "open":  round(float(row["open"]),  2),
            "high":  round(float(row["high"]),  2),
            "low":   round(float(row["low"]),   2),
            "close": round(float(row["close"]), 2),
        })

    # ── Volume ────────────────────────────────────────────────────────────────
    volume = []
    for ts, row in df_plot.iterrows():
        volume.append({
            "time":  to_chart_ts(ts),
            "value": int(row["volume"]),
            "color": "#26a69a" if row["close"] >= row["open"] else "#ef5350",
        })

    # ── Sessions ──────────────────────────────────────────────────────────────
    sessions = []
    for p in profiles_to_show:
        day_df = df_plot[df_plot.index.date == pd.to_datetime(p.date).date()]
        if day_df.empty:
            continue

        bars = []
        for b in p.bars:
            bars.append({
                "priceLow":  b.price_low,
                "priceHigh": b.price_high,
                "totalVol":  b.total_vol,
                "upVol":     b.up_vol,
                "downVol":   b.down_vol,
                "inVA":      b.in_value_area,
                "isPOC":     b.is_poc,
            })

        sessions.append({
            "date":    p.date,
            "startTs": to_chart_ts(day_df.index[0]),
            "endTs":   to_chart_ts(day_df.index[-1]),
            "poc":     p.poc,
            "vah":     p.vah,
            "val":     p.val,
            "high":    p.day_high,
            "low":     p.day_low,
            "close":   p.day_close,
            "bias":    p.bias,
            "bars":    bars,
        })

    # ── Volume Surge Detection (today only, 2.5x average) ────────────────────
    # Always use full df for surge detection regardless of view filter
    df_full = df.copy()
    df_full.index = pd.to_datetime(df_full.index, utc=True).tz_convert("Asia/Kolkata")

    SURGE_MULTIPLIER = 2.5
    LOOKBACK         = 20
    surges           = []
    today_date       = df_full.index[-1].date()
    vol_values       = list(df_full["volume"])

    for i, (ts, row) in enumerate(df_full.iterrows()):
        if ts.date() != today_date:
            continue
        if i < LOOKBACK:
            continue
        avg = sum(vol_values[i-LOOKBACK:i]) / LOOKBACK
        if avg > 0 and row["volume"] > avg * SURGE_MULTIPLIER:
            surges.append({
                "time":       to_chart_ts(ts),
                "price":      round(float(row["close"]), 2),
                "volume":     int(row["volume"]),
                "avg":        round(avg, 0),
                "multiplier": round(row["volume"] / avg, 1),
                "timeStr":    ts.strftime("%H:%M"),
            })

    return {"candles": candles, "volume": volume, "sessions": sessions, "surges": surges}


def render_chart_html(
    df: pd.DataFrame,
    profiles: List[SessionProfile],
    symbol: str = "NIFTY",
    height: int = 650,
    market_open: bool = False,
    zones: list = None,
) -> str:
    """Generate full HTML string for Lightweight Charts."""

    data      = build_chart_data(df, profiles, market_open=market_open)
    if zones:
        data["zones"] = zones
    else:
        data["zones"] = []
    DATA_JSON = json.dumps(data)

    last = profiles[-1] if profiles else None
    prev = profiles[-2] if len(profiles) >= 2 else None

    title = f"📊 {symbol} FUT — Session Volume Profile"

    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<script src="https://unpkg.com/lightweight-charts@4.1.3/dist/lightweight-charts.standalone.production.js"></script>
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ background:#131722; font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif; color:#d1d4dc; overflow:hidden; }}
#header {{
    display:flex; align-items:center; gap:12px;
    padding:6px 16px; background:#1e222d;
    border-bottom:1px solid #2a2e39; height:40px;
}}
#header h1 {{ font-size:13px; font-weight:600; color:#d1d4dc; white-space:nowrap; }}
.badge {{ padding:2px 10px; border-radius:4px; font-size:12px; font-weight:700; }}
.bull {{ background:#0d2b1d; color:#00c853; border:1px solid #00c853; }}
.bear {{ background:#2b0d0d; color:#ff1744; border:1px solid #ff1744; }}
.side {{ background:#1d1d0d; color:#ffd600; border:1px solid #ffd600; }}
.live-badge {{ background:#1a0a00; color:#ff6d00; border:1px solid #ff6d00; padding:2px 8px; border-radius:4px; font-size:11px; font-weight:700; }}
#levels {{ display:flex; gap:16px; font-size:11px; }}
.lvl {{ display:flex; gap:4px; align-items:center; font-weight:500; }}
#surge-bar {{
    position:fixed; bottom:0; left:0; right:0;
    background:#1a1000; border-top:1px solid #ff6d00;
    padding:4px 16px; font-size:11px; color:#ff6d00;
    display:none; z-index:100; flex-wrap:wrap; gap:12px;
}}
.surge-item {{
    background:#2a1500; border:1px solid #ff6d00;
    padding:2px 8px; border-radius:4px; white-space:nowrap;
}}
#timer {{ font-size:10px; color:#4a5568; margin-left:auto; }}
#wrap {{ width:100%; height:{height - 50}px; display:flex; flex-direction:column; }}
#chart    {{ width:100%; flex:5; position:relative; }}
#volchart {{ width:100%; flex:1.2; border-top:1px solid #2a2e39; }}
.price-label {{
    position:absolute; right:0;
    font-size:10px; font-weight:700;
    padding:1px 5px; border-radius:3px;
    white-space:nowrap; transform:translateY(-50%);
    pointer-events:none;
}}
</style>
</head>
<body>
<div id="header">
    <h1>{title}</h1>
    <div id="bias-badge" class="badge side">🟡 SIDEWAYS</div>
    <div id="live-badge" class="live-badge" style="display:none">🔴 LIVE</div>
    <div id="levels">
        <div class="lvl" style="color:#ff1744">POC <span id="lv-poc">—</span></div>
        <div class="lvl" style="color:#1e88e5">VAH <span id="lv-vah">—</span></div>
        <div class="lvl" style="color:#1e88e5">VAL <span id="lv-val">—</span></div>
        <div class="lvl" style="color:#ef6c00">P.High <span id="lv-ph">—</span></div>
        <div class="lvl" style="color:#ef6c00">P.Low <span id="lv-pl">—</span></div>
        <div class="lvl" style="color:#00c853">W.POC <span id="lv-wpoc">—</span></div>
        <div id="timer"></div>
    </div>
</div>
<div id="surge-bar"></div>
<div id="wrap">
  <div id="chart"></div>
  <div id="volchart"></div>
</div>

<script>
const RAW = {DATA_JSON};

const chartEl = document.getElementById('chart');
const chart = LightweightCharts.createChart(chartEl, {{
    width: chartEl.offsetWidth, height: chartEl.offsetHeight,
    layout: {{ background:{{color:'#131722'}}, textColor:'#d1d4dc', fontSize:12 }},
    grid:   {{ vertLines:{{color:'#1e2130'}}, horzLines:{{color:'#1e2130'}} }},
    crosshair: {{ mode: LightweightCharts.CrosshairMode.Normal }},
    rightPriceScale: {{ borderColor:'#2a2e39', scaleMarginTop:0.03, scaleMarginBottom:0.03 }},
    timeScale: {{
        borderColor:'#2a2e39', timeVisible:true, secondsVisible:false,
        tickMarkFormatter:(t) => {{
            const d = new Date(t * 1000);
            const h = String(d.getUTCHours()).padStart(2,'0');
            const m = String(d.getUTCMinutes()).padStart(2,'0');
            const day = d.getUTCDate();
            const mon = ['Jan','Feb','Mar','Apr','May','Jun',
                         'Jul','Aug','Sep','Oct','Nov','Dec'][d.getUTCMonth()];
            if (h === '09' && m === '15') return day + ' ' + mon;
            return h + ':' + m;
        }}
    }},
}});

const volEl = document.getElementById('volchart');
const volChart = LightweightCharts.createChart(volEl, {{
    width: volEl.offsetWidth, height: volEl.offsetHeight,
    layout: {{ background:{{color:'#131722'}}, textColor:'#d1d4dc', fontSize:10 }},
    grid:   {{ vertLines:{{color:'#1e2130'}}, horzLines:{{color:'#1e2130'}} }},
    rightPriceScale: {{ borderColor:'#2a2e39', scaleMarginTop:0.1, scaleMarginBottom:0 }},
    timeScale: {{ borderColor:'#2a2e39', timeVisible:true, secondsVisible:false }},
    crosshair: {{ mode: LightweightCharts.CrosshairMode.Normal }},
}});

const candleSeries = chart.addCandlestickSeries({{
    upColor:'#26a69a', downColor:'#ef5350',
    borderUpColor:'#26a69a', borderDownColor:'#ef5350',
    wickUpColor:'#26a69a', wickDownColor:'#ef5350',
    lastValueVisible: false, priceLineVisible: false,
}});
candleSeries.setData(RAW.candles);

const volSeries = volChart.addHistogramSeries({{
    priceFormat:{{type:'volume'}},
    lastValueVisible: false, priceLineVisible: false,
}});
volSeries.setData(RAW.volume);

chart.timeScale().subscribeVisibleLogicalRangeChange(r => {{ if(r) volChart.timeScale().setVisibleLogicalRange(r); }});
volChart.timeScale().subscribeVisibleLogicalRangeChange(r => {{ if(r) chart.timeScale().setVisibleLogicalRange(r); }});

// ── Calc weekly POC ───────────────────────────────────────────────────────────
const allBins = {{}};
RAW.sessions.forEach(s => s.bars.forEach(b => {{
    const k = (b.priceLow + b.priceHigh) / 2;
    allBins[k] = (allBins[k]||0) + b.totalVol;
}}));
const weeklyPoc = parseFloat(Object.entries(allBins).sort((a,b)=>b[1]-a[1])[0][0]);
const prev = RAW.sessions[RAW.sessions.length - 2];
const last = RAW.sessions[RAW.sessions.length - 1];

// ── Header ────────────────────────────────────────────────────────────────────
document.getElementById('lv-poc').textContent  = last.poc;
document.getElementById('lv-vah').textContent  = last.vah;
document.getElementById('lv-val').textContent  = last.val;
document.getElementById('lv-ph').textContent   = prev ? prev.high : '—';
document.getElementById('lv-pl').textContent   = prev ? prev.low  : '—';
document.getElementById('lv-wpoc').textContent = weeklyPoc;
const badge = document.getElementById('bias-badge');
const b = last.bias;
badge.className = 'badge '+(b==='BULLISH'?'bull':b==='BEARISH'?'bear':'side');
badge.textContent = b==='BULLISH'?'🟢 BULLISH':b==='BEARISH'?'🔴 BEARISH':'🟡 SIDEWAYS';

// ── Floating HTML labels (right side, no lines) ───────────────────────────────
const labelsDiv = document.createElement('div');
labelsDiv.style.cssText = 'position:absolute;right:70px;top:0;pointer-events:none;z-index:20;height:100%;';
chartEl.appendChild(labelsDiv);

const KEY_LEVELS = prev ? [
    {{ price: prev.poc,  color:'#ff1744', bg:'rgba(255,23,68,0.15)',   text:'Prev POC '  + prev.poc  }},
    {{ price: prev.vah,  color:'#1e88e5', bg:'rgba(30,136,229,0.15)',  text:'Prev VAH '  + prev.vah  }},
    {{ price: prev.val,  color:'#1e88e5', bg:'rgba(30,136,229,0.15)',  text:'Prev VAL '  + prev.val  }},
    {{ price: prev.high, color:'#ef6c00', bg:'rgba(239,108,0,0.15)',   text:'Prev High ' + prev.high }},
    {{ price: prev.low,  color:'#ef6c00', bg:'rgba(239,108,0,0.15)',   text:'Prev Low '  + prev.low  }},
    {{ price: weeklyPoc, color:'#00c853', bg:'rgba(0,200,83,0.15)',    text:'W.POC '     + weeklyPoc }},
] : [];

const labelEls = KEY_LEVELS.map(lv => {{
    const el = document.createElement('div');
    el.className = 'price-label';
    el.textContent = lv.text;
    el.style.color = lv.color;
    el.style.background = lv.bg;
    el.style.border = '1px solid ' + lv.color;
    labelsDiv.appendChild(el);
    return {{ el, price: lv.price }};
}});

function updateLabels() {{
    labelEls.forEach(item => {{
        const y = candleSeries.priceToCoordinate(item.price);
        if (y === null || y < 0 || y > chartEl.offsetHeight) {{
            item.el.style.display = 'none'; return;
        }}
        item.el.style.display = 'block';
        item.el.style.top = y + 'px';
    }});
}}

// ── Canvas — profile bars + session POC/VAH/VAL ───────────────────────────────
const canvas = document.createElement('canvas');
canvas.style.cssText = 'position:absolute;top:0;left:0;pointer-events:none;z-index:10;';
canvas.width  = chartEl.offsetWidth;
canvas.height = chartEl.offsetHeight;
chartEl.appendChild(canvas);
const ctx = canvas.getContext('2d');

// ── Draw Supply/Demand Zones ──────────────────────────────────────────────────
function drawZones() {{
    if (!RAW.zones || !RAW.zones.length) return;

    RAW.zones.forEach(zone => {{
        const y1 = candleSeries.priceToCoordinate(zone.high);
        const y2 = candleSeries.priceToCoordinate(zone.low);
        if (y1 === null || y2 === null) return;

        const yTop  = Math.min(y1, y2);
        const yBot  = Math.max(y1, y2);
        const zoneH = Math.max(yBot - yTop, 4);
        const W     = canvas.width;

        // Zone rectangle — full width
        ctx.save();
        ctx.fillStyle   = zone.colorFill;
        ctx.strokeStyle = zone.colorBorder;
        ctx.lineWidth   = 1;
        ctx.fillRect(0, yTop, W, zoneH);
        // Top border line
        ctx.beginPath();
        ctx.moveTo(0,  yTop);
        ctx.lineTo(W,  yTop);
        ctx.stroke();
        // Bottom border line
        ctx.beginPath();
        ctx.moveTo(0,  yBot);
        ctx.lineTo(W,  yBot);
        ctx.stroke();
        ctx.restore();

        // Zone label — right side
        ctx.save();
        ctx.font      = 'bold 10px sans-serif';
        ctx.fillStyle = zone.labelColor;
        ctx.textAlign = 'right';
        ctx.fillText(zone.label, W - 75, yTop + zoneH / 2 + 4);
        ctx.restore();
    }});
}}

function renderAll() {{
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    const ts = chart.timeScale();
    const W  = canvas.width;

    RAW.sessions.forEach((session, idx) => {{
        const maxVol = Math.max(...session.bars.map(b => b.totalVol));
        const startX = ts.timeToCoordinate(session.startTs);
        const endX   = ts.timeToCoordinate(session.endTs);
        if (startX===null||endX===null) return;
        const maxBarW = Math.abs(endX - startX) * 0.35;

        session.bars.forEach(bar => {{
            const y1 = candleSeries.priceToCoordinate(bar.priceHigh);
            const y2 = candleSeries.priceToCoordinate(bar.priceLow);
            if (y1===null||y2===null) return;
            const yTop = Math.min(y1,y2);
            const barH = Math.max(Math.abs(y2-y1)-1, 1);
            const upW  = (bar.upVol    / maxVol) * maxBarW;
            const dnW  = (bar.downVol  / maxVol) * maxBarW;
            const totW = (bar.totalVol / maxVol) * maxBarW;

            if (bar.isPOC) {{
                ctx.fillStyle = 'rgba(255,23,68,0.90)';
                ctx.fillRect(startX, yTop, totW, barH);
            }} else if (bar.inVA) {{
                ctx.fillStyle = 'rgba(0,188,212,0.80)';
                ctx.fillRect(startX, yTop, upW, barH);
                ctx.fillStyle = 'rgba(240,98,146,0.80)';
                ctx.fillRect(startX+upW, yTop, dnW, barH);
            }} else {{
                ctx.fillStyle = 'rgba(120,132,150,0.45)';
                ctx.fillRect(startX, yTop, totW, barH);
            }}
        }});

        // POC line
        const pocY = candleSeries.priceToCoordinate(session.poc);
        if (pocY!==null) {{
            ctx.save(); ctx.strokeStyle='#ff1744'; ctx.lineWidth=1.5; ctx.setLineDash([]);
            ctx.beginPath(); ctx.moveTo(startX,pocY); ctx.lineTo(endX,pocY); ctx.stroke(); ctx.restore();
        }}
        // VAH line
        const vahY = candleSeries.priceToCoordinate(session.vah);
        if (vahY!==null) {{
            ctx.save(); ctx.strokeStyle='#1e88e5'; ctx.lineWidth=1; ctx.setLineDash([]);
            ctx.beginPath(); ctx.moveTo(startX,vahY); ctx.lineTo(endX,vahY); ctx.stroke(); ctx.restore();
        }}
        // VAL line
        const valY = candleSeries.priceToCoordinate(session.val);
        if (valY!==null) {{
            ctx.save(); ctx.strokeStyle='#1e88e5'; ctx.lineWidth=1; ctx.setLineDash([]);
            ctx.beginPath(); ctx.moveTo(startX,valY); ctx.lineTo(endX,valY); ctx.stroke(); ctx.restore();
        }}
        // Session separator
        if (idx < RAW.sessions.length-1 && endX>0 && endX<W) {{
            ctx.save(); ctx.strokeStyle='rgba(80,90,110,0.5)';
            ctx.lineWidth=1; ctx.setLineDash([4,4]);
            ctx.beginPath(); ctx.moveTo(endX,0); ctx.lineTo(endX,canvas.height); ctx.stroke(); ctx.restore();
        }}
    }});

    updateLabels();
    drawSurgeMarkers();
    drawZones();
}}

// ── Volume Surge Markers on canvas only ──────────────────────────────────────

// ── Surge bar at bottom ───────────────────────────────────────────────────────
const surgeBar = document.getElementById('surge-bar');
if (RAW.surges && RAW.surges.length > 0) {{
    surgeBar.style.display = 'flex';
    surgeBar.innerHTML = '<b style="color:#ff6d00">⚡ Volume Surges Today:</b> ' +
        RAW.surges.map(s =>
            `<span class="surge-item">⚡ ${{s.timeStr}} @ ${{s.price}} — ${{s.multiplier}}x avg</span>`
        ).join('');
}}

// ── Surge markers on canvas (orange triangles) ────────────────────────────────
function drawSurgeMarkers() {{
    if (!RAW.surges || !RAW.surges.length) return;
    const ts = chart.timeScale();
    RAW.surges.forEach(surge => {{
        const x = ts.timeToCoordinate(surge.time);
        const y = candleSeries.priceToCoordinate(surge.price);
        if (x===null||y===null) return;
        // Draw orange triangle marker
        ctx.save();
        ctx.fillStyle = '#ff6d00';
        ctx.beginPath();
        ctx.moveTo(x,      y + 15);
        ctx.lineTo(x - 6,  y + 25);
        ctx.lineTo(x + 6,  y + 25);
        ctx.closePath();
        ctx.fill();
        // Label
        ctx.font = 'bold 9px sans-serif';
        ctx.fillStyle = '#ff6d00';
        ctx.textAlign = 'center';
        ctx.fillText('⚡' + surge.multiplier + 'x', x, y + 36);
        ctx.restore();
    }});
}}

// ── Live mode detection ───────────────────────────────────────────────────────
function isMarketHours() {{
    const now = new Date();
    const ist = new Date(now.toLocaleString('en-US', {{timeZone:'Asia/Kolkata'}}));
    const h = ist.getHours(), m = ist.getMinutes();
    const mins = h * 60 + m;
    return mins >= 555 && mins <= 930; // 9:15 to 15:30
}}

if (isMarketHours()) {{
    document.getElementById('live-badge').style.display = 'block';
    // Auto-refresh every 3 minutes via parent Streamlit
    let countdown = 180;
    const timerEl = document.getElementById('timer');
    setInterval(() => {{
        countdown--;
        const m = Math.floor(countdown/60);
        const s = countdown % 60;
        timerEl.textContent = `🔄 Refresh in ${{m}}:${{s.toString().padStart(2,'0')}}`;
        if (countdown <= 0) {{
            countdown = 180;
            // Signal parent Streamlit to refresh
            window.parent.postMessage({{type:'streamlit:rerun'}}, '*');
        }}
    }}, 1000);
}}
chart.timeScale().subscribeVisibleLogicalRangeChange(renderAll);
chart.subscribeCrosshairMove(renderAll);
window.addEventListener('resize', () => {{
    canvas.width  = chartEl.offsetWidth;
    canvas.height = chartEl.offsetHeight;
    chart.resize(chartEl.offsetWidth, chartEl.offsetHeight);
    volChart.resize(volEl.offsetWidth, volEl.offsetHeight);
    renderAll();
}});
setTimeout(renderAll, 200);
setTimeout(renderAll, 700);
</script>
</body>
</html>"""

    return html
