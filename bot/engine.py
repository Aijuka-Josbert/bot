"""Live engine: polls candles, drives the same pipeline as the backtester."""
from __future__ import annotations

import logging
import signal
import time
from datetime import datetime, timezone
from typing import Optional

from .buffer import CandleBuffer
from .exchange import Exchange
from .exchanges.ccxt_exchange import CcxtExchange
from .executor import process_candle
from .models import Candle
from .portfolio import Portfolio
from .risk import RiskManager
from .safety import KillSwitch
from .strategy import Strategy, StrategyContext

logger = logging.getLogger(__name__)


class Engine:
    """
    Long-running trading loop.

    Each tick:
        1. check kill switch
        2. fetch recent candles
        3. skip already-processed candles
        4. push each new candle through the shared pipeline
        5. emit a heartbeat every `heartbeat_seconds`
    """

    def __init__(
        self,
        symbol: str,
        strategy: Strategy,
        exchange: Exchange,
        portfolio: Portfolio,
        buffer_size: int = 500,
        risk: Optional[RiskManager] = None,
        poll_seconds: int = 30,
        source: Optional[CcxtExchange] = None,
        kill_switch: Optional[KillSwitch] = None,
        heartbeat_seconds: int = 60,
    ) -> None:
        self.symbol = symbol
        self.strategy = strategy
        self.exchange = exchange
        self.portfolio = portfolio
        self.buffer = CandleBuffer(maxlen=buffer_size)
        self.risk = risk
        self.poll_seconds = poll_seconds
        self.source = source
        self.kill_switch = kill_switch or KillSwitch()
        self.heartbeat_seconds = heartbeat_seconds

        self._stop = False
        self._last_ts: Optional[datetime] = None
        self._ctx: Optional[StrategyContext] = None
        self._last_heartbeat: float = 0.0

    # --- lifecycle ---

    def _install_signal_handlers(self) -> None:
        def _handler(signum, frame):
            logger.warning("signal %s received; stopping engine", signum)
            self.stop()
        signal.signal(signal.SIGINT, _handler)
        signal.signal(signal.SIGTERM, _handler)

    def stop(self) -> None:
        self._stop = True

    # --- main loop ---

    def warmup(self, candles: list[Candle]) -> None:
        for c in candles:
            self.buffer.append(c)
            self.exchange.update_price(self.symbol, c.close)
        if candles:
            self._last_ts = candles[-1].timestamp
        logger.info("warmup complete: %d candles buffered", len(candles))

    def run(self, max_iterations: Optional[int] = None) -> None:
        self._install_signal_handlers()

        first_price = self.exchange.get_last_price(self.symbol) or 0.0
        self._ctx = StrategyContext(
            symbol=self.symbol,
            portfolio=self.portfolio,
            exchange=self.exchange,
            buffer=self.buffer,
            last_price=first_price,
            now=datetime.now(timezone.utc),
        )
        self.strategy.on_start(self._ctx)
        if self.risk is not None:
            self.risk.on_start(self._ctx)

        self._last_heartbeat = time.time()

        iteration = 0
        try:
            while not self._stop:
                if max_iterations is not None and iteration >= max_iterations:
                    break
                if self.kill_switch.is_triggered():
                    logger.warning("kill switch detected; halting engine")
                    break
                self._tick()
                self._maybe_heartbeat()
                iteration += 1
                if self._stop:
                    break
                time.sleep(self.poll_seconds)
        finally:
            self.strategy.on_stop(self._ctx)
            logger.info("engine stopped after %d ticks", iteration)

    def _tick(self) -> None:
        if self.source is None:
            logger.info("no live source; tick is a no-op")
            return

        try:
            candles = self.source.fetch_ohlcv(limit=10)
        except Exception as e:
            logger.error("fetch failed: %s", e)
            return

        new_candles = [
            c for c in candles
            if self._last_ts is None or c.timestamp > self._last_ts
        ]
        if not new_candles:
            return

        for candle in new_candles:
            self.buffer.append(candle)
            self.exchange.update_price(self.symbol, candle.close)
            fills = process_candle(
                candle, self.symbol, self._ctx, self.strategy,
                self.exchange, self.portfolio, self.risk,
            )
            for f in fills:
                logger.info(
                    "FILL %s qty=%.6f @ %.4f fee=%.4f",
                    f.side.value.upper(), f.quantity, f.price, f.fee,
                )
            self._last_ts = candle.timestamp

        eq = self.portfolio.equity({self.symbol: new_candles[-1].close})
        logger.info(
            "tick: %d new candle(s) | last=%.2f | equity=%.2f | pos=%s",
            len(new_candles), new_candles[-1].close, eq,
            list(self.portfolio.positions.keys()),
        )

    def _maybe_heartbeat(self) -> None:
        now = time.time()
        if now - self._last_heartbeat < self.heartbeat_seconds:
            return
        self._last_heartbeat = now
        last_price = self.exchange.get_last_price(self.symbol) or 0.0
        eq = self.portfolio.equity({self.symbol: last_price})
        logger.info(
            "heartbeat | equity=%.2f | positions=%d | last=%.2f",
            eq, len(self.portfolio.positions), last_price,
        )