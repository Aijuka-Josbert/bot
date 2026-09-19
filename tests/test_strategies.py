"""Strategies emit the right orders on known price series."""
from bot.models import Position, Side
from bot.strategies import make

from .conftest import make_candle


def _feed(strategy, ctx, prices):
    orders = []
    for p in prices:
        c = make_candle(p, ctx.now)
        ctx.buffer.append(c)
        ctx.exchange.update_price(ctx.symbol, p)
        ctx.last_price = p
        orders.extend(strategy.on_candle(c, ctx))
    return orders


def test_sma_crossover_buys_on_golden_cross(ctx):
    strat = make("sma_crossover", {"fast": 2, "slow": 3, "quantity": 1.0})
    strat.on_start(ctx)
    orders = _feed(strat, ctx, [10, 9, 8, 7, 8, 9, 10, 9, 8])
    buys = [o for o in orders if o.side is Side.BUY]
    assert len(buys) == 1


def test_sma_crossover_sells_on_death_cross_when_holding(ctx):
    strat = make("sma_crossover", {"fast": 2, "slow": 3, "quantity": 1.0})
    strat.on_start(ctx)
    # pre-seed a position so ctx.has_position is True
    ctx.portfolio.positions[ctx.symbol] = Position(
        symbol=ctx.symbol, side=Side.BUY, quantity=1.0, entry_price=10.0,
    )
    orders = _feed(strat, ctx, [10, 9, 8, 7, 8, 9, 10, 9, 8])
    sells = [o for o in orders if o.side is Side.SELL]
    assert len(sells) == 1


def test_sma_crossover_does_nothing_before_warmup(ctx):
    strat = make("sma_crossover", {"fast": 2, "slow": 5, "quantity": 1.0})
    strat.on_start(ctx)
    orders = _feed(strat, ctx, [10, 11, 12, 13])
    assert orders == []


def test_rsi_mean_reversion_buys_when_oversold(ctx):
    strat = make("rsi_mean_reversion", {"period": 3, "oversold": 30, "overbought": 70,
                                        "quantity": 1.0})
    strat.on_start(ctx)
    # strictly decreasing prices -> RSI = 0
    orders = _feed(strat, ctx, [10, 9, 8, 7, 6, 5, 4, 3])
    buys = [o for o in orders if o.side is Side.BUY]
    assert len(buys) >= 1


def test_bollinger_breakout_buys_above_upper_band(ctx):
    strat = make("bollinger_breakout", {"period": 3, "num_std": 1.0, "quantity": 1.0})
    strat.on_start(ctx)
    # flat then a big spike -> close above upper band
    orders = _feed(strat, ctx, [10, 10, 10, 10, 20])
    buys = [o for o in orders if o.side is Side.BUY]
    assert len(buys) == 1