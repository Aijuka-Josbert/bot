"""Engine tick logic with a stubbed data source."""
from datetime import datetime, timedelta, timezone

import pytest

from bot.engine import Engine
from bot.exchange import PaperExchange
from bot.models import Candle
from bot.portfolio import Portfolio
from bot.strategies import make


class StubSource:
    def __init__(self, candles: list[Candle]):
        self._candles = candles
        self._last_price = candles[-1].close if candles else 0.0

    def fetch_ohlcv(self, limit: int = 10) -> list[Candle]:
        return self._candles[-limit:]

    def get_last_price(self, symbol: str) -> float:
        return self._last_price

    def update_price(self, symbol: str, price: float) -> None:
        self._last_price = price


def _candles(n=20, start=100.0, ts0=None):
    ts0 = ts0 or datetime(2026, 1, 1, tzinfo=timezone.utc)
    out = []
    price = start
    for i in range(n):
        out.append(Candle(
            timestamp=ts0 + timedelta(minutes=i),
            open=price, high=price + 0.5, low=price - 0.5,
            close=price, volume=1.0,
        ))
    return out


def test_engine_rejects_empty_strategies():
    with pytest.raises(ValueError):
        Engine(strategies={}, exchange=PaperExchange(), portfolio=Portfolio(1000.0), sources={})


def test_engine_rejects_mismatched_symbols():
    exchange = PaperExchange()
    portfolio = Portfolio(1000.0)
    strat = make("sma_crossover", {"fast": 2, "slow": 3, "quantity": 1.0})
    with pytest.raises(ValueError):
        Engine(
            strategies={"BTC/USDT": strat},
            exchange=exchange,
            portfolio=portfolio,
            sources={"ETH/USDT": StubSource(_candles())},
        )


def test_engine_processes_new_candles_only():
    candles = _candles(20)
    source = StubSource(candles)
    exchange = PaperExchange(fee_rate=0.0, slippage_bps=0)
    portfolio = Portfolio(starting_balance=10_000.0)
    strat = make("sma_crossover", {"fast": 2, "slow": 3, "quantity": 0.01})

    engine = Engine(
        strategies={"BTC/USDT": strat},
        exchange=exchange,
        portfolio=portfolio,
        sources={"BTC/USDT": source},
        poll_seconds=0,
    )
    engine.warmup()

    # first tick processes the 10 most recent candles
    engine._tick()
    # second tick should find no new candles
    before = len(engine.buffers["BTC/USDT"])
    engine._tick()
    after = len(engine.buffers["BTC/USDT"])
    assert before == after


def test_engine_stops_on_kill_switch(tmp_path):
    candles = _candles(20)
    source = StubSource(candles)
    exchange = PaperExchange(fee_rate=0.0, slippage_bps=0)
    portfolio = Portfolio(starting_balance=10_000.0)
    strat = make("sma_crossover", {"fast": 2, "slow": 3, "quantity": 0.01})

    from bot.safety import KillSwitch
    ks = KillSwitch(tmp_path / "KILL")
    ks.trigger()

    engine = Engine(
        strategies={"BTC/USDT": strat},
        exchange=exchange,
        portfolio=portfolio,
        sources={"BTC/USDT": source},
        kill_switch=ks,
        poll_seconds=0,
    )
    engine.warmup()
    before = len(engine.buffers["BTC/USDT"])
    engine.run(max_iterations=5)
    after = len(engine.buffers["BTC/USDT"])

    # the kill switch should halt before any tick runs, so no new candles
    assert before == after