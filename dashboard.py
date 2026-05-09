"""
CINAX BTC — Dashboard Flask
Disponible en el puerto definido por Railway ($PORT)
"""

from flask import Flask, jsonify, render_template_string
import pandas as pd
import os
import json
from datetime import datetime

app = Flask(__name__)

DATA_DIR       = "/data"
SEÑALES_CSV    = f"{DATA_DIR}/cinax_btc_señales.csv"
POSICIONES_CSV = f"{DATA_DIR}/cinax_btc_posiciones.csv"
LOG_FILE       = f"{DATA_DIR}/cinax_btc.log"

# ══════════════════════════════════════════════════════════════
# HTML TEMPLATE
# ══════════════════════════════════════════════════════════════

HTML = """
<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>CINAX BTC — Paper Trading</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Share+Tech+Mono&family=Rajdhani:wght@400;600;700&display=swap" rel="stylesheet">
<style>
  :root {
    --bg:       #080c10;
    --panel:    #0d1117;
    --border:   #1a2332;
    --accent:   #f7931a;
    --green:    #00e5a0;
    --red:      #ff4466;
    --muted:    #4a5568;
    --text:     #c9d1d9;
    --subtext:  #8b949e;
  }

  * { box-sizing: border-box; margin: 0; padding: 0; }

  body {
    background: var(--bg);
    color: var(--text);
    font-family: 'Rajdhani', sans-serif;
    font-size: 16px;
    min-height: 100vh;
  }

  /* Grid background */
  body::before {
    content: '';
    position: fixed; inset: 0;
    background-image:
      linear-gradient(rgba(247,147,26,0.03) 1px, transparent 1px),
      linear-gradient(90deg, rgba(247,147,26,0.03) 1px, transparent 1px);
    background-size: 40px 40px;
    pointer-events: none;
    z-index: 0;
  }

  .container { max-width: 1200px; margin: 0 auto; padding: 24px 16px; position: relative; z-index: 1; }

  /* Header */
  header {
    display: flex; align-items: center; justify-content: space-between;
    margin-bottom: 32px;
    padding-bottom: 16px;
    border-bottom: 1px solid var(--border);
  }
  .logo {
    display: flex; align-items: center; gap: 12px;
  }
  .logo-icon {
    width: 40px; height: 40px;
    background: var(--accent);
    border-radius: 8px;
    display: flex; align-items: center; justify-content: center;
    font-size: 20px;
  }
  h1 { font-size: 1.8rem; font-weight: 700; letter-spacing: 2px; }
  h1 span { color: var(--accent); }
  .status-badge {
    font-family: 'Share Tech Mono', monospace;
    font-size: 0.75rem;
    padding: 4px 12px;
    border-radius: 20px;
    border: 1px solid var(--green);
    color: var(--green);
    animation: pulse 2s infinite;
  }
  @keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.5; }
  }
  .timestamp {
    font-family: 'Share Tech Mono', monospace;
    font-size: 0.75rem;
    color: var(--subtext);
  }

  /* KPI cards */
  .kpis {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    gap: 16px;
    margin-bottom: 32px;
  }
  .kpi {
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 20px;
    position: relative;
    overflow: hidden;
  }
  .kpi::before {
    content: '';
    position: absolute; top: 0; left: 0; right: 0;
    height: 2px;
    background: linear-gradient(90deg, transparent, var(--accent), transparent);
  }
  .kpi-label {
    font-size: 0.7rem;
    text-transform: uppercase;
    letter-spacing: 2px;
    color: var(--subtext);
    margin-bottom: 8px;
  }
  .kpi-value {
    font-size: 2rem;
    font-weight: 700;
    line-height: 1;
  }
  .kpi-value.accent  { color: var(--accent); }
  .kpi-value.green   { color: var(--green); }
  .kpi-value.red     { color: var(--red); }
  .kpi-value.neutral { color: var(--text); }
  .kpi-sub {
    font-size: 0.75rem;
    color: var(--subtext);
    margin-top: 6px;
    font-family: 'Share Tech Mono', monospace;
  }

  /* Panels */
  .panels { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom: 20px; }
  @media (max-width: 768px) { .panels { grid-template-columns: 1fr; } }

  .panel {
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 12px;
    overflow: hidden;
  }
  .panel-header {
    padding: 14px 20px;
    border-bottom: 1px solid var(--border);
    font-size: 0.75rem;
    text-transform: uppercase;
    letter-spacing: 2px;
    color: var(--subtext);
    display: flex; align-items: center; gap: 8px;
  }
  .panel-header .dot {
    width: 6px; height: 6px; border-radius: 50%;
    background: var(--accent);
  }

  /* Table */
  table { width: 100%; border-collapse: collapse; font-size: 0.85rem; }
  th {
    padding: 10px 16px;
    text-align: left;
    font-size: 0.65rem;
    text-transform: uppercase;
    letter-spacing: 1.5px;
    color: var(--subtext);
    border-bottom: 1px solid var(--border);
  }
  td {
    padding: 10px 16px;
    border-bottom: 1px solid rgba(26,35,50,0.5);
    font-family: 'Share Tech Mono', monospace;
    font-size: 0.8rem;
  }
  tr:last-child td { border-bottom: none; }
  tr:hover td { background: rgba(247,147,26,0.04); }

  .badge {
    display: inline-block;
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 0.7rem;
    font-weight: 600;
  }
  .badge-green  { background: rgba(0,229,160,0.15); color: var(--green); }
  .badge-red    { background: rgba(255,68,102,0.15); color: var(--red); }
  .badge-orange { background: rgba(247,147,26,0.15); color: var(--accent); }
  .badge-gray   { background: rgba(139,148,158,0.15); color: var(--subtext); }

  /* Log panel */
  .log-panel {
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 12px;
    overflow: hidden;
    margin-bottom: 20px;
  }
  .log-content {
    padding: 16px 20px;
    max-height: 260px;
    overflow-y: auto;
    font-family: 'Share Tech Mono', monospace;
    font-size: 0.75rem;
    line-height: 1.8;
    color: var(--subtext);
  }
  .log-content .log-warn  { color: #f9a825; }
  .log-content .log-señal { color: var(--accent); font-weight: 600; }
  .log-content .log-ok    { color: var(--green); }
  .log-content .log-err   { color: var(--red); }

  /* No data */
  .empty {
    padding: 40px;
    text-align: center;
    color: var(--subtext);
    font-size: 0.85rem;
  }

  /* Equity chart */
  #equity-chart { width: 100%; height: 200px; }

  footer {
    text-align: center;
    padding: 24px 0 8px;
    font-size: 0.7rem;
    color: var(--muted);
    font-family: 'Share Tech Mono', monospace;
  }
</style>
</head>
<body>
<div class="container">

  <header>
    <div class="logo">
      <div class="logo-icon">₿</div>
      <div>
        <h1>CINAX <span>BTC</span></h1>
        <div class="timestamp" id="ts">Actualizando...</div>
      </div>
    </div>
    <div>
      <div class="status-badge">● LIVE PAPER</div>
    </div>
  </header>

  <!-- KPIs -->
  <div class="kpis" id="kpis">
    <div class="kpi">
      <div class="kpi-label">Win Rate</div>
      <div class="kpi-value accent" id="kpi-wr">—</div>
      <div class="kpi-sub" id="kpi-wr-sub">trades cerrados</div>
    </div>
    <div class="kpi">
      <div class="kpi-label">Profit Factor</div>
      <div class="kpi-value accent" id="kpi-pf">—</div>
      <div class="kpi-sub">ganadores / perdedores</div>
    </div>
    <div class="kpi">
      <div class="kpi-label">Retorno Acumulado</div>
      <div class="kpi-value" id="kpi-ret">—</div>
      <div class="kpi-sub">suma lineal</div>
    </div>
    <div class="kpi">
      <div class="kpi-label">Posiciones Abiertas</div>
      <div class="kpi-value neutral" id="kpi-open">—</div>
      <div class="kpi-sub">en progreso</div>
    </div>
    <div class="kpi">
      <div class="kpi-label">Mejor Trade</div>
      <div class="kpi-value green" id="kpi-best">—</div>
      <div class="kpi-sub">retorno máximo</div>
    </div>
    <div class="kpi">
      <div class="kpi-label">Peor Trade</div>
      <div class="kpi-value red" id="kpi-worst">—</div>
      <div class="kpi-sub">retorno mínimo</div>
    </div>
  </div>

  <!-- Posiciones abiertas + cerradas -->
  <div class="panels">
    <div class="panel">
      <div class="panel-header"><div class="dot"></div> Posiciones Abiertas</div>
      <div id="abiertas-body">
        <div class="empty">Sin posiciones abiertas</div>
      </div>
    </div>
    <div class="panel">
      <div class="panel-header"><div class="dot"></div> Últimas Cerradas</div>
      <div id="cerradas-body">
        <div class="empty">Sin trades cerrados aún</div>
      </div>
    </div>
  </div>

  <!-- Equidad simple -->
  <div class="panel" style="margin-bottom:20px;">
    <div class="panel-header"><div class="dot"></div> Equidad Acumulada (lineal)</div>
    <div style="padding:16px;">
      <canvas id="equity-chart"></canvas>
    </div>
  </div>

  <!-- Log -->
  <div class="log-panel">
    <div class="panel-header"><div class="dot"></div> Log del Sistema</div>
    <div class="log-content" id="log-content">Cargando...</div>
  </div>

  <footer>CINAX BTC v2 · Paper Trading · Auto-refresh 60s</footer>
</div>

<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.0/chart.umd.min.js"></script>
<script>
let equityChart = null;

function fmt(n, dec=2) { return n !== null && n !== undefined ? parseFloat(n).toFixed(dec) : '—'; }
function pct(n)        { const v = parseFloat(n)*100; return (v >= 0 ? '+' : '') + v.toFixed(2) + '%'; }

async function refresh() {
  try {
    const r    = await fetch('/api/data');
    const data = await r.json();

    document.getElementById('ts').textContent = 'Actualizado: ' + new Date().toLocaleTimeString('es-CL');

    // KPIs
    const s = data.stats;
    const retEl = document.getElementById('kpi-ret');
    const retVal = s.retorno_acum !== null ? parseFloat(s.retorno_acum)*100 : null;
    document.getElementById('kpi-wr').textContent    = s.win_rate !== null ? (parseFloat(s.win_rate)*100).toFixed(1)+'%' : '—';
    document.getElementById('kpi-wr-sub').textContent = `${s.n_cerradas || 0} trades cerrados`;
    document.getElementById('kpi-pf').textContent    = s.profit_factor !== null ? fmt(s.profit_factor) : '—';
    retEl.textContent = retVal !== null ? (retVal >= 0 ? '+' : '') + retVal.toFixed(2) + '%' : '—';
    retEl.className   = 'kpi-value ' + (retVal === null ? 'neutral' : retVal >= 0 ? 'green' : 'red');
    document.getElementById('kpi-open').textContent  = s.n_abiertas ?? '—';
    document.getElementById('kpi-best').textContent  = s.mejor !== null ? pct(s.mejor) : '—';
    document.getElementById('kpi-worst').textContent = s.peor  !== null ? pct(s.peor)  : '—';

    // Abiertas
    const ab = data.abiertas;
    const abDiv = document.getElementById('abiertas-body');
    if (!ab || ab.length === 0) {
      abDiv.innerHTML = '<div class="empty">Sin posiciones abiertas</div>';
    } else {
      let rows = ab.map(p => {
        const ret = ((data.btc_price / p.entry_price) - 1) * 100;
        const cls = ret >= 0 ? 'green' : 'red';
        return `<tr>
          <td>${p.entry_date}</td>
          <td>${parseFloat(p.entry_price).toLocaleString()}</td>
          <td>${parseFloat(p.tp_price).toLocaleString()}</td>
          <td>${parseFloat(p.sl_price).toLocaleString()}</td>
          <td style="color:var(--${cls})">${ret >= 0 ? '+' : ''}${ret.toFixed(2)}%</td>
        </tr>`;
      }).join('');
      abDiv.innerHTML = `<table><thead><tr>
        <th>Entry</th><th>Precio</th><th>TP</th><th>SL</th><th>Ret.</th>
      </tr></thead><tbody>${rows}</tbody></table>`;
    }

    // Cerradas
    const ce = data.cerradas;
    const ceDiv = document.getElementById('cerradas-body');
    if (!ce || ce.length === 0) {
      ceDiv.innerHTML = '<div class="empty">Sin trades cerrados aún</div>';
    } else {
      let rows = ce.slice(-10).reverse().map(p => {
        const ret = parseFloat(p.retorno)*100;
        const cls   = ret >= 0 ? 'badge-green' : 'badge-red';
        const motivo = p.motivo_salida || '';
        let mCls = 'badge-gray';
        if (motivo.includes('TP')) mCls = 'badge-green';
        else if (motivo.includes('SL')) mCls = 'badge-red';
        else if (motivo.includes('Time')) mCls = 'badge-orange';
        return `<tr>
          <td>${String(p.entry_date).slice(0,16)}</td>
          <td><span class="badge ${cls}">${ret >= 0 ? '+' : ''}${ret.toFixed(2)}%</span></td>
          <td><span class="badge ${mCls}">${motivo}</span></td>
        </tr>`;
      }).join('');
      ceDiv.innerHTML = `<table><thead><tr>
        <th>Entry</th><th>Retorno</th><th>Salida</th>
      </tr></thead><tbody>${rows}</tbody></table>`;
    }

    // Equity chart
    if (ce && ce.length > 0) {
      const labels = ce.map((_, i) => `T${i+1}`);
      const equity = [];
      let acc = 0;
      ce.forEach(p => { acc += parseFloat(p.retorno)*100; equity.push(parseFloat(acc.toFixed(2))); });

      const ctx = document.getElementById('equity-chart').getContext('2d');
      if (equityChart) equityChart.destroy();
      equityChart = new Chart(ctx, {
        type: 'line',
        data: {
          labels,
          datasets: [{
            data: equity,
            borderColor: equity[equity.length-1] >= 0 ? '#00e5a0' : '#ff4466',
            backgroundColor: equity[equity.length-1] >= 0
              ? 'rgba(0,229,160,0.08)' : 'rgba(255,68,102,0.08)',
            borderWidth: 2,
            fill: true,
            tension: 0.3,
            pointRadius: 3,
            pointBackgroundColor: '#f7931a',
          }]
        },
        options: {
          animation: false,
          plugins: { legend: { display: false }, tooltip: { callbacks: {
            label: ctx => `${ctx.parsed.y >= 0 ? '+' : ''}${ctx.parsed.y.toFixed(2)}%`
          }}},
          scales: {
            x: { display: false },
            y: {
              grid: { color: 'rgba(26,35,50,0.8)' },
              ticks: { color: '#8b949e', font: { family: 'Share Tech Mono', size: 11 },
                       callback: v => (v >= 0 ? '+' : '') + v + '%' }
            }
          }
        }
      });
    }

    // Log
    const logDiv = document.getElementById('log-content');
    if (data.log) {
      const lines = data.log.slice(-60).reverse().map(l => {
        let cls = '';
        if (l.includes('★')) cls = 'log-señal';
        else if (l.includes('✓') || l.includes('OK')) cls = 'log-ok';
        else if (l.includes('!') || l.includes('WARN')) cls = 'log-warn';
        else if (l.includes('✗') || l.includes('ERR')) cls = 'log-err';
        return `<div class="${cls}">${l}</div>`;
      }).join('');
      logDiv.innerHTML = lines;
    }

  } catch (e) {
    console.error('Refresh error:', e);
  }
}

refresh();
setInterval(refresh, 60000);
</script>
</body>
</html>
"""

