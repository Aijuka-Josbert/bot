"""
Candle sources. Stage 4 ships synthetic + a helper buffer.

Synthetic generator: produces a sine-wave trend + gaussian noise.
Why? Because pure random walk rarely produces MA crossovers, so you'd
see 0 trades and think the bot is broken. The wave guarantees action.
"""
from __future__ import annotations

import math
import random
from collections import deque
from datetime import datetime, timedelta, timezone
from typing import Iterator, Optional

from .models import Candle


def synthetic_candles(
    symbol: str,
    n: int = 500,
    start_price: float = 30_000.0,
    amplitude: float = 0.08,       # 8% swing around trend
    period: int = 60,              # candles per full wave
    noise: float = 0.004,          # 0.4% gaussian noise
    start_time: Optional[datetime] = None,
    interval: timedelta = timedelta(minutes=1),
    seed: Optional[int] = 42,
) -> Iterator[Candle]:
    """
    Yields `n` candles. Price follows:
        p(t) = start * (1 + amplitude * sin(2πt/period)) + noise
    so you get clean up/down regimes -> many SMA crossovers.
    """
    rng = random.Random(seed)
    t0 = start_time or datetime.now(timezone.utc) - interval * n

    for i in range(n):
        trend = 1.0 + amplitude * math.sin(2 * math.pi * i / period)
        mid = start_price * trend
        close = mid * (1 + rng.gauss(0, noise))
        open_ = mid * (1 + rng.gauss(0, noise))
        high = max(open_, close) * (1 + abs(rng.gauss(0, noise / 2)))
        low = min(open_, close) * (1 - abs(rng.gauss(0, noise / 2)))
        volume = 10 + rng.random() * 5

        yield Candle(
            timestamp=t0 + interval * i,
            open=open_, high=high, low=low, close=close, volume=volume,
        )


class CandleBuffer:
    """A bounded history of candles for indicators that need lookback."""

    def __init__(self, maxlen: int = 1000) -> None:
        self._buf: deque[Candle] = deque(maxlen=maxlen)

    def push(self, c: Candle) -> None:
        self._buf.append(c)

    def __len__(self) -> int:
        return len(self._buf)

    def __iter__(self):
        return iter(self._buf)

    def last(self) -> Optional[Candle]:
        return self._buf[-1] if self._buf else None