"""Portfolio: cash, positions, realized PnL. Consumes fills, emits nothing."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .models import ClosedTrade, Fill, Position, Side


@dataclass
class PortfolioSnapshot:
    cash: float
    equity: float
    realized_pnl: float
    net_realized_pnl: float 
    unrealized_pnl: float
    total_fees: float
    open_positions: list[str]
    trades_closed: int


class Portfolio:
    """
    Accounts for cash, open positions and closed trades.

    Convention:
      - Long:  cash decreases by notional on open; increases on close.
      - Short: cash increases by notional on open; decreases on close.
      - Equity = cash + Σ long market_value − Σ short market_value
    """

    EPS = 1e-12

    def __init__(self, starting_balance: float) -> None:
        if starting_balance <= 0:
            raise ValueError("starting_balance must be > 0")
        self.starting_balance = float(starting_balance)
        self.cash = float(starting_balance)
        self.realized_pnl = 0.0
        self.total_fees = 0.0
        self.positions: dict[str, Position] = {}
        self.closed_trades: list[ClosedTrade] = []

    # ---------- fills ----------
    @property
    def net_realized_pnl(self) -> float:
        """Realized trading PnL minus all fees paid so far."""
        return self.realized_pnl - self.total_fees
    
    def apply_fill(self, fill: Fill) -> None:
        # 1. cash flow
        if fill.side is Side.BUY:
            self.cash -= fill.notional
        else:
            self.cash += fill.notional
        self.cash -= fill.fee
        self.total_fees += fill.fee

        # 2. position updates
        existing = self.positions.get(fill.symbol)

        if existing is None:
            self.positions[fill.symbol] = Position(
                symbol=fill.symbol,
                side=fill.side,
                quantity=fill.quantity,
                entry_price=fill.price,
            )
            return

        if existing.side is fill.side:
            # Adding to an existing position — weighted average entry
            new_qty = existing.quantity + fill.quantity
            new_entry = (
                existing.entry_price * existing.quantity
                + fill.price * fill.quantity
            ) / new_qty
            existing.quantity = new_qty
            existing.entry_price = new_entry
            return

        # Opposite side — reduce or flip
        if fill.quantity < existing.quantity - self.EPS:
            closed_qty = fill.quantity
            self._realize(existing, closed_qty, fill)
            existing.quantity -= closed_qty
            return

        # Closing entire position (and maybe flipping)
        closed_qty = existing.quantity
        self._realize(existing, closed_qty, fill)
        remainder = fill.quantity - closed_qty

        if remainder > self.EPS:
            self.positions[fill.symbol] = Position(
                symbol=fill.symbol,
                side=fill.side,
                quantity=remainder,
                entry_price=fill.price,
            )
        else:
            del self.positions[fill.symbol]

    def _realize(self, pos: Position, closed_qty: float, fill: Fill) -> None:
        direction = 1 if pos.side is Side.BUY else -1
        pnl = direction * (fill.price - pos.entry_price) * closed_qty
        self.realized_pnl += pnl
        self.closed_trades.append(
            ClosedTrade(
                symbol=fill.symbol,
                side=pos.side,
                quantity=closed_qty,
                entry_price=pos.entry_price,
                exit_price=fill.price,
                pnl=pnl,
                fees=fill.fee,
                opened_at=pos.opened_at,
                closed_at=fill.timestamp,
            )
        )

    # ---------- valuation ----------

    def unrealized_pnl(self, market_prices: dict[str, float]) -> float:
        total = 0.0
        for sym, pos in self.positions.items():
            price = market_prices.get(sym)
            if price is None:
                continue
            total += pos.unrealized_pnl(price)
        return total

    def equity(self, market_prices: dict[str, float]) -> float:
        eq = self.cash
        for sym, pos in self.positions.items():
            price = market_prices.get(sym)
            if price is None:
                continue
            if pos.side is Side.BUY:
                eq += pos.market_value(price)
            else:
                eq -= pos.market_value(price)
        return eq

    # ---------- helpers ----------

    def position_for(self, symbol: str) -> Optional[Position]:
        return self.positions.get(symbol)

    def has_position(self, symbol: str) -> bool:
        return symbol in self.positions

    def snapshot(self, market_prices: Optional[dict[str, float]] = None) -> PortfolioSnapshot:
        prices = market_prices or {}
        return PortfolioSnapshot(
            cash=round(self.cash, 4),
            equity=round(self.equity(prices), 4),
            realized_pnl=round(self.realized_pnl, 4),
            net_realized_pnl=round(self.net_realized_pnl, 4),  
            unrealized_pnl=round(self.unrealized_pnl(prices), 4),
            total_fees=round(self.total_fees, 4),
            open_positions=list(self.positions.keys()),
            trades_closed=len(self.closed_trades),
        )