"""Replays a candle series through a strategy, with optional risk enforcement."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterable, Optional

from .buffer import CandleBuffer
from .exchange import PaperExchange
from .metrics import compute_all
from .models import Candle, ClosedTrade, Fill, Order
from .portfolio import Portfolio
from .risk import RiskManager
from .strategy import Strategy, StrategyContext


@dataclass
class BacktestResult:
    strategy_name: str
    symbol: str
    starting_balance: float
    candles_processed: int
    error_count: int
    started_at: datetime
    finished_at: datetime
    fills: list[Fill] = field(default_factory=list)
    closed_trades: list[ClosedTrade] = field(default_factory=list)
    equity_curve: list[float] = field(default_factory=list)
    timestamps: list[datetime] = field(default_factory=list)
    metrics: dict[str, float] = field(default_factory=dict)

    @property
    def final_equity(self) -> float:
        return self.equity_curve[-1] if self.equity_curve else self.starting_balance


class Backtester:
    """
    Drives one strategy over a fixed candle series.

    If a RiskManager is provided, forced exits (SL/TP/halt) run before the
    strategy sees each candle, and every strategy order passes through
    check_order() first.
    """

    def __init__(
        self,
        starting_balance: float,
        fee_rate: float = 0.001,
        slippage_bps: int = 5,
        buffer_size: int = 500,
        periods_per_year: int = 525_600,
        risk: Optional[RiskManager] = None,
    ) -> None:
        self.starting_balance = starting_balance
        self.fee_rate = fee_rate
        self.slippage_bps = slippage_bps
        self.buffer_size = buffer_size
        self.periods_per_year = periods_per_year
        self.risk = risk

    # --- internals ---

    def _execute(
        self,
        order: Order,
        symbol: str,
        candle: Candle,
        exchange: PaperExchange,
        portfolio: Portfolio,
        strategy: Strategy,
        ctx: StrategyContext,
        result: BacktestResult,
    ) -> Optional[Fill]:
        """Submit one order. Handles trigger_price override for forced exits."""
        override = order.trigger_price is not None
        if override:
            exchange.update_price(symbol, order.trigger_price)

        fill = exchange.submit(order)

        if override:
            exchange.update_price(symbol, candle.close)

        if fill is None:
            return None

        portfolio.apply_fill(fill)
        if self.risk is not None:
            self.risk.on_fill(fill, ctx)
        strategy.on_fill(fill, ctx)
        result.fills.append(fill)
        return fill

    # --- main loop ---

    def run(
        self,
        candles: Iterable[Candle],
        strategy: Strategy,
        symbol: str,
    ) -> BacktestResult:
        candles = list(candles)
        if not candles:
            raise ValueError("no candles to backtest")

        portfolio = Portfolio(starting_balance=self.starting_balance)
        exchange = PaperExchange(fee_rate=self.fee_rate, slippage_bps=self.slippage_bps)
        buffer = CandleBuffer(maxlen=self.buffer_size)

        result = BacktestResult(
            strategy_name=getattr(strategy, "name", strategy.__class__.__name__),
            symbol=symbol,
            starting_balance=self.starting_balance,
            candles_processed=0,
            error_count=0,
            started_at=candles[0].timestamp,
            finished_at=candles[-1].timestamp,
        )

        ctx = StrategyContext(
            symbol=symbol,
            portfolio=portfolio,
            exchange=exchange,
            buffer=buffer,
            last_price=candles[0].close,
            now=candles[0].timestamp,
        )
        strategy.on_start(ctx)
        if self.risk is not None:
            self.risk.on_start(ctx)

        for candle in candles:
            try:
                buffer.append(candle)
                exchange.update_price(symbol, candle.close)
                ctx.last_price = candle.close
                ctx.now = candle.timestamp

                # 1. risk-driven forced exits (SL / TP / halt)
                if self.risk is not None:
                    for order in self.risk.on_candle(candle, ctx):
                        self._execute(order, symbol, candle, exchange,
                                      portfolio, strategy, ctx, result)

                # 2. strategy decisions
                strategy_orders = strategy.on_candle(candle, ctx) or []

                # 3. screen + execute
                for order in strategy_orders:
                    if self.risk is not None:
                        order = self.risk.check_order(order, ctx)
                        if order is None:
                            continue
                    self._execute(order, symbol, candle, exchange,
                                  portfolio, strategy, ctx, result)

                # 4. snapshot
                result.equity_curve.append(portfolio.equity({symbol: candle.close}))
                result.timestamps.append(candle.timestamp)
                result.candles_processed += 1
            except Exception:
                result.error_count += 1

        strategy.on_stop(ctx)

        result.closed_trades = list(portfolio.closed_trades)
        result.metrics = compute_all(
            equity_curve=result.equity_curve,
            trades=result.closed_trades,
            starting_balance=self.starting_balance,
            periods_per_year=self.periods_per_year,
        )

        # risk meta-metrics
        if self.risk is not None:
            result.metrics["rejected_orders"] = float(self.risk.rejection_count)
            result.metrics["halt_events"] = float(self.risk.halt_count)

        return result