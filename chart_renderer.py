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


def build_chart_data(df: pd.DataFrame, profiles: List[SessionProfile]) -> dict:
    """Convert DataFrame + profiles into JSON-serializable dict for JS chart."""

    df_plot = df.copy()
    df_plot.index = pd.to_datetime(df_plot.index, utc=True).tz_convert("Asia/Kolkata")

    # ── Candles ───────────────────────────────────────────────────────────────
    candles = []
    for ts, row in df_plot.iterrows():
        candles.append({
            "time":  int(ts.timestamp()),
            "open":  round(float(row["open"]),  2),
            "high":  round(float(row["high"]),  2),
            "low":   round(float(row["low"]),   2),
            "close": round(float(row["close"]), 2),
        })

    # ── Volume ────────────────────────────────────────────────────────────────
    volume = []
    for ts, row in df_plot.iterrows():
        volume.append({
            "time":  int(ts.timestamp()),
            "value": int(row["volume"]),
            "color": "#26a69a" if row["close"] >= row["open"] else "#ef5350",
        })

    # ── Sessions ──────────────────────────────────────────────────────────────
    sessions = []
    for p in profiles:
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
            "startTs": int(day_df.index[0].timestamp()),
            "endTs":   int(day_df.index[-1].timestamp()),
            "poc":     p.poc,
            "vah":     p.vah,
            "val":     p.val,
            "high":    p.day_high,
            "low":     p.day_low,
            "close":   p.day_close,
            "bias":    p.bias,
            "bars":    bars,
        })

    return {"candles": candles, "volume": volume, "sessions": sessions}


def render_chart_html(
    df: pd.DataFrame,
    profiles: List[SessionProfile],
    symbol: str = "NIFTY",
    height: int = 650,
) -> str:
    """Generate full HTML string for Lightweight Charts."""

    data     = build_chart_data(df, profiles)
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
#levels {{ display:flex; gap:16px; font-size:11px; }}
.lvl {{ display:flex; gap:4px; align-items:center; font-weight:500; }}
#wrap {{ width:100%; height:{height}px; display:flex; flex-direction:column; }}
#chart    {{ width:100%; flex:5; position:relative; }}
#volchart {{ width:100%; flex:1; border-top:1px solid #2a2e39; }}
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
    <div id="levels">
        <div class="lvl" style="color:#ff1744">POC <span id="lv-poc">—</span></div>
        <div class="lvl" style="color:#1e88e5">VAH <span id="lv-vah">—</span></div>
        <div class="lvl" style="color:#1e88e5">VAL <span id="lv-val">—</span></div>
        <div class="lvl" style="color:#ef6c00">P.High <span id="lv-ph">—</span></div>
        <div class="lvl" style="color:#ef6c00">P.Low <span id="lv-pl">—</span></div>
        <div class="lvl" style="color:#00c853">W.POC <span id="lv-wpoc">—</span></div>
    </div>
</div>
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
            const d = new Date(t*1000);
            return d.toLocaleString('en-IN',{{hour:'2-digit',minute:'2-digit',hour12:false,timeZone:'Asia/Kolkata'}});
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
}}

chart.timeScale().subscribeVisibleTimeRangeChange(renderAll);
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
