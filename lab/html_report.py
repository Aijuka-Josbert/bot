"""Self-contained HTML report per lab run. PNGs embedded as base64."""
from __future__ import annotations

import base64
import html
from pathlib import Path

from .runner import LabRun


# --- formatting helpers ---

_METRIC_ORDER = [
    ("total_return_pct", "+.2f", "%"),
    ("final_equity", ",.2f", ""),
    ("sharpe", "+.2f", ""),
    ("sortino", "+.2f", ""),
    ("max_drawdown_pct", ".2f", "%"),
    ("trades", "d", ""),
    ("win_rate_pct", ".2f", "%"),
    ("profit_factor", ".2f", ""),
    ("expectancy", "+.4f", ""),
    ("avg_win_loss_ratio", ".2f", ""),
    ("rejected_orders", "d", ""),
    ("halt_events", "d", ""),
]


def _fmt(value, spec: str) -> str:
    if value is None:
        return "-"
    if isinstance(value, float) and value != value:
        return "n/a"
    try:
        if spec == "d":
            return str(int(value))
        return format(value, spec)
    except (ValueError, TypeError):
        return str(value)


def _esc(s) -> str:
    return html.escape(str(s))


def _png_b64(path: Path) -> str | None:
    if not path.exists():
        return None
    try:
        return base64.b64encode(path.read_bytes()).decode("ascii")
    except OSError:
        return None


# --- sections ---

def _leaderboard_rows(run: LabRun) -> str:
    ranked = sorted(
        run.runs,
        key=lambda sr: sr.result.metrics.get("total_return_pct", 0.0),
        reverse=True,
    )
    rows = []
    for i, sr in enumerate(ranked, 1):
        m = sr.result.metrics
        rows.append(
            "<tr>"
            f"<td class='rank'>{i}</td>"
            f"<td class='name'>{_esc(sr.name)}</td>"
            f"<td class='cls'>{_esc(sr.spec.cls)}</td>"
            f"<td class='num'>{_fmt(m.get('trades'), 'd')}</td>"
            f"<td class='num'>{_fmt(m.get('win_rate_pct'), '.2f')}</td>"
            f"<td class='num ret'>{_fmt(m.get('total_return_pct'), '+.2f')}</td>"
            f"<td class='num'>{_fmt(m.get('sharpe'), '+.2f')}</td>"
            f"<td class='num'>{_fmt(m.get('sortino'), '+.2f')}</td>"
            f"<td class='num'>{_fmt(m.get('max_drawdown_pct'), '.2f')}</td>"
            f"<td class='num'>{_fmt(m.get('profit_factor'), '.2f')}</td>"
            f"<td class='num'>{_fmt(m.get('final_equity'), ',.2f')}</td>"
            "</tr>"
        )
    return "".join(rows)


def _metrics_grid(metrics: dict) -> str:
    cells = []
    for key, spec, suffix in _METRIC_ORDER:
        if key not in metrics:
            continue
        cells.append(
            "<div class='metric'>"
            f"<div class='metric-key'>{_esc(key)}</div>"
            f"<div class='metric-val'>{_fmt(metrics[key], spec)}{suffix}</div>"
            "</div>"
        )
    return "".join(cells)


def _params_line(params: dict) -> str:
    if not params:
        return "<em>no params</em>"
    parts = [f"<code>{_esc(k)}={_esc(v)}</code>" for k, v in params.items()]
    return " ".join(parts)


def _strategy_section(sr, run_dir: Path) -> str:
    chart_name = f"chart_{sr.name}.png"
    chart_b64 = _png_b64(run_dir / chart_name)
    chart_html = (
        f"<img class='chart' alt='{_esc(sr.name)} chart' "
        f"src='data:image/png;base64,{chart_b64}'>"
        if chart_b64
        else "<p class='muted'>no chart available</p>"
    )
    return f"""
    <section class="strategy">
      <h2>{_esc(sr.name)} <span class="muted">— {_esc(sr.spec.cls)}</span></h2>
      <p class="params">{_params_line(sr.spec.params)}</p>
      <div class="grid">{_metrics_grid(sr.result.metrics)}</div>
      {chart_html}
    </section>
    """


# --- styles / script ---

_CSS = """
:root{
  --bg:#0f1216; --panel:#171b21; --border:#262c35;
  --text:#e6e9ef; --muted:#8a95a5; --accent:#4ea1ff;
  --pos:#3ddc84; --neg:#ff5c5c;
}
*{box-sizing:border-box}
body{margin:0;padding:24px;background:var(--bg);color:var(--text);
     font:14px/1.5 -apple-system,system-ui,sans-serif}
h1,h2{font-weight:600;margin:0 0 8px}
h1{font-size:22px}
h2{font-size:16px;margin-top:32px}
.muted{color:var(--muted);font-weight:400}
.header{display:flex;justify-content:space-between;align-items:baseline;
        padding-bottom:12px;border-bottom:1px solid var(--border);margin-bottom:20px}
.header .meta{color:var(--muted);font-size:12px}
table{width:100%;border-collapse:collapse;background:var(--panel);
      border:1px solid var(--border);border-radius:6px;overflow:hidden}
th,td{padding:8px 12px;text-align:left}
th{background:#1c222a;font-weight:600;font-size:12px;color:var(--muted);
   text-transform:uppercase;letter-spacing:.04em;cursor:pointer;user-select:none}
th:hover{color:var(--text)}
td.num{text-align:right;font-variant-numeric:tabular-nums;
       font-family:ui-monospace,monospace}
td.rank{width:32px;color:var(--muted)}
td.name{font-weight:600}
td.cls{color:var(--muted);font-size:12px}
td.ret{color:var(--pos)}
tr:hover td{background:rgba(255,255,255,.03)}
.strategy{margin-top:24px}
.params{color:var(--muted);font-size:12px}
.params code{background:var(--panel);padding:2px 6px;border-radius:3px;
             border:1px solid var(--border)}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(140px,1fr));
      gap:8px;margin:12px 0 16px}
.metric{background:var(--panel);border:1px solid var(--border);
        border-radius:6px;padding:8px 10px}
.metric-key{color:var(--muted);font-size:11px;text-transform:uppercase;
            letter-spacing:.03em}
.metric-val{font-family:ui-monospace,monospace;font-size:14px;margin-top:2px}
.chart{width:100%;max-width:1100px;border:1px solid var(--border);
       border-radius:6px;display:block}
footer{margin-top:40px;color:var(--muted);font-size:12px;text-align:center}
"""

_JS = """
document.querySelectorAll('th').forEach((th, i) => {
  th.addEventListener('click', () => {
    const table = th.closest('table');
    const rows = Array.from(table.querySelectorAll('tbody tr'));
    const dir = th.dataset.dir === 'asc' ? 'desc' : 'asc';
    th.dataset.dir = dir;
    rows.sort((a, b) => {
      const av = a.children[i].innerText;
      const bv = b.children[i].innerText;
      const an = parseFloat(av.replace(/[^0-9.+-eE]/g, ''));
      const bn = parseFloat(bv.replace(/[^0-9.+-eE]/g, ''));
      if (!isNaN(an) && !isNaN(bn)) return dir === 'asc' ? an - bn : bn - an;
      return dir === 'asc' ? av.localeCompare(bv) : bv.localeCompare(av);
    });
    const tbody = table.querySelector('tbody');
    rows.forEach(r => tbody.appendChild(r));
  });
});
"""


# --- public ---

def render_html(run: LabRun, run_dir: Path, saved_at: str | None = None) -> str:
    ranked = sorted(
        run.runs,
        key=lambda sr: sr.result.metrics.get("total_return_pct", 0.0),
        reverse=True,
    )
    best = ranked[0] if ranked else None
    sections = "".join(_strategy_section(sr, run_dir) for sr in ranked)
    best_line = (
        f"<strong>{_esc(best.name)}</strong> "
        f"({_fmt(best.result.metrics.get('total_return_pct'), '+.2f')}%)"
        if best else "<em>no strategies</em>"
    )

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Lab Report — {_esc(run.name)}</title>
<style>{_CSS}</style>
</head>
<body>
  <div class="header">
    <div>
      <h1>Lab Report — {_esc(run.name)}</h1>
      <div class="meta">
        symbol <strong>{_esc(run.symbol)}</strong> ·
        candles <strong>{len(run.candles)}</strong> ·
        starting balance <strong>{run.starting_balance:,.2f}</strong>
      </div>
    </div>
    <div class="meta">saved {_esc(saved_at or '')}</div>
  </div>

  <p>Best: {best_line}</p>

  <h2>Leaderboard</h2>
  <table id="leaderboard">
    <thead>
      <tr>
        <th>#</th><th>Strategy</th><th>Class</th><th>Trades</th>
        <th>Win %</th><th>Return %</th><th>Sharpe</th><th>Sortino</th>
        <th>Max DD %</th><th>PF</th><th>Final</th>
      </tr>
    </thead>
    <tbody>
      {_leaderboard_rows(run)}
    </tbody>
  </table>

  {sections}

  <footer>Generated by <code>lab</code> · click any column header to sort</footer>

<script>{_JS}</script>
</body>
</html>
"""


def write_report(run: LabRun, run_dir: Path, saved_at: str | None = None) -> Path:
    path = Path(run_dir) / "report.html"
    path.write_text(render_html(run, run_dir, saved_at=saved_at), encoding="utf-8")
    return path