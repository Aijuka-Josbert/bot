"""Abstract strategy interface + the context object strategies see."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

from .buffer import CandleBuffer
from .exchange import Exchange
from .models import Candle, Fill, Order
from .portfolio import Portfolio


@dataclass
class StrategyContext:
    """Everything a strategy is allowed to look at or act on."""
    symbol: str
    portfolio: Portfolio
    exchange: Exchange
    buffer: CandleBuffer
    last_price: float
    now: datetime

    @property
    def closes(self) -> list[float]:
        return self.buffer.closes()

    @property
    def position(self):
        return self.portfolio.position_for(self.symbol)

    @property
    def has_position(self) -> bool:
        return self.portfolio.has_position(self.symbol)


class Strategy(ABC):
    """
    Base class for all strategies.

    Lifecycle:
        on_start(ctx)            -> once, before any candle is fed
        on_candle(candle, ctx)   -> on every new closed candle; return list[Order]
        on_fill(fill, ctx)       -> whenever an order fills
        on_stop(ctx)             -> once, at the end

    Strategies are stateless with respect to money - they only emit orders.
    The engine is responsible for executing them.
    """

    name: str = "strategy"

    def __init__(self, params: Optional[dict[str, Any]] = None) -> None:
        self.params = params or {}

    def on_start(self, ctx: StrategyContext) -> None:
        pass

    @abstractmethod
    def on_candle(self, candle: Candle, ctx: StrategyContext) -> list[Order]:
        ...

    def on_fill(self, fill: Fill, ctx: StrategyContext) -> None:
        pass

    def on_stop(self, ctx: StrategyContext) -> None:
        pass

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} name={self.name!r} params={self.params}>"