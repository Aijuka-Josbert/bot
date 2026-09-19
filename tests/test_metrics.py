"""Metrics against hand-computed values."""
import math

import pytest

from bot.metrics import (
    compute_all,
    max_drawdown_pct,
    profit_factor,
    total_return_pct,
    win_rate,
)
from bot.models import ClosedTrade, Side


def _trade(pnl):
    return ClosedTrade(
        symbol="X", side=Side.BUY, quantity=1.0,
        entry_price=100.0, exit_price=100.0 + pnl,
        pnl=pnl, fees=0.0,
        opened_at=__import__("datetime").datetime(2026, 1, 1, tzinfo=__import__("datetime").timezone.utc),
        closed_at=__import__("datetime").datetime(2026, 1, 2, tzinfo=__import__("datetime").timezone.utc),
    )


def test_total_return_pct_positive():
    assert total_return_pct(100.0, 110.0) == pytest.approx(10.0)


def test_total_return_pct_negative():
    assert total_return_pct(100.0, 90.0) == pytest.approx(-10.0)


def test_max_drawdown_hand_computed():
    # peak 120 -> trough 90 => 25%
    equity = [100, 110, 120, 100, 90, 100]
    assert max_drawdown_pct(equity) == pytest.approx(25.0)


def test_max_drawdown_monotonic_up_is_zero():
    assert max_drawdown_pct([100, 101, 102, 103]) == 0.0


def test_win_rate():
    trades = [_trade(1.0), _trade(-0.5), _trade(2.0), _trade(-1.0)]
    assert win_rate(trades) == pytest.approx(50.0)


def test_profit_factor():
    trades = [_trade(2.0), _trade(-1.0), _trade(4.0), _trade(-1.0)]
    assert profit_factor(trades) == pytest.approx(3.0)  # 6 / 2


def test_profit_factor_no_losers_is_infinite():
    assert profit_factor([_trade(1.0)]) == math.inf


def test_compute_all_contains_expected_keys():
    trades = [_trade(1.0), _trade(-0.5)]
    equity = [100, 100.5, 101.0]
    m = compute_all(equity, trades, starting_balance=100.0, periods_per_year=365)
    for key in ("total_return_pct", "sharpe", "sortino", "max_drawdown_pct",
                "win_rate_pct", "profit_factor", "expectancy"):
        assert key in m