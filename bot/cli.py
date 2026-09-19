"""Console entry point: `bot-run` (equivalent to `python main.py`)."""
from __future__ import annotations

import argparse
import logging
import sys

from .config import load_config
from .engine import Engine
from .exchanges import CcxtExchange, make_exchange
from .portfolio import Portfolio
from .risk import RiskLimits, RiskManager
from .safety import KillSwitch, preflight_live, summarize_balances
from .strategies import make


def banner(title: str) -> None:
    print(f"\n=== {title} ===")


def build_risk(cfg) -> RiskManager:
    return RiskManager(RiskLimits(
        max_position_pct=cfg.risk.max_position_pct,
        max_daily_loss_pct=cfg.risk.max_daily_loss_pct,
        max_open_positions=cfg.risk.max_open_positions,
        stop_loss_pct=cfg.risk.stop_loss_pct,
        take_profit_pct=cfg.risk.take_profit_pct,
    ))


def _ticks_label(ticks: int) -> str:
    return "forever" if ticks <= 0 else f"{ticks} ticks"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="bot-run",
        description="Run the trading bot (paper by default).",
    )
    parser.add_argument("--config", default="config.yaml",
                        help="path to config.yaml (default: ./config.yaml)")
    parser.add_argument("--live", action="store_true",
                        help="use live mode (needs API keys)")
    parser.add_argument("--dry-run", action="store_true",
                        help="log orders without submitting (live mode only)")
    parser.add_argument("--ticks", type=int, default=20,
                        help="number of ticks to run; 0 = forever (default: 20)")
    parser.add_argument("--poll", type=int, default=5,
                        help="seconds between ticks (default: 5)")
    parser.add_argument("--heartbeat", type=int, default=60,
                        help="seconds between heartbeat logs (default: 60)")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
    )

    cfg = load_config(args.config)
    mode = "live" if args.live else "paper"
    dry_run = args.dry_run and mode == "live"

    banner(f"Booting engine (mode={mode}{', dry-run' if dry_run else ''})")
    print(f"  symbol    : {cfg.market.symbol}")
    print(f"  timeframe : {cfg.market.timeframe}")
    print(f"  testnet   : {cfg.exchange.testnet}")

    # 1. exchange (paper or live)
    exchange = make_exchange(cfg, force_mode=mode, dry_run=dry_run)

    # 2. live data source (always ccxt, read-only for candles)
    source = CcxtExchange(
        name=cfg.exchange.name,
        symbol=cfg.market.symbol,
        timeframe=cfg.market.timeframe,
        api_key=cfg.exchange.api_key,
        api_secret=cfg.exchange.api_secret,
        testnet=cfg.exchange.testnet,
    )

    # 3. preflight if live and not dry-run
    if mode == "live" and not dry_run:
        banner("Preflight")
        ok, msg = preflight_live(exchange, cfg.market.symbol, min_balance=10.0)
        print(f"  preflight: {msg}")
        if not ok:
            print("  refusing to start. fix the issue above and retry.")
            return 2
        bal = summarize_balances(exchange)
        if bal:
            print(f"  free {bal['quote']}: {bal['free']:.4f}")

    # 4. strategy + portfolio + risk
    strategy = make(cfg.bot.strategy, {"fast": 10, "slow": 30, "quantity": 0.005})
    portfolio = Portfolio(starting_balance=cfg.risk.starting_balance)
    risk = build_risk(cfg)

    # 5. engine
    engine = Engine(
        symbol=cfg.market.symbol,
        strategy=strategy,
        exchange=exchange,
        portfolio=portfolio,
        risk=risk,
        poll_seconds=args.poll,
        source=source,
        kill_switch=KillSwitch("KILL"),
        heartbeat_seconds=args.heartbeat,
    )

    # 6. warmup with recent candles
    warmup = source.fetch_ohlcv(limit=200)
    engine.warmup(warmup)
    print(f"  warmed up with {len(warmup)} candles")

    # 7. run (ticks <= 0 means run forever)
    banner(f"Running for {_ticks_label(args.ticks)} (poll={args.poll}s)")
    print("  kill switch: create a file named 'KILL' to halt")
    max_iter = args.ticks if args.ticks > 0 else None
    engine.run(max_iterations=max_iter)

    # 8. report
    banner("Final state")
    last_price = source.get_last_price(cfg.market.symbol) or 0.0
    print(portfolio.snapshot({cfg.market.symbol: last_price}))
    for t in portfolio.closed_trades:
        print(
            f"  {t.side.value.upper()} qty={t.quantity:.6f} "
            f"{t.entry_price:.2f} -> {t.exit_price:.2f} "
            f"pnl={t.pnl:+.4f}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())