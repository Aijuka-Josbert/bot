"""Performance metrics computed from an equity curve and closed trades."""
from __future__ import annotations

import math
from typing import Sequence

from .models import ClosedTrade


# --- return-based ---

def total_return_pct(start: float, end: float) -> float:
    if start <= 0:
        return 0.0
    return (end - start) / start * 100.0


def periodic_returns(equity: Sequence[float]) -> list[float]:
    """Simple period-over-period returns from an equity curve."""
    out: list[float] = []
    for prev, cur in zip(equity, equity[1:]):
        out.append((cur - prev) / prev if prev > 0 else 0.0)
    return out


def sharpe(returns: Sequence[float], periods_per_year: int = 525_600) -> float:
    """Annualized Sharpe (risk-free assumed 0). 525600 = minutes in a year."""
    if len(returns) < 2:
        return 0.0
    mean = sum(returns) / len(returns)
    var = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
    sd = math.sqrt(var)
    if sd == 0:
        return 0.0
    return (mean / sd) * math.sqrt(periods_per_year)


def sortino(returns: Sequence[float], periods_per_year: int = 525_600) -> float:
    """Like Sharpe but only penalizes downside volatility."""
    if len(returns) < 2:
        return 0.0
    mean = sum(returns) / len(returns)
    downside = [r for r in returns if r < 0]
    if not downside:
        return 0.0
    dd = math.sqrt(sum(r * r for r in downside) / len(downside))
    if dd == 0:
        return 0.0
    return (mean / dd) * math.sqrt(periods_per_year)


def max_drawdown_pct(equity: Sequence[float]) -> float:
    """Largest peak-to-trough drop, as a positive percentage."""
    if not equity:
        return 0.0
    peak = equity[0]
    worst = 0.0
    for v in equity:
        peak = max(peak, v)
        if peak > 0:
            worst = max(worst, (peak - v) / peak)
    return worst * 100.0


# --- trade-based ---

def win_rate(trades: Sequence[ClosedTrade]) -> float:
    """Fraction of trades with positive net PnL, as a percentage."""
    if not trades:
        return 0.0
    wins = sum(1 for t in trades if t.pnl > 0)
    return wins / len(trades) * 100.0


def profit_factor(trades: Sequence[ClosedTrade]) -> float:
    """Gross profit / gross loss. inf if no losers, 0 if no winners."""
    gross_win = sum(t.pnl for t in trades if t.pnl > 0)
    gross_loss = -sum(t.pnl for t in trades if t.pnl < 0)
    if gross_loss == 0:
        return math.inf if gross_win > 0 else 0.0
    return gross_win / gross_loss


def expectancy(trades: Sequence[ClosedTrade]) -> float:
    """Average net PnL per trade."""
    if not trades:
        return 0.0
    return sum(t.pnl for t in trades) / len(trades)


def average_win_loss_ratio(trades: Sequence[ClosedTrade]) -> float:
    wins = [t.pnl for t in trades if t.pnl > 0]
    losses = [-t.pnl for t in trades if t.pnl < 0]
    if not wins or not losses:
        return 0.0
    return (sum(wins) / len(wins)) / (sum(losses) / len(losses))


# --- aggregate ---

def compute_all(
    equity_curve: Sequence[float],
    trades: Sequence[ClosedTrade],
    starting_balance: float,
    periods_per_year: int = 525_600,
) -> dict[str, float]:
    """One dict with every metric the leaderboard needs."""
    if not equity_curve:
        final = starting_balance
    else:
        final = equity_curve[-1]
    rets = periodic_returns(equity_curve)
    return {
        "total_return_pct": round(total_return_pct(starting_balance, final), 4),
        "final_equity": round(final, 4),
        "sharpe": round(sharpe(rets, periods_per_year), 4),
        "sortino": round(sortino(rets, periods_per_year), 4),
        "max_drawdown_pct": round(max_drawdown_pct(equity_curve), 4),
        "trades": len(trades),
        "win_rate_pct": round(win_rate(trades), 4),
        "profit_factor": (
            round(profit_factor(trades), 4)
            if math.isfinite(profit_factor(trades)) else float("inf")
        ),
        "expectancy": round(expectancy(trades), 4),
        "avg_win_loss_ratio": round(average_win_loss_ratio(trades), 4),
    }