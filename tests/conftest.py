"""Shared fixtures for the test suite."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from bot.buffer import CandleBuffer
from bot.exchange import PaperExchange
from bot.models import Candle
from bot.portfolio import Portfolio
from bot.strategy import StrategyContext


@pytest.fixture
def symbol() -> str:
    return "BTC/USDT"


@pytest.fixture
def ts() -> datetime:
    return datetime(2026, 1, 1, tzinfo=timezone.utc)


@pytest.fixture
def paper(symbol: str) -> PaperExchange:
    """PaperExchange with zero slippage so tests are deterministic."""
    ex = PaperExchange(fee_rate=0.001, slippage_bps=0)
    ex.update_price(symbol, 30_000.0)
    return ex


@pytest.fixture
def portfolio() -> Portfolio:
    return Portfolio(starting_balance=10_000.0)


@pytest.fixture
def ctx(symbol, portfolio, paper, ts) -> StrategyContext:
    return StrategyContext(
        symbol=symbol,
        portfolio=portfolio,
        exchange=paper,
        buffer=CandleBuffer(maxlen=500),
        last_price=30_000.0,
        now=ts,
    )


def make_candle(price: float, ts: datetime, spread: float = 0.0) -> Candle:
    return Candle(
        timestamp=ts,
        open=price,
        high=price + spread,
        low=price - spread,
        close=price,
        volume=1.0,
    )