"""Portfolio accounting: cash, positions, PnL invariants."""
import pytest

from bot.models import ClosedTrade, Fill, Side
from bot.portfolio import Portfolio


def _fill(symbol, side, qty, price, fee=0.0):
    return Fill(order_id="t", symbol=symbol, side=side, quantity=qty, price=price, fee=fee)


def test_initial_state():
    p = Portfolio(starting_balance=1_000.0)
    assert p.cash == 1_000.0
    assert p.realized_pnl == 0.0
    assert p.net_realized_pnl == 0.0
    assert p.positions == {}


def test_buy_then_sell_realizes_gross_pnl():
    p = Portfolio(starting_balance=10_000.0)
    p.apply_fill(_fill("BTC/USDT", Side.BUY, 1.0, 100.0))
    p.apply_fill(_fill("BTC/USDT", Side.SELL, 1.0, 110.0))
    assert p.realized_pnl == pytest.approx(10.0)
    assert p.closed_trades[0].pnl == pytest.approx(10.0)


def test_fees_tracked_separately():
    p = Portfolio(starting_balance=10_000.0)
    p.apply_fill(_fill("BTC/USDT", Side.BUY, 1.0, 100.0, fee=0.1))
    p.apply_fill(_fill("BTC/USDT", Side.SELL, 1.0, 110.0, fee=0.1))
    assert p.total_fees == pytest.approx(0.2)
    assert p.net_realized_pnl == pytest.approx(10.0 - 0.2)


def test_cash_invariant_holds():
    p = Portfolio(starting_balance=10_000.0)
    p.apply_fill(_fill("BTC/USDT", Side.BUY, 0.5, 200.0, fee=0.1))
    p.apply_fill(_fill("BTC/USDT", Side.SELL, 0.5, 210.0, fee=0.105))
    invariant = p.cash - p.starting_balance + p.total_fees
    assert invariant == pytest.approx(p.realized_pnl)


def test_adding_to_position_averages_entry():
    p = Portfolio(starting_balance=10_000.0)
    p.apply_fill(_fill("BTC/USDT", Side.BUY, 1.0, 100.0))
    p.apply_fill(_fill("BTC/USDT", Side.BUY, 1.0, 120.0))
    pos = p.position_for("BTC/USDT")
    assert pos is not None
    assert pos.quantity == pytest.approx(2.0)
    assert pos.entry_price == pytest.approx(110.0)


def test_partial_close_keeps_remainder():
    p = Portfolio(starting_balance=10_000.0)
    p.apply_fill(_fill("BTC/USDT", Side.BUY, 2.0, 100.0))
    p.apply_fill(_fill("BTC/USDT", Side.SELL, 1.0, 110.0))
    pos = p.position_for("BTC/USDT")
    assert pos is not None
    assert pos.quantity == pytest.approx(1.0)
    assert p.realized_pnl == pytest.approx(10.0)


def test_flip_creates_opposite_position():
    p = Portfolio(starting_balance=10_000.0)
    p.apply_fill(_fill("BTC/USDT", Side.BUY, 1.0, 100.0))
    p.apply_fill(_fill("BTC/USDT", Side.SELL, 2.0, 110.0))
    pos = p.position_for("BTC/USDT")
    assert pos is not None
    assert pos.side is Side.SELL
    assert pos.quantity == pytest.approx(1.0)
    assert pos.entry_price == pytest.approx(110.0)
    assert p.realized_pnl == pytest.approx(10.0)


def test_equity_long_position():
    p = Portfolio(starting_balance=10_000.0)
    p.apply_fill(_fill("BTC/USDT", Side.BUY, 1.0, 100.0))
    eq = p.equity({"BTC/USDT": 120.0})
    assert eq == pytest.approx(10_020.0)  # 9900 cash + 120 value


def test_equity_short_position():
    p = Portfolio(starting_balance=10_000.0)
    p.apply_fill(_fill("BTC/USDT", Side.SELL, 1.0, 100.0))
    eq = p.equity({"BTC/USDT": 90.0})
    assert eq == pytest.approx(10_010.0)  # 10100 cash - 90 liability