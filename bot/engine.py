"""Live engine: polls candles for N symbols, drives the shared pipeline."""
from __future__ import annotations

import logging
import signal
import time
from datetime import datetime, timezone

from .buffer import CandleBuffer
from .exchange import Exchange
from .exchanges.ccxt_exchange import CcxtExchange
from .executor import process_candle
from .notify import NullNotifier
from .portfolio import Portfolio
from .risk import RiskManager
from .safety import KillSwitch
from .strategy import Strategy, StrategyContext

logger = logging.getLogger(__name__)


class Engine:
    """
    Long-running trading loop, multi-symbol.

    Each tick:
        1. check kill switch
        2. for each symbol: fetch recent candles, skip processed
        3. push each new candle through the shared pipeline
        4. emit a heartbeat every `heartbeat_seconds`
    """

    def __init__(
        self,
        strategies: dict[str, Strategy],
        exchange: Exchange,
        portfolio: Portfolio,
        sources: dict[str, CcxtExchange],
        buffer_size: int = 500,
        risk: RiskManager | None = None,
        poll_seconds: int = 30,
        kill_switch: KillSwitch | None = None,
        heartbeat_seconds: int = 60,
        notifier=None,
        notify_fills: bool = False,
    ) -> None:
        if not strategies:
            raise ValueError("at least one symbol/strategy is required")
        if set(strategies) != set(sources):
            raise ValueError("strategies and sources must cover the same symbols")

        self.symbols = list(strategies.keys())
        self.strategies = strategies
        self.sources = sources
        self.exchange = exchange
        self.portfolio = portfolio
        self.risk = risk
        self.poll_seconds = poll_seconds
        self.kill_switch = kill_switch or KillSwitch()
        self.heartbeat_seconds = heartbeat_seconds
        self.notifier = notifier or NullNotifier()
        self.notify_fills = notify_fills

        self.buffers: dict[str, CandleBuffer] = {
            s: CandleBuffer(maxlen=buffer_size) for s in self.symbols
        }
        self.contexts: dict[str, StrategyContext] = {}
        self._last_ts: dict[str, datetime | None] = {s: None for s in self.symbols}

        self._stop = False
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

    # --- warmup ---

    def warmup(self) -> None:
        """Fetch historical candles per symbol and build contexts."""
        for symbol in self.symbols:
            candles = self.sources[symbol].fetch_ohlcv(limit=200)
            for c in candles:
                self.buffers[symbol].append(c)
                self.exchange.update_price(symbol, c.close)
            if candles:
                self._last_ts[symbol] = candles[-1].timestamp

            first_price = self.exchange.get_last_price(symbol) or 0.0
            self.contexts[symbol] = StrategyContext(
                symbol=symbol,
                portfolio=self.portfolio,
                exchange=self.exchange,
                buffer=self.buffers[symbol],
                last_price=first_price,
                now=datetime.now(timezone.utc),
            )
            logger.info("warmup %s: %d candles", symbol, len(candles))

    # --- main loop ---

    def run(self, max_iterations: int | None = None) -> None:
        if not self.contexts:
            self.warmup()

        self._install_signal_handlers()

        for symbol in self.symbols:
            self.strategies[symbol].on_start(self.contexts[symbol])
        if self.risk is not None:
            self.risk.on_start(self.contexts[self.symbols[0]])

        self.notifier.send(
            f"Engine started\n"
            f"symbols: {', '.join(self.symbols)}\n"
            f"strategies: {', '.join(self.strategies[s].name for s in self.symbols)}\n"
            f"poll: {self.poll_seconds}s",
            level="info",
        )

        self._last_heartbeat = time.time()
        iteration = 0
        try:
            while not self._stop:
                if max_iterations is not None and iteration >= max_iterations:
                    break
                if self.kill_switch.is_triggered():
                    logger.warning("kill switch detected; halting engine")
                    self.notifier.send(
                        "Kill switch triggered — engine halting", level="warning"
                    )
                    break
                self._tick()
                self._maybe_heartbeat()
                iteration += 1
                if self._stop:
                    break
                time.sleep(self.poll_seconds)
        finally:
            for symbol in self.symbols:
                self.strategies[symbol].on_stop(self.contexts[symbol])
            logger.info("engine stopped after %d ticks", iteration)
            self.notifier.send(f"Engine stopped after {iteration} ticks", level="info")

    # --- one tick across all symbols ---

    def _tick(self) -> None:
        total_new = 0
        for symbol in self.symbols:
            total_new += self._tick_symbol(symbol)

        if total_new:
            prices = {
                s: self.exchange.get_last_price(s) or 0.0 for s in self.symbols
            }
            eq = self.portfolio.equity(prices)
            logger.info(
                "tick: %d new candle(s) | equity=%.2f | pos=%s",
                total_new, eq, list(self.portfolio.positions.keys()),
            )

    def _tick_symbol(self, symbol: str) -> int:
        try:
            candles = self.sources[symbol].fetch_ohlcv(limit=10)
        except Exception as e:
            logger.error("fetch %s failed: %s", symbol, e)
            return 0

        new_candles = [
            c for c in candles
            if self._last_ts[symbol] is None or c.timestamp > self._last_ts[symbol]
        ]
        if not new_candles:
            return 0

        ctx = self.contexts[symbol]
        for candle in new_candles:
            self.buffers[symbol].append(candle)
            self.exchange.update_price(symbol, candle.close)

            halts_before = self.risk.halt_count if self.risk else 0

            fills = process_candle(
                candle, symbol, ctx, self.strategies[symbol],
                self.exchange, self.portfolio, self.risk,
            )

            halts_after = self.risk.halt_count if self.risk else 0
            if halts_after > halts_before:
                self.notifier.send(
                    f"Daily loss limit hit — trading halted\n"
                    f"equity: {self.portfolio.equity({symbol: candle.close}):.2f}",
                    level="error",
                )

            for f in fills:
                logger.info(
                    "FILL %s %s qty=%.6f @ %.4f fee=%.4f",
                    f.side.value.upper(), symbol, f.quantity, f.price, f.fee,
                )
                if self.notify_fills:
                    self.notifier.send(
                        f"<b>{f.side.value.upper()}</b> {symbol}\n"
                        f"qty: {f.quantity:.6f}\n"
                        f"price: {f.price:.4f}\n"
                        f"fee: {f.fee:.6f}",
                        level="info",
                    )

            self._last_ts[symbol] = candle.timestamp

        return len(new_candles)

    def _maybe_heartbeat(self) -> None:
        now = time.time()
        if now - self._last_heartbeat < self.heartbeat_seconds:
            return
        self._last_heartbeat = now
        prices = {s: self.exchange.get_last_price(s) or 0.0 for s in self.symbols}
        eq = self.portfolio.equity(prices)
        logger.info(
            "heartbeat | equity=%.2f | positions=%d | symbols=%d",
            eq, len(self.portfolio.positions), len(self.symbols),
        )