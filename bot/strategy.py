"""
Strategy interface + a concrete SMA crossover implementation.

Design rules:
  - A strategy is STATELESS from the engine's point of view.
    It receives a candle + a read-only Context, returns a list of Orders.
  - Strategies must NOT touch the portfolio or the exchange directly.
    They only *propose*; the engine *executes*.
  - This makes strategies testable in isolation and reusable in the lab.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections import deque
from dataclasses import dataclass
from typing import Optional

from .models import Candle, Order, OrderType, Position, Side


# ---------------------------------------------------------------------------
# Context — the read-only world view handed to a strategy each candle.
# ---------------------------------------------------------------------------
@dataclass
class Context:
    """
    Everything a strategy might legitimately want to know:
      symbol    — what we're trading
      position  — current open Position (or None)
      cash      — free cash
      equity    — total equity (cash + unrealized)
      candle    — the candle just closed (same as the one passed in)
    """
    symbol: str
    position: Optional[Position]
    cash: float
    equity: float
    candle: Candle


# ---------------------------------------------------------------------------
# Base class — one method to implement.
# ---------------------------------------------------------------------------
class Strategy(ABC):
    """Every strategy subclasses this and implements `on_candle`."""

    name: str = "unnamed"

    def __init__(self, **params) -> None:
        self.params = params

    @abstractmethod
    def on_candle(self, candle: Candle, ctx: Context) -> list[Order]:
        """
        Called once per closed candle. Return zero or more Orders.
        The engine will submit them in order and apply the resulting fills.
        """
        ...

    def reset(self) -> None:
        """Called between runs. Override if you keep state."""
        pass

    def __repr__(self) -> str:
        return f"<{type(self).__name__} name={self.name!r} params={self.params}>"


# ---------------------------------------------------------------------------
# A tiny rolling window helper — used by any indicator-based strategy.
# ---------------------------------------------------------------------------
class RollingWindow:
    """
    Fixed-size deque of floats. `mean()` is O(n) but n is tiny (20-200).
    Not thread-safe — one instance per strategy instance.
    """

    def __init__(self, size: int) -> None:
        if size <= 0:
            raise ValueError("size must be > 0")
        self.size = size
        self._buf: deque[float] = deque(maxlen=size)

    def push(self, value: float) -> None:
        self._buf.append(value)

    def ready(self) -> bool:
        """True once the window has been filled at least once."""
        return len(self._buf) == self.size

    def mean(self) -> Optional[float]:
        if not self.ready():
            return None
        return sum(self._buf) / self.size

    def __len__(self) -> int:
        return len(self._buf)


# ---------------------------------------------------------------------------
# Concrete strategy: SMA crossover
# ---------------------------------------------------------------------------
class SmaCrossover(Strategy):
    """
    Classic trend-following strategy.

    Rules (long-only):
      - When FAST SMA crosses ABOVE SLOW SMA  -> BUY (open long)
      - When FAST SMA crosses BELOW SLOW SMA -> SELL (close long)

    We only act on the CROSS event, not the state, so we don't spam orders.
    """

    name = "sma_crossover"

    def __init__(
        self,
        fast: int = 20,
        slow: int = 50,
        quantity: float = 1.0,
        **extra,
    ) -> None:
        super().__init__(fast=fast, slow=slow, quantity=quantity, **extra)
        if fast >= slow:
            raise ValueError("fast must be < slow")
        if fast < 2 or slow < 2:
            raise ValueError("windows must be >= 2")

        self.fast = fast
        self.slow = slow
        self.quantity = quantity

        # Two rolling windows of closes.
        self._fast_win = RollingWindow(fast)
        self._slow_win = RollingWindow(slow)

        # We remember the *previous* relationship to detect the cross.
        # None means "not yet initialized".
        self._prev_fast_above: Optional[bool] = None

    # -- engine hooks --

    def reset(self) -> None:
        self._fast_win = RollingWindow(self.fast)
        self._slow_win = RollingWindow(self.slow)
        self._prev_fast_above = None

    def on_candle(self, candle: Candle, ctx: Context) -> list[Order]:
        # 1. Update indicators with the newest close.
        self._fast_win.push(candle.close)
        self._slow_win.push(candle.close)

        # 2. Not enough history yet — do nothing.
        if not (self._fast_win.ready() and self._slow_win.ready()):
            return []

        fast = self._fast_win.mean()
        slow = self._slow_win.mean()
        assert fast is not None and slow is not None

        fast_above = fast > slow
        prev = self._prev_fast_above
        self._prev_fast_above = fast_above

        # 3. First time we have a value — just record state, don't trade.
        if prev is None:
            return []

        # 4. No cross — nothing to do.
        if fast_above == prev:
            return []

        # 5. Cross detected. Emit an order only if it makes sense given
        #    the current position.
        orders: list[Order] = []

        if fast_above and ctx.position is None:
            # Golden cross + flat -> go long.
            orders.append(Order(
                symbol=candle.symbol if hasattr(candle, "symbol") else ctx.symbol,
                side=Side.BUY,
                quantity=self.quantity,
                order_type=OrderType.MARKET,
            ))

        elif (not fast_above) and ctx.position is not None:
            # Death cross + in a position -> close it.
            # Use the exact position size so we don't leave dust.
            orders.append(Order(
                symbol=ctx.position.symbol,
                side=Side.SELL if ctx.position.side is Side.BUY else Side.BUY,
                quantity=ctx.position.quantity,
                order_type=OrderType.MARKET,
            ))

        return orders