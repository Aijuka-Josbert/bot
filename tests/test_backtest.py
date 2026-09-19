"""End-to-end backtest smoke tests."""
import pytest

from bot.backtest import Backtester
from bot.data import generate_synthetic
from bot.risk import RiskLimits, RiskManager
from bot.strategies import make


def test_backtest_smoke():
    candles = generate_synthetic(n=500, start_price=30_000.0, volatility=0.004, seed=7)
    strat = make("sma_crossover", {"fast": 5, "slow": 15, "quantity": 0.01})
    bt = Backtester(starting_balance=10_000.0)
    result = bt.run(candles, strat, symbol="BTC/USDT")

    assert result.candles_processed == 500
    assert result.error_count == 0
    assert len(result.equity_curve) == 500
    assert len(result.timestamps) == 500


def test_fills_match_closed_trades():
    candles = generate_synthetic(n=500, start_price=30_000.0, volatility=0.004, seed=7)
    strat = make("sma_crossover", {"fast": 5, "slow": 15, "quantity": 0.01})
    bt = Backtester(starting_balance=10_000.0)
    result = bt.run(candles, strat, symbol="BTC/USDT")

    n_closed = len(result.closed_trades)
    # each closed trade consumes exactly one entry + one exit fill;
    # one extra fill is possible if a position is open at the end
    assert len(result.fills) in (2 * n_closed, 2 * n_closed + 1)


def test_backtest_with_risk_produces_meta_metrics():
    candles = generate_synthetic(n=500, start_price=30_000.0, volatility=0.004, seed=7)
    strat = make("sma_crossover", {"fast": 5, "slow": 15, "quantity": 0.5})
    risk = RiskManager(RiskLimits(
        max_position_pct=0.05,
        max_daily_loss_pct=0.02,
        stop_loss_pct=0.01,
        take_profit_pct=0.02,
    ))
    bt = Backtester(starting_balance=10_000.0, risk=risk)
    result = bt.run(candles, strat, symbol="BTC/USDT")

    assert "rejected_orders" in result.metrics
    assert "halt_events" in result.metrics
    assert result.error_count == 0


def test_backtest_rejects_empty_candles():
    bt = Backtester(starting_balance=10_000.0)
    strat = make("sma_crossover", {"fast": 2, "slow": 3, "quantity": 1.0})
    with pytest.raises(ValueError):
        bt.run([], strat, symbol="BTC/USDT")