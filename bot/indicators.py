"""Pure indicator functions. Take a sequence of floats, return a float or None."""
from __future__ import annotations

from typing import Optional, Sequence


def sma(values: Sequence[float], period: int) -> Optional[float]:
    """Simple moving average of the last `period` values."""
    if period <= 0:
        raise ValueError("period must be > 0")
    if len(values) < period:
        return None
    return sum(values[-period:]) / period


def ema(values: Sequence[float], period: int) -> Optional[float]:
    """Exponential moving average, seeded with an SMA of the first `period` values."""
    if period <= 0:
        raise ValueError("period must be > 0")
    if len(values) < period:
        return None
    k = 2.0 / (period + 1.0)
    seed = sum(values[:period]) / period
    result = seed
    for v in values[period:]:
        result = v * k + result * (1 - k)
    return result


def rsi(values: Sequence[float], period: int = 14) -> Optional[float]:
    """Wilder's RSI over the last `period` changes."""
    if period <= 0:
        raise ValueError("period must be > 0")
    if len(values) < period + 1:
        return None

    gains = 0.0
    losses = 0.0
    for i in range(-period, 0):
        change = values[i] - values[i - 1]
        if change >= 0:
            gains += change
        else:
            losses -= change

    avg_gain = gains / period
    avg_loss = losses / period
    if avg_loss == 0.0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))