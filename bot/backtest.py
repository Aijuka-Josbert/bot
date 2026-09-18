"""Replays a candle series through a strategy, with optional risk enforcement."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterable, Optional

from .buffer import CandleBuffer
from .exchange import PaperExchange
from .executor import process_candle
from .metrics import compute_all
from .models import Candle, ClosedTrade, Fill
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
                fills = process_candle(
                    candle, symbol, ctx, strategy,
                    exchange, portfolio, self.risk,
                )
                result.fills.extend(fills)

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
        if self.risk is not None:
            result.metrics["rejected_orders"] = float(self.risk.rejection_count)
            result.metrics["halt_events"] = float(self.risk.halt_count)

        return result