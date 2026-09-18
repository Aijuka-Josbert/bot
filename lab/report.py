"""Pretty-print a lab run and its leaderboard."""
from __future__ import annotations

from .runner import LabRun


_COLUMNS = [
    ("strategy", "name",             16, "s"),
    ("trades",   "trades",            7, "d"),
    ("win%",     "win_rate_pct",      7, ".2f"),
    ("return%",  "total_return_pct",  9, "+.2f"),
    ("sharpe",   "sharpe",            8, "+.2f"),
    ("sortino",  "sortino",           8, "+.2f"),
    ("maxDD%",   "max_drawdown_pct",  8, ".2f"),
    ("PF",       "profit_factor",     6, ".2f"),
    ("final",    "final_equity",     11, ".2f"),
]


def _fmt(value, spec: str) -> str:
    if value is None:
        return "-"
    if spec == "s":
        return str(value)
    if spec == "d":
        return str(int(value))
    try:
        return format(float(value), spec)
    except (ValueError, TypeError):
        return str(value)


def print_leaderboard(run: LabRun) -> None:
    print(f"\nLAB RUN: {run.name}")
    print(f"  symbol  : {run.symbol}")
    print(f"  candles : {len(run.candles)}")
    print(f"  start   : {run.starting_balance:,.2f}")
    print()

    header = "  ".join(f"{h:<{w}}" for h, _, w, _ in _COLUMNS)
    print("  " + header)
    print("  " + "-" * (len(header)))

    ranked = sorted(
        run.runs,
        key=lambda sr: sr.result.metrics.get("total_return_pct", 0.0),
        reverse=True,
    )

    for sr in ranked:
        row = []
        for _, key, width, spec in _COLUMNS:
            value = sr.name if key == "name" else sr.result.metrics.get(key)
            row.append(f"{_fmt(value, spec):<{width}}")
        print("  " + "  ".join(row))

    if ranked:
        best = ranked[0]
        print(
            f"\n  best: {best.name}  "
            f"return={best.result.metrics.get('total_return_pct', 0):+.2f}%  "
            f"trades={len(best.result.closed_trades)}"
        )