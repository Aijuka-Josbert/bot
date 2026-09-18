"""Fixed-size rolling window of candles. Shared by all strategies."""
from __future__ import annotations

from collections import deque
from typing import Iterable, Iterator, Optional

from .models import Candle


class CandleBuffer:
    def __init__(self, maxlen: int = 500) -> None:
        if maxlen <= 0:
            raise ValueError("maxlen must be > 0")
        self._candles: deque[Candle] = deque(maxlen=maxlen)

    def append(self, candle: Candle) -> None:
        self._candles.append(candle)

    def extend(self, candles: Iterable[Candle]) -> None:
        for c in candles:
            self.append(c)

    def __len__(self) -> int:
        return len(self._candles)

    def __iter__(self) -> Iterator[Candle]:
        return iter(self._candles)

    def __getitem__(self, idx) -> Candle:
        return list(self._candles)[idx]

    @property
    def last(self) -> Optional[Candle]:
        return self._candles[-1] if self._candles else None

    def closes(self) -> list[float]:
        return [c.close for c in self._candles]

    def highs(self) -> list[float]:
        return [c.high for c in self._candles]

    def lows(self) -> list[float]:
        return [c.low for c in self._candles]

    def volumes(self) -> list[float]:
        return [c.volume for c in self._candles]