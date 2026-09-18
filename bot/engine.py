"""
Engine: feeds candles to a strategy, executes orders, updates portfolio.

Responsibilities:
  1. For each candle:
     a. push price to exchange
     b. build Context from current portfolio state
     c. call strategy.on_candle -> list[Order]
     d. submit orders, collect fills
     e. apply fills to portfolio
     f. check stop-loss / take-profit on open positions
     g. record equity for the curve
  2. Return a RunResult with everything the caller needs.

The engine is exchange-agnostic: any Exchange subclass works.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Optional

from .exchange import Exchange
from .models import Candle, Fill, Order, Side
from .portfolio import Portfolio, PortfolioSnapshot
from .strategy import Context, Strategy


# ---------------------------------------------------------------------------
# RunResult — what the engine hands back when done.
# ---------------------------------------------------------------------------
@dataclass
class EquityPoint:
    timestamp: object
    equity: float


@dataclass
class RunResult:
    starting_balance: float
    final_equity: float
    realized_pnl: float
    total_fees: float
    candles_processed: int
    fills: list[Fill] = field(default_factory=list)
    equity_curve: list[EquityPoint] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def net_pnl(self) -> float:
        return self.final_equity - self.starting_balance

    @property
    def return_pct(self) -> float:
        if self.starting_balance == 0:
            return 0.0
        return self.net_pnl / self.starting_balance


# ---------------------------------------------------------------------------
# The engine itself.
# ---------------------------------------------------------------------------
class Engine:
    def __init__(
        self,
        strategy: Strategy,
        exchange: Exchange,
        portfolio: Portfolio,
        symbol: str,
        stop_loss_pct: Optional[float] = None,
        take_profit_pct: Optional[float] = None,
        verbose: bool = False,
    ) -> None:
        self.strategy = strategy
        self.exchange = exchange
        self.portfolio = portfolio
        self.symbol = symbol
        self.stop_loss_pct = stop_loss_pct
        self.take_profit_pct = take_profit_pct
        self.verbose = verbose

    # ---- main entry ----

    def run(self, candles: Iterable[Candle]) -> RunResult:
        result = RunResult(
            starting_balance=self.portfolio.starting_balance,
            final_equity=self.portfolio.starting_balance,
            realized_pnl=0.0,
            total_fees=0.0,
            candles_processed=0,
        )

        self.strategy.reset()

        for candle in candles:
            try:
                self._step(candle, result)
            except Exception as exc:  # never let one bad candle kill the run
                msg = f"candle {candle.timestamp}: {type(exc).__name__}: {exc}"
                result.errors.append(msg)
                if self.verbose:
                    print(f"  [engine error] {msg}")
                continue

            result.candles_processed += 1
            result.equity_curve.append(
                EquityPoint(timestamp=candle.timestamp, equity=self.portfolio.equity({self.symbol: candle.close}))
            )

        # Finalize summary numbers.
        last_price = (
            result.equity_curve[-1].equity if result.equity_curve else self.portfolio.starting_balance
        )
        result.final_equity = self.portfolio.equity({self.symbol: last_price}) \
            if False else last_price  # last_price already IS equity
        result.realized_pnl = self.portfolio.realized_pnl
        result.total_fees = self.portfolio.total_fees
        result.fills = list(self.exchange.fills)  # type: ignore[attr-defined]
        return result

    # ---- one candle ----

    def _step(self, candle: Candle, result: RunResult) -> None:
        # (a) Update market price so the exchange can fill orders.
        self.exchange.update_price(self.symbol, candle.close)

        # (f) BEFORE asking the strategy for new orders, honor SL/TP
        #     on any position we already hold. This models "the market
        #     hit your stop during this candle".
        self._check_exits(candle)

        # (b) Build a read-only view for the strategy.
        prices = {self.symbol: candle.close}
        ctx = Context(
            symbol=self.symbol,
            position=self.portfolio.position_for(self.symbol),
            cash=self.portfolio.cash,
            equity=self.portfolio.equity(prices),
            candle=candle,
        )

        # (c) Ask the strategy what it wants to do.
        orders = self.strategy.on_candle(candle, ctx)
        if not orders:
            return

        # (d) Submit each order; apply any fills to the portfolio.
        for order in orders:
            fill = self.exchange.submit(order)  # type: ignore[attr-defined]
            if fill is None:
                if self.verbose:
                    print(f"  [skip] {order.side.value} {order.quantity} not filled")
                continue
            self.portfolio.apply_fill(fill)
            if self.verbose:
                print(
                    f"  [{candle.timestamp:%H:%M}] "
                    f"{fill.side.value.upper():4s} {fill.quantity:.4f} "
                    f"@ {fill.price:,.2f}  fee={fill.fee:.4f}"
                )

    # ---- stop loss / take profit ----

    def _check_exits(self, candle: Candle) -> None:
        pos = self.portfolio.position_for(self.symbol)
        if pos is None:
            return

        # Respect the live price before checking thresholds.
        price = candle.close
        direction = 1 if pos.side is Side.BUY else -1
        change = direction * (price - pos.entry_price) / pos.entry_price

        should_exit = False
        if self.stop_loss_pct is not None and change <= -self.stop_loss_pct:
            should_exit = True
        if self.take_profit_pct is not None and change >= self.take_profit_pct:
            should_exit = True

        if not should_exit:
            return

        # Close the position at the current price.
        close_side = Side.SELL if pos.side is Side.BUY else Side.BUY
        order = Order(symbol=self.symbol, side=close_side, quantity=pos.quantity)
        fill = self.exchange.submit(order)  # type: ignore[attr-defined]
        if fill is not None:
            self.portfolio.apply_fill(fill)
            if self.verbose:
                reason = "SL" if change < 0 else "TP"
                print(f"  [{candle.timestamp:%H:%M}] {reason} hit — closed @ {fill.price:,.2f}")