# ══════════════════════════════════════════════════════════════
# API
# ══════════════════════════════════════════════════════════════

def leer_posiciones():
    if not os.path.exists(POSICIONES_CSV):
        return pd.DataFrame()
    try:
        return pd.read_csv(POSICIONES_CSV)
    except Exception:
        return pd.DataFrame()


def leer_log(n_lineas=200):
    if not os.path.exists(LOG_FILE):
        return []
    try:
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()
        return [l.rstrip() for l in lines[-n_lineas:]]
    except Exception:
        return []


@app.route("/")
def index():
    return render_template_string(HTML)


@app.route("/api/data")
def api_data():
    df_pos = leer_posiciones()

    stats = {
        "win_rate": None, "profit_factor": None,
        "retorno_acum": None, "n_cerradas": 0,
        "n_abiertas": 0, "mejor": None, "peor": None,
    }

    abiertas_list  = []
    cerradas_list  = []

    if not df_pos.empty:
        cerradas = df_pos[df_pos["estado"] == "CERRADA"]
        abiertas = df_pos[df_pos["estado"] == "ABIERTA"]

        stats["n_abiertas"] = len(abiertas)
        stats["n_cerradas"] = len(cerradas)

        if len(cerradas) > 0:
            rets = cerradas["retorno"].astype(float)
            stats["win_rate"]      = float((rets > 0).mean())
            ganancias              = rets[rets > 0].sum()
            perdidas               = abs(rets[rets < 0].sum())
            stats["profit_factor"] = float(ganancias / (perdidas + 1e-8))
            stats["retorno_acum"]  = float(rets.sum())
            stats["mejor"]         = float(rets.max())
            stats["peor"]          = float(rets.min())
            cerradas_list          = cerradas.to_dict(orient="records")

        if len(abiertas) > 0:
            abiertas_list = abiertas.to_dict(orient="records")

    # Precio BTC aproximado desde última señal o última posición
    btc_price = 0.0
    if os.path.exists(SEÑALES_CSV):
        try:
            df_s = pd.read_csv(SEÑALES_CSV)
            if not df_s.empty:
                btc_price = float(df_s["precio"].iloc[-1])
        except Exception:
            pass

    return jsonify({
        "stats":     stats,
        "abiertas":  abiertas_list,
        "cerradas":  cerradas_list,
        "btc_price": btc_price,
        "log":       leer_log(100),
        "ts":        datetime.now().isoformat(),
    })


@app.route("/api/señales")
def api_señales():
    if not os.path.exists(SEÑALES_CSV):
        return jsonify([])
    try:
        df = pd.read_csv(SEÑALES_CSV)
        return jsonify(df.tail(100).to_dict(orient="records"))
    except Exception:
        return jsonify([])


@app.route("/health")
def health():
    return jsonify({"status": "ok", "ts": datetime.now().isoformat()})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=False)
