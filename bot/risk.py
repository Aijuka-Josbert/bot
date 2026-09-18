"""Risk enforcement layer: position sizing, stop-loss, take-profit, daily halt."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime
from typing import Optional

from .models import Candle, Fill, Order, OrderType, Position, Side
from .strategy import StrategyContext


@dataclass
class RiskLimits:
    max_position_pct: float = 0.10
    max_daily_loss_pct: float = 0.05
    max_open_positions: int = 3
    stop_loss_pct: Optional[float] = 0.02
    take_profit_pct: Optional[float] = 0.04

    def to_dict(self) -> dict:
        return asdict(self)


class RiskManager:
    """
    Sits between the strategy and the exchange.

    Hook points used by the backtester / engine:
        on_start(ctx)               reset state
        on_candle(candle, ctx)      returns forced-exit orders (SL / TP / halt)
        check_order(order, ctx)     returns order (possibly resized) or None
        on_fill(fill, ctx)          attach SL / TP to fresh positions
    """

    def __init__(self, limits: RiskLimits) -> None:
        self.limits = limits
        self.halted = False
        self.rejection_count = 0
        self.halt_count = 0
        self._day: Optional[date] = None
        self._day_start_equity: Optional[float] = None

    # --- lifecycle ---

    def on_start(self, ctx: StrategyContext) -> None:
        self.halted = False
        self.rejection_count = 0
        self.halt_count = 0
        self._day = None
        self._day_start_equity = None

    # --- daily rollover ---

    def _roll_day(self, now: datetime, equity: float) -> None:
        today = now.date()
        if self._day != today:
            self._day = today
            self._day_start_equity = equity
            if self.halted:
                self.halted = False  # new day lifts the halt

    # --- per-candle checks ---

    def on_candle(self, candle: Candle, ctx: StrategyContext) -> list[Order]:
        equity = ctx.portfolio.equity({ctx.symbol: candle.close})
        self._roll_day(candle.timestamp, equity)

        # daily loss limit
        if self._day_start_equity and not self.halted:
            dd = (self._day_start_equity - equity) / self._day_start_equity
            if dd >= self.limits.max_daily_loss_pct:
                self.halted = True
                self.halt_count += 1

        forced: list[Order] = []
        pos = ctx.position

        if pos is None:
            return forced

        # stop-loss takes priority
        if pos.stop_loss is not None:
            hit = (
                candle.low <= pos.stop_loss if pos.side is Side.BUY
                else candle.high >= pos.stop_loss
            )
            if hit:
                forced.append(self._exit_order(ctx, pos, pos.stop_loss))
                return forced

        # take-profit
        if pos.take_profit is not None:
            hit = (
                candle.high >= pos.take_profit if pos.side is Side.BUY
                else candle.low <= pos.take_profit
            )
            if hit:
                forced.append(self._exit_order(ctx, pos, pos.take_profit))
                return forced

        # if halted, flatten everything
        if self.halted:
            forced.append(self._exit_order(ctx, pos, candle.close))

        return forced

    def _exit_order(self, ctx: StrategyContext, pos: Position, price: float) -> Order:
        return Order(
            symbol=ctx.symbol,
            side=pos.side.opposite,
            quantity=pos.quantity,
            order_type=OrderType.MARKET,
            trigger_price=price,
        )

    # --- order screening ---

    def check_order(self, order: Order, ctx: StrategyContext) -> Optional[Order]:
        if self.halted:
            self.rejection_count += 1
            return None

        if (
            not ctx.has_position
            and len(ctx.portfolio.positions) >= self.limits.max_open_positions
        ):
            self.rejection_count += 1
            return None

        # size cap on buys
        if order.side is Side.BUY and ctx.last_price > 0:
            equity = ctx.portfolio.equity({ctx.symbol: ctx.last_price})
            max_notional = equity * self.limits.max_position_pct
            notional = order.quantity * ctx.last_price
            if notional > max_notional:
                new_qty = max_notional / ctx.last_price
                if new_qty <= 0:
                    self.rejection_count += 1
                    return None
                order.quantity = new_qty

        return order

    # --- post-fill ---

    def on_fill(self, fill: Fill, ctx: StrategyContext) -> None:
        pos = ctx.portfolio.position_for(fill.symbol)
        if pos is None:
            return
        # only attach on opening fills (position side matches fill side)
        if pos.side is not fill.side:
            return

        sl = self.limits.stop_loss_pct
        tp = self.limits.take_profit_pct

        if pos.side is Side.BUY:
            pos.stop_loss = pos.entry_price * (1 - sl) if sl else None
            pos.take_profit = pos.entry_price * (1 + tp) if tp else None
        else:
            pos.stop_loss = pos.entry_price * (1 + sl) if sl else None
            pos.take_profit = pos.entry_price * (1 - tp) if tp else None