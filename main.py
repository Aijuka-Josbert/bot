"""Stage 8 demo: same strategy, with and without risk enforcement."""
from bot.backtest import Backtester
from bot.data import generate_synthetic
from bot.risk import RiskLimits, RiskManager
from bot.strategies import make


def banner(title: str) -> None:
    print(f"\n=== {title} ===")


def summarize(label: str, result) -> None:
    m = result.metrics
    print(
        f"  {label:<14}  trades={int(m['trades']):>3}  "
        f"return={m['total_return_pct']:+7.2f}%  "
        f"maxDD={m['max_drawdown_pct']:6.2f}%  "
        f"rejected={int(m.get('rejected_orders', 0)):>3}  "
        f"halts={int(m.get('halt_events', 0))}"
    )


def main() -> None:
    candles = generate_synthetic(
        n=2000, start_price=30_000.0,
        drift=0.00002, volatility=0.004,
        step_seconds=60, seed=42,
    )
    print(f"generated {len(candles)} synthetic candles")

    symbol = "BTC/USDT"

    def run(strategy_name, params, risk: RiskManager | None):
        strategy = make(strategy_name, params)
        bt = Backtester(
            starting_balance=10_000.0,
            fee_rate=0.001,
            slippage_bps=5,
            periods_per_year=525_600,
            risk=risk,
        )
        return bt.run(candles, strategy, symbol=symbol)

    base_params = {"fast": 10, "slow": 30, "quantity": 0.05}

    banner("Without risk")
    summarize("no risk", run("sma_crossover", base_params, None))

    banner("With risk")
    tight = RiskManager(RiskLimits(
        max_position_pct=0.10,
        max_daily_loss_pct=0.02,
        max_open_positions=1,
        stop_loss_pct=0.01,
        take_profit_pct=0.02,
    ))
    summarize("with risk", run("sma_crossover", base_params, tight))


if __name__ == "__main__":
    main()