"""CLI entry point: python -m lab run --config labs/compare.yaml"""
from __future__ import annotations

import argparse
import sys

from .config import load_lab_config
from .report import print_leaderboard
from .runner import run_lab
from .storage import LabStore


def cmd_run(args: argparse.Namespace) -> int:
    cfg = load_lab_config(args.config)
    print(f"loading data ({cfg.data.source}) ...")
    run = run_lab(cfg, parallel=not args.sequential)
    print_leaderboard(run)

    if not args.no_save:
        store = LabStore(cfg.output.dir)
        run_dir = store.save(run)
        print(f"\n  saved -> {run_dir}")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    store = LabStore(args.dir)
    runs = store.list_runs()
    if not runs:
        print("no saved runs")
        return 0
    for r in runs:
        try:
            s = store.load_summary(r)
            best = max(
                s["strategies"],
                key=lambda x: x["metrics"].get("total_return_pct", 0.0),
            )
            print(
                f"  {r.name}  {s['name']:<24}  "
                f"best={best['name']:<14}  "
                f"return={best['metrics'].get('total_return_pct', 0):+.2f}%"
            )
        except Exception as e:
            print(f"  {r.name}  <unreadable: {e}>")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="lab", description="Virtual trading lab")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_run = sub.add_parser("run", help="run a lab experiment")
    p_run.add_argument("--config", required=True, help="path to a lab YAML")
    p_run.add_argument("--sequential", action="store_true",
                       help="disable parallel execution")
    p_run.add_argument("--no-save", action="store_true",
                       help="do not write results to disk")
    p_run.set_defaults(func=cmd_run)

    p_list = sub.add_parser("list", help="list saved lab runs")
    p_list.add_argument("--dir", default="data/lab_runs")
    p_list.set_defaults(func=cmd_list)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())