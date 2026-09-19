"""Indicator sanity checks against hand-computed values."""
import pytest

from bot.indicators import ema, rsi, sma


def test_sma_basic():
    assert sma([1, 2, 3, 4, 5], 3) == pytest.approx(4.0)


def test_sma_returns_none_when_too_few_values():
    assert sma([1, 2], 5) is None


def test_sma_rejects_zero_period():
    with pytest.raises(ValueError):
        sma([1, 2, 3], 0)


def test_ema_matches_known_series():
    # values chosen so the seed = 3 and subsequent EMA is deterministic
    result = ema([1, 2, 3, 4, 5], 3)
    # seed = (1+2+3)/3 = 2; k = 2/(3+1) = 0.5
    # ema = 4*0.5 + 2*0.5 = 3; then 5*0.5 + 3*0.5 = 4
    assert result == pytest.approx(4.0)


def test_rsi_all_up_is_100():
    values = [float(i) for i in range(1, 20)]
    assert rsi(values, 14) == pytest.approx(100.0)


def test_rsi_all_down_is_zero():
    values = [float(i) for i in range(20, 1, -1)]
    assert rsi(values, 14) == pytest.approx(0.0)


def test_rsi_none_when_not_enough_data():
    assert rsi([1, 2, 3], 14) is None