"""Classic SMA crossover: go long on golden cross, flat on death cross."""
from __future__ import annotations

from typing import Any, Optional

from ..indicators import sma
from ..models import Candle, Order, OrderType, Side
from ..strategy import Strategy, StrategyContext


class SmaCrossover(Strategy):
    name = "sma_crossover"

    def __init__(self, params: Optional[dict[str, Any]] = None) -> None:
        super().__init__(params)
        self.fast = int(self.params.get("fast", 20))
        self.slow = int(self.params.get("slow", 50))
        self.quantity = float(self.params.get("quantity", 0.01))
        if self.fast >= self.slow:
            raise ValueError(f"fast ({self.fast}) must be < slow ({self.slow})")

        self._prev_diff: Optional[float] = None
        self._warmup = self.slow

    def on_start(self, ctx: StrategyContext) -> None:
        self._prev_diff = None

    def on_candle(self, candle: Candle, ctx: StrategyContext) -> list[Order]:
        closes = ctx.closes
        if len(closes) < self._warmup:
            return []

        fast_val = sma(closes, self.fast)
        slow_val = sma(closes, self.slow)
        if fast_val is None or slow_val is None:
            return []

        diff = fast_val - slow_val
        orders: list[Order] = []

        if self._prev_diff is not None:
            crossed_up = self._prev_diff <= 0 < diff
            crossed_down = self._prev_diff >= 0 > diff

            if crossed_up and not ctx.has_position:
                orders.append(Order(symbol=ctx.symbol, side=Side.BUY,
                                    quantity=self.quantity, order_type=OrderType.MARKET))

            elif crossed_down and ctx.has_position:
                pos = ctx.position
                if pos is not None:
                    orders.append(Order(symbol=ctx.symbol, side=Side.SELL,
                                        quantity=pos.quantity, order_type=OrderType.MARKET))

        self._prev_diff = diff
        return orders