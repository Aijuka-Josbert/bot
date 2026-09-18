"""Shared per-candle pipeline used by both the backtester and the live engine."""
from __future__ import annotations

from typing import Optional

from .exchange import Exchange
from .models import Candle, Fill, Order
from .portfolio import Portfolio
from .risk import RiskManager
from .strategy import Strategy, StrategyContext


def execute_order(
    order: Order,
    candle: Candle,
    symbol: str,
    exchange: Exchange,
    portfolio: Portfolio,
    strategy: Strategy,
    risk: Optional[RiskManager],
    ctx: StrategyContext,
) -> Optional[Fill]:
    """
    Submit one order. If the order carries a trigger_price (SL/TP/halt),
    temporarily pin the exchange price to it so the fill lands near the trigger.
    """
    override = order.trigger_price is not None
    if override:
        exchange.update_price(symbol, order.trigger_price)

    fill = exchange.submit(order)

    if override:
        exchange.update_price(symbol, candle.close)

    if fill is None:
        return None

    portfolio.apply_fill(fill)
    if risk is not None:
        risk.on_fill(fill, ctx)
    strategy.on_fill(fill, ctx)
    return fill


def process_candle(
    candle: Candle,
    symbol: str,
    ctx: StrategyContext,
    strategy: Strategy,
    exchange: Exchange,
    portfolio: Portfolio,
    risk: Optional[RiskManager],
) -> list[Fill]:
    """
    Run one closed candle through:
        1. risk-driven forced exits (SL / TP / daily halt)
        2. strategy decisions
        3. order screening + execution
    Returns all fills produced this candle.
    """
    exchange.update_price(symbol, candle.close)
    ctx.last_price = candle.close
    ctx.now = candle.timestamp

    fills: list[Fill] = []

    # 1. forced exits
    if risk is not None:
        for order in risk.on_candle(candle, ctx):
            fill = execute_order(order, candle, symbol, exchange,
                                 portfolio, strategy, risk, ctx)
            if fill is not None:
                fills.append(fill)

    # 2. strategy
    orders = strategy.on_candle(candle, ctx) or []

    # 3. screen + execute
    for order in orders:
        if risk is not None:
            order = risk.check_order(order, ctx)
            if order is None:
                continue
        fill = execute_order(order, candle, symbol, exchange,
                             portfolio, strategy, risk, ctx)
        if fill is not None:
            fills.append(fill)

    return fills