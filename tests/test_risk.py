"""RiskManager: SL/TP attachment, size cap, halt logic."""
import pytest

from bot.models import Fill, Side
from bot.risk import RiskLimits, RiskManager

from .conftest import make_candle


def _buy_fill(symbol, qty, price, fee=0.0):
    return Fill(order_id="x", symbol=symbol, side=Side.BUY, quantity=qty, price=price, fee=fee)


def test_on_fill_attaches_sl_and_tp_for_long(ctx):
    risk = RiskManager(RiskLimits(stop_loss_pct=0.02, take_profit_pct=0.04))
    risk.on_start(ctx)

    fill = _buy_fill(ctx.symbol, 1.0, 30_000.0)
    ctx.portfolio.apply_fill(fill)
    risk.on_fill(fill, ctx)

    pos = ctx.portfolio.position_for(ctx.symbol)
    assert pos is not None
    assert pos.stop_loss == pytest.approx(30_000.0 * 0.98)
    assert pos.take_profit == pytest.approx(30_000.0 * 1.04)


def test_stop_loss_triggers_forced_exit(ctx):
    risk = RiskManager(RiskLimits(stop_loss_pct=0.02, take_profit_pct=None))
    risk.on_start(ctx)
    ctx.exchange.update_price(ctx.symbol, 30_000.0)
    ctx.buffer.append(make_candle(30_000.0, ctx.now))

    fill = _buy_fill(ctx.symbol, 1.0, 30_000.0)
    ctx.portfolio.apply_fill(fill)
    risk.on_fill(fill, ctx)

    # candle low dips below 29,400 -> SL should fire
    candle = make_candle(29_300.0, ctx.now, spread=200.0)  # low=29,100
    ctx.exchange.update_price(ctx.symbol, 29_300.0)
    orders = risk.on_candle(candle, ctx)

    assert len(orders) == 1
    assert orders[0].side is Side.SELL
    assert orders[0].trigger_price == pytest.approx(29_400.0)


def test_take_profit_triggers_forced_exit(ctx):
    risk = RiskManager(RiskLimits(stop_loss_pct=None, take_profit_pct=0.04))
    risk.on_start(ctx)
    ctx.exchange.update_price(ctx.symbol, 30_000.0)
    ctx.buffer.append(make_candle(30_000.0, ctx.now))

    fill = _buy_fill(ctx.symbol, 1.0, 30_000.0)
    ctx.portfolio.apply_fill(fill)
    risk.on_fill(fill, ctx)

    candle = make_candle(31_500.0, ctx.now, spread=300.0)  # high=31,800
    ctx.exchange.update_price(ctx.symbol, 31_500.0)
    orders = risk.on_candle(candle, ctx)

    assert len(orders) == 1
    assert orders[0].side is Side.SELL
    assert orders[0].trigger_price == pytest.approx(31_200.0)


def test_check_order_resizes_oversized_buy(ctx):
    risk = RiskManager(RiskLimits(max_position_pct=0.10))
    risk.on_start(ctx)
    # equity = 10,000; last_price = 30,000; max notional = 1,000
    order = __import__("bot.models", fromlist=["Order"]).Order(
        symbol=ctx.symbol, side=Side.BUY, quantity=1.0,
    )
    result = risk.check_order(order, ctx)
    assert result is not None
    assert result.quantity == pytest.approx(1_000.0 / 30_000.0)


def test_check_order_rejects_when_halted(ctx):
    risk = RiskManager(RiskLimits())
    risk.on_start(ctx)
    risk.halted = True
    order = __import__("bot.models", fromlist=["Order"]).Order(
        symbol=ctx.symbol, side=Side.BUY, quantity=0.001,
    )
    assert risk.check_order(order, ctx) is None
    assert risk.rejection_count == 1


def test_daily_halt_triggers_on_equity_drop(ctx):
    risk = RiskManager(RiskLimits(max_daily_loss_pct=0.05, stop_loss_pct=None, take_profit_pct=None))
    risk.on_start(ctx)

    # first candle establishes day_start_equity
    c1 = make_candle(100.0, ctx.now)
    ctx.exchange.update_price(ctx.symbol, 100.0)
    risk.on_candle(c1, ctx)
    assert risk.halted is False

    # drop cash by 10% and feed another candle
    ctx.portfolio.cash = 9_000.0
    c2 = make_candle(100.0, ctx.now)
    risk.on_candle(c2, ctx)

    assert risk.halted is True
    assert risk.halt_count == 1