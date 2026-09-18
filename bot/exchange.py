"""Exchange abstraction. Stage 2 ships PaperExchange only."""
from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from typing import Optional

from .models import Fill, Order, OrderStatus, OrderType, Side


class Exchange(ABC):
    """Common interface every exchange adapter implements."""

    @abstractmethod
    def update_price(self, symbol: str, price: float) -> None: ...

    @abstractmethod
    def get_last_price(self, symbol: str) -> Optional[float]: ...

    @abstractmethod
    def submit(self, order: Order) -> Optional[Fill]: ...


class PaperExchange(Exchange):
    """
    In-memory exchange simulator.

    - Market orders fill immediately at the last known price,
      adjusted by `slippage_bps` in the adverse direction.
    - Limit orders only fill if the last price crosses the limit.
    - Fees are charged as `fee_rate * notional`.
    - Prices must be pushed in via `update_price()` before submitting.
    """

    def __init__(self, fee_rate: float = 0.001, slippage_bps: int = 5) -> None:
        if fee_rate < 0:
            raise ValueError("fee_rate must be >= 0")
        if slippage_bps < 0:
            raise ValueError("slippage_bps must be >= 0")
        self.fee_rate = float(fee_rate)
        self.slippage_bps = int(slippage_bps)
        self._prices: dict[str, float] = {}
        self.fills: list[Fill] = []

    # ---- market data ----

    def update_price(self, symbol: str, price: float) -> None:
        if price <= 0:
            raise ValueError(f"price must be > 0, got {price}")
        self._prices[symbol] = float(price)

    def get_last_price(self, symbol: str) -> Optional[float]:
        return self._prices.get(symbol)

    # ---- order flow ----

    def submit(self, order: Order) -> Optional[Fill]:
        last = self._prices.get(order.symbol)
        if last is None:
            order.status = OrderStatus.REJECTED
            return None
        if order.quantity <= 0:
            order.status = OrderStatus.REJECTED
            return None

        slip = self.slippage_bps / 10_000.0
        ref_price = last * (1 + slip) if order.side is Side.BUY else last * (1 - slip)

        # Limit order crossing check
        if order.order_type is OrderType.LIMIT:
            assert order.price is not None, "limit order requires price"
            if order.side is Side.BUY and ref_price > order.price:
                return None  # would not be filled
            if order.side is Side.SELL and ref_price < order.price:
                return None
            fill_price = min(ref_price, order.price) if order.side is Side.BUY \
                else max(ref_price, order.price)
        else:
            fill_price = ref_price

        fee = fill_price * order.quantity * self.fee_rate
        order.id = order.id or str(uuid.uuid4())
        order.status = OrderStatus.FILLED

        fill = Fill(
            order_id=order.id,
            symbol=order.symbol,
            side=order.side,
            quantity=order.quantity,
            price=fill_price,
            fee=fee,
        )
        self.fills.append(fill)
        return fill