"""Buy oversold, sell overbought. Rides mean reversion in range-bound markets."""
from __future__ import annotations

from typing import Any, Optional

from ..indicators import rsi
from ..models import Candle, Order, OrderType, Side
from ..strategy import Strategy, StrategyContext


class RsiMeanReversion(Strategy):
    name = "rsi_mean_reversion"

    def __init__(self, params: Optional[dict[str, Any]] = None) -> None:
        super().__init__(params)
        self.period = int(self.params.get("period", 14))
        self.oversold = float(self.params.get("oversold", 30.0))
        self.overbought = float(self.params.get("overbought", 70.0))
        self.quantity = float(self.params.get("quantity", 0.05))
        if not (0 < self.oversold < self.overbought < 100):
            raise ValueError("need 0 < oversold < overbought < 100")

    def on_candle(self, candle: Candle, ctx: StrategyContext) -> list[Order]:
        closes = ctx.closes
        if len(closes) < self.period + 1:
            return []

        value = rsi(closes, self.period)
        if value is None:
            return []

        orders: list[Order] = []

        if value < self.oversold and not ctx.has_position:
            orders.append(Order(
                symbol=ctx.symbol,
                side=Side.BUY,
                quantity=self.quantity,
                order_type=OrderType.MARKET,
            ))
        elif value > self.overbought and ctx.has_position:
            pos = ctx.position
            if pos is not None:
                orders.append(Order(
                    symbol=ctx.symbol,
                    side=Side.SELL,
                    quantity=pos.quantity,
                    order_type=OrderType.MARKET,
                ))

        return orders