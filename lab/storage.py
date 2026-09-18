"""Save and load lab runs on disk."""
from __future__ import annotations

import csv
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from .charts import generate_charts
from .runner import LabRun
from .html_report import write_report


def _run_id() -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return f"{ts}-{uuid.uuid4().hex[:6]}"


def _write_equity_csv(path: Path, timestamps, equity) -> None:
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["timestamp", "equity"])
        for ts, eq in zip(timestamps, equity):
            w.writerow([ts.isoformat(), f"{eq:.6f}"])


def _write_trades_csv(path: Path, trades) -> None:
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow([
            "opened_at", "closed_at", "symbol", "side", "quantity",
            "entry_price", "exit_price", "pnl", "fees",
        ])
        for t in trades:
            w.writerow([
                t.opened_at.isoformat(), t.closed_at.isoformat(),
                t.symbol, t.side.value, f"{t.quantity:.8f}",
                f"{t.entry_price:.6f}", f"{t.exit_price:.6f}",
                f"{t.pnl:.6f}", f"{t.fees:.6f}",
            ])


class LabStore:
    def __init__(self, root: str | Path = "data/lab_runs") -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def save(self, run: LabRun, write_html: bool = True) -> Path:
        run_dir = self.root / _run_id()
        run_dir.mkdir(parents=True, exist_ok=True)

        summary = {
            "name": run.name,
            "saved_at": datetime.now(timezone.utc).isoformat(),
            "symbol": run.symbol,
            "candles": len(run.candles),
            "starting_balance": run.starting_balance,
            "strategies": [],
        }

        for sr in run.runs:
            summary["strategies"].append({
                "name": sr.name,
                "class": sr.spec.cls,
                "params": sr.spec.params,
                "metrics": sr.result.metrics,
                "fills": len(sr.result.fills),
                "closed_trades": len(sr.result.closed_trades),
                "candles_processed": sr.result.candles_processed,
                "error_count": sr.result.error_count,
            })
            _write_equity_csv(
                run_dir / f"equity_{sr.name}.csv",
                sr.result.timestamps,
                sr.result.equity_curve,
            )
            _write_trades_csv(
                run_dir / f"trades_{sr.name}.csv",
                sr.result.closed_trades,
            )

        chart_paths = generate_charts(run, run_dir)
        if chart_paths:
            summary["charts"] = [p.name for p in chart_paths]

        if write_html:
            report_path = write_report(run, run_dir, saved_at=summary["saved_at"])
            summary["report"] = report_path.name

        (run_dir / "summary.json").write_text(json.dumps(summary, indent=2))
        return run_dir

    def list_runs(self) -> list[Path]:
        return sorted([p for p in self.root.iterdir() if p.is_dir()])

    def load_summary(self, run_dir: Path) -> dict:
        return json.loads((run_dir / "summary.json").read_text())