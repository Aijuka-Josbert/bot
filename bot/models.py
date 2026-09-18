"""Core domain models — plain data, no behaviour beyond helpers."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


class Side(str, Enum):
    BUY = "buy"
    SELL = "sell"

    @property
    def opposite(self) -> "Side":
        return Side.SELL if self is Side.BUY else Side.BUY


class OrderType(str, Enum):
    MARKET = "market"
    LIMIT = "limit"


class OrderStatus(str, Enum):
    NEW = "new"
    FILLED = "filled"
    PARTIALLY_FILLED = "partially_filled"
    CANCELED = "canceled"
    REJECTED = "rejected"


class Signal(str, Enum):
    LONG = "long"
    SHORT = "short"
    FLAT = "flat"
    HOLD = "hold"


@dataclass(frozen=True)
class Candle:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float

    @property
    def is_bullish(self) -> bool:
        return self.close >= self.open


@dataclass
class Order:
    symbol: str
    side: Side
    quantity: float
    order_type: OrderType = OrderType.MARKET
    price: Optional[float] = None
    trigger_price: Optional[float] = None   # <-- NEW: forced-exit fill price hint
    status: OrderStatus = OrderStatus.NEW
    id: Optional[str] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class Fill:
    order_id: str
    symbol: str
    side: Side
    quantity: float
    price: float
    fee: float
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def notional(self) -> float:
        return self.quantity * self.price


@dataclass
class Position:
    symbol: str
    side: Side
    quantity: float
    entry_price: float
    opened_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None

    def unrealized_pnl(self, price: float) -> float:
        direction = 1 if self.side is Side.BUY else -1
        return direction * (price - self.entry_price) * self.quantity

    def market_value(self, price: float) -> float:
        return self.quantity * price


@dataclass
class ClosedTrade:
    symbol: str
    side: Side
    quantity: float
    entry_price: float
    exit_price: float
    pnl: float
    fees: float
    opened_at: datetime
    closed_at: datetime

    @property
    def return_pct(self) -> float:
        if self.entry_price == 0:
            return 0.0
        direction = 1 if self.side is Side.BUY else -1
        return direction * (self.exit_price - self.entry_price) / self.entry_price