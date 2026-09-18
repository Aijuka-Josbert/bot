"""
Stage 5 smoke test — same run as Stage 4, now persisted to SQLite.

Flow:
   1. Build portfolio + exchange + strategy + engine (as before)
   2. Run the engine over synthetic candles
   3. Save the whole run to data/bot.db
   4. Read it back and print what was stored
"""
from datetime import datetime, timezone

from bot.config import load_config
from bot.data import synthetic_candles
from bot.engine import Engine
from bot.exchange import PaperExchange
from bot.portfolio import Portfolio
from bot.storage import Storage
from bot.strategy import SmaCrossover


def fmt_money(x: float) -> str:
    return f"{x:,.2f}"


def main() -> None:
    cfg = load_config("config.yaml")

    # ---- 1. Build the pieces ----
    portfolio = Portfolio(starting_balance=cfg.risk.starting_balance)
    exchange = PaperExchange(
        fee_rate=cfg.risk.fee_rate,
        slippage_bps=cfg.risk.slippage_bps,
    )
    strategy = SmaCrossover(fast=5, slow=15, quantity=0.05)
    print(f"strategy: {strategy}")

    engine = Engine(
        strategy=strategy,
        exchange=exchange,
        portfolio=portfolio,
        symbol=cfg.market.symbol,
        stop_loss_pct=cfg.risk.stop_loss_pct,
        take_profit_pct=cfg.risk.take_profit_pct,
        verbose=False,        # quieter this time
    )

    # ---- 2. Run ----
    candles = list(synthetic_candles(
        symbol=cfg.market.symbol,
        n=400,
        start_price=30_000.0,
        amplitude=0.10,
        period=80,
        noise=0.003,
    ))
    started = datetime.now(timezone.utc)
    result = engine.run(candles)
    finished = datetime.now(timezone.utc)

    # ---- 3. Print quick summary ----
    print(f"candles: {result.candles_processed}  fills: {len(result.fills)}  "
          f"net PnL: {fmt_money(result.net_pnl)}  ({result.return_pct:+.2%})")

    # ---- 4. Save ----
    with Storage(cfg.storage.db_path) as db:
        run_id = db.save_run(
            name="smoke_test_stage5",
            strategy=strategy,
            symbol=cfg.market.symbol,
            starting_balance=result.starting_balance,
            final_equity=result.final_equity,
            realized_pnl=result.realized_pnl,
            total_fees=result.total_fees,
            candles_processed=result.candles_processed,
            error_count=len(result.errors),
            fills=result.fills,
            equity_curve=result.equity_curve,
            closed_trades=portfolio.closed_trades,
            started_at=started,
            finished_at=finished,
        )
        print(f"\n✅ saved run #{run_id} to {cfg.storage.db_path}")
        print(f"   total runs in DB: {db.count_runs()}")

        # ---- 5. Read back ----
        print("\n=== Stored header ===")
        header = db.get_run(run_id)
        for k, v in header.items():
            print(f"  {k:20s}: {v}")

        fills = db.get_fills(run_id)
        eq = db.get_equity_curve(run_id)
        trades = db.get_closed_trades(run_id)
        print(f"\n  stored fills        : {len(fills)}")
        print(f"  stored equity points: {len(eq)}")
        print(f"  stored closed trades: {len(trades)}")

        print("\n=== First 3 stored fills ===")
        for f in fills[:3]:
            print(f"  {f}")

        print("\n=== Last stored equity point ===")
        if eq:
            print(f"  {eq[-1]}")

        print("\n=== Recent runs ===")
        for r in db.list_runs(limit=5):
            print(f"  #{r['id']:3d}  {r['name']:20s}  "
                  f"{r['strategy']:15s}  "
                  f"pnl={r['realized_pnl']:+10.2f}  "
                  f"candles={r['candles_processed']}")


if __name__ == "__main__":
    main()