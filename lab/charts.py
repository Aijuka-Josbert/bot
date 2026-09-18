"""Optional matplotlib charts for lab runs. No-op if matplotlib is missing."""
from __future__ import annotations

import logging
from pathlib import Path

from .runner import LabRun, StrategyRun

logger = logging.getLogger(__name__)

try:
    import matplotlib
    matplotlib.use("Agg")  # headless — no display required
    import matplotlib.pyplot as plt
    HAVE_MPL = True
except Exception:
    HAVE_MPL = False


def _draw_equity(ax, sr: StrategyRun, starting_balance: float) -> None:
    eq = sr.result.equity_curve
    ts = sr.result.timestamps
    if not eq or not ts:
        return
    ax.plot(ts, eq, label=sr.name, linewidth=1.2)
    ax.axhline(starting_balance, color="gray", linewidth=0.6, linestyle="--")
    ax.set_ylabel("Equity")
    ax.grid(True, alpha=0.3)


def _draw_drawdown(ax, sr: StrategyRun) -> None:
    eq = sr.result.equity_curve
    ts = sr.result.timestamps
    if not eq:
        return
    peak = eq[0]
    dd_pct = []
    for v in eq:
        peak = max(peak, v)
        dd_pct.append(0.0 if peak <= 0 else (v - peak) / peak * 100.0)
    ax.fill_between(ts, dd_pct, 0, color="red", alpha=0.3)
    ax.set_ylabel("Drawdown %")
    ax.grid(True, alpha=0.3)


def _draw_trades(ax, sr: StrategyRun) -> None:
    """Mark BUY/SELL fills on top of the price series derived from the equity curve."""
    fills = sr.result.fills
    if not fills:
        return
    buys_x = [f.timestamp for f in fills if f.side.value == "buy"]
    buys_y = [f.price for f in fills if f.side.value == "buy"]
    sells_x = [f.timestamp for f in fills if f.side.value == "sell"]
    sells_y = [f.price for f in fills if f.side.value == "sell"]
    ax.scatter(buys_x, buys_y, marker="^", color="green", s=25, label="buy")
    ax.scatter(sells_x, sells_y, marker="v", color="red", s=25, label="sell")
    ax.set_ylabel("Fill price")
    ax.legend(loc="best", fontsize=8)
    ax.grid(True, alpha=0.3)


def _save_strategy_chart(run: LabRun, sr: StrategyRun, out_dir: Path) -> Path:
    fig, axes = plt.subplots(3, 1, figsize=(11, 8), sharex=True)
    _draw_equity(axes[0], sr, run.starting_balance)
    _draw_drawdown(axes[1], sr)
    _draw_trades(axes[2], sr)

    m = sr.result.metrics
    title = (
        f"{run.name} / {sr.name}   "
        f"return={m.get('total_return_pct', 0):+.2f}%   "
        f"trades={int(m.get('trades', 0))}   "
        f"maxDD={m.get('max_drawdown_pct', 0):.2f}%   "
        f"sharpe={m.get('sharpe', 0):+.2f}"
    )
    fig.suptitle(title, fontsize=10)
    fig.tight_layout()

    path = out_dir / f"chart_{sr.name}.png"
    fig.savefig(path, dpi=110)
    plt.close(fig)
    return path


def _save_overview_chart(run: LabRun, out_dir: Path) -> Path:
    """All equity curves on one plot for the fastest visual comparison."""
    fig, ax = plt.subplots(figsize=(11, 5))
    for sr in run.runs:
        eq = sr.result.equity_curve
        ts = sr.result.timestamps
        if not eq or not ts:
            continue
        ax.plot(ts, eq, label=sr.name, linewidth=1.2)
    ax.axhline(run.starting_balance, color="gray", linewidth=0.6, linestyle="--")
    ax.set_title(f"{run.name} — equity curves")
    ax.set_ylabel("Equity")
    ax.grid(True, alpha=0.3)
    ax.legend(loc="best", fontsize=8)
    fig.tight_layout()

    path = out_dir / "overview_equity.png"
    fig.savefig(path, dpi=110)
    plt.close(fig)
    return path


def generate_charts(run: LabRun, out_dir: Path) -> list[Path]:
    """
    Generate all charts for a lab run. Returns list of written paths.
    Returns [] if matplotlib isn't installed.
    """
    if not HAVE_MPL:
        logger.warning("matplotlib not installed; skipping charts")
        return []

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    written: list[Path] = []
    for sr in run.runs:
        written.append(_save_strategy_chart(run, sr, out_dir))
    written.append(_save_overview_chart(run, out_dir))
    return written