"""Breakout on close above upper band; exit on close below middle band."""
from __future__ import annotations

import statistics
from typing import Any, Optional

from ..models import Candle, Order, OrderType, Side
from ..strategy import Strategy, StrategyContext


class BollingerBreakout(Strategy):
    name = "bollinger_breakout"

    def __init__(self, params: Optional[dict[str, Any]] = None) -> None:
        super().__init__(params)
        self.period = int(self.params.get("period", 20))
        self.num_std = float(self.params.get("num_std", 2.0))
        self.quantity = float(self.params.get("quantity", 0.05))
        if self.period < 2:
            raise ValueError("period must be >= 2")

    def on_candle(self, candle: Candle, ctx: StrategyContext) -> list[Order]:
        closes = ctx.closes
        if len(closes) < self.period:
            return []

        window = closes[-self.period:]
        mid = sum(window) / self.period
        sd = statistics.pstdev(window)  # population stddev, matches most charting tools
        upper = mid + self.num_std * sd
        lower = mid - self.num_std * sd

        orders: list[Order] = []

        if candle.close > upper and not ctx.has_position:
            orders.append(Order(
                symbol=ctx.symbol,
                side=Side.BUY,
                quantity=self.quantity,
                order_type=OrderType.MARKET,
            ))
        elif candle.close < mid and ctx.has_position:
            pos = ctx.position
            if pos is not None:
                orders.append(Order(
                    symbol=ctx.symbol,
                    side=Side.SELL,
                    quantity=pos.quantity,
                    order_type=OrderType.MARKET,
                ))

        # lower band is defined but unused; keeping the variable documents intent
        _ = lower

        return orders