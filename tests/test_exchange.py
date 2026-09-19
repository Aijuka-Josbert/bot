"""PaperExchange: slippage direction, fee math, order rejection."""
import pytest

from bot.exchange import PaperExchange
from bot.models import Order, OrderStatus, OrderType, Side


def test_buy_slippage_is_adverse():
    ex = PaperExchange(fee_rate=0.0, slippage_bps=10)  # 0.10%
    ex.update_price("BTC/USDT", 10_000.0)
    fill = ex.submit(Order(symbol="BTC/USDT", side=Side.BUY, quantity=1.0))
    assert fill is not None
    assert fill.price == pytest.approx(10_010.0)


def test_sell_slippage_is_adverse():
    ex = PaperExchange(fee_rate=0.0, slippage_bps=10)
    ex.update_price("BTC/USDT", 10_000.0)
    fill = ex.submit(Order(symbol="BTC/USDT", side=Side.SELL, quantity=1.0))
    assert fill is not None
    assert fill.price == pytest.approx(9_990.0)


def test_fee_is_rate_times_notional():
    ex = PaperExchange(fee_rate=0.001, slippage_bps=0)
    ex.update_price("BTC/USDT", 1_000.0)
    fill = ex.submit(Order(symbol="BTC/USDT", side=Side.BUY, quantity=2.0))
    assert fill is not None
    assert fill.notional == pytest.approx(2_000.0)
    assert fill.fee == pytest.approx(2.0)


def test_order_rejected_without_price():
    ex = PaperExchange()
    fill = ex.submit(Order(symbol="UNKNOWN", side=Side.BUY, quantity=1.0))
    assert fill is None


def test_order_rejected_with_zero_quantity():
    ex = PaperExchange()
    ex.update_price("BTC/USDT", 100.0)
    fill = ex.submit(Order(symbol="BTC/USDT", side=Side.BUY, quantity=0.0))
    assert fill is None


def test_limit_buy_not_filled_above_limit():
    ex = PaperExchange(fee_rate=0.0, slippage_bps=0)
    ex.update_price("BTC/USDT", 100.0)
    order = Order(
        symbol="BTC/USDT", side=Side.BUY, quantity=1.0,
        order_type=OrderType.LIMIT, price=90.0,
    )
    fill = ex.submit(order)
    assert fill is None
    assert order.status is OrderStatus.NEW