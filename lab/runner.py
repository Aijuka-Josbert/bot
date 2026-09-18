"""Run multiple strategies over the same candle set."""
from __future__ import annotations

import concurrent.futures as cf
from dataclasses import dataclass

from bot.backtest import BacktestResult, Backtester
from bot.data import generate_synthetic, load_csv
from bot.models import Candle
from bot.strategies import make

from .config import LabConfig, StrategySpec
from bot.risk import RiskLimits, RiskManager


@dataclass
class StrategyRun:
    name: str
    spec: StrategySpec
    result: BacktestResult


@dataclass
class LabRun:
    name: str
    candles: list[Candle]
    symbol: str
    runs: list[StrategyRun]
    starting_balance: float


def load_candles(cfg: LabConfig) -> list[Candle]:
    d = cfg.data
    if d.source == "csv":
        if not d.path:
            raise ValueError("data.path required for csv source")
        return load_csv(d.path)
    if d.source == "synthetic":
        return generate_synthetic(
            n=d.n,
            start_price=d.start_price,
            drift=d.drift,
            volatility=d.volatility,
            step_seconds=d.step_seconds,
            seed=d.seed,
        )
    if d.source == "ccxt":
        from bot.data import download_ccxt
        return download_ccxt(
            symbol=d.symbol,
            timeframe=d.timeframe,
            since_iso=d.since,
            limit=d.n,
        )
    raise ValueError(f"unknown data source: {d.source!r}")

def _build_risk(cfg: LabConfig) -> Optional[RiskManager]:
    if not cfg.risk.enabled:
        return None
    return RiskManager(RiskLimits(
        max_position_pct=cfg.risk.max_position_pct,
        max_daily_loss_pct=cfg.risk.max_daily_loss_pct,
        max_open_positions=cfg.risk.max_open_positions,
        stop_loss_pct=cfg.risk.stop_loss_pct,
        take_profit_pct=cfg.risk.take_profit_pct,
    ))


def _run_one(spec: StrategySpec, candles: list[Candle], symbol: str, cfg: LabConfig) -> StrategyRun:
    strategy = make(spec.cls, spec.params)
    bt = Backtester(
        starting_balance=cfg.backtest.starting_balance,
        fee_rate=cfg.backtest.fee_rate,
        slippage_bps=cfg.backtest.slippage_bps,
        periods_per_year=cfg.backtest.periods_per_year,
        risk=_build_risk(cfg),
    )
    result = bt.run(candles, strategy, symbol=symbol)
    return StrategyRun(name=spec.name, spec=spec, result=result)


def run_lab(cfg: LabConfig, parallel: bool = True) -> LabRun:
    candles = load_candles(cfg)
    symbol = cfg.data.symbol

    if parallel and len(cfg.strategies) > 1:
        with cf.ThreadPoolExecutor() as pool:
            futures = [
                pool.submit(_run_one, spec, candles, symbol, cfg)
                for spec in cfg.strategies
            ]
            runs = [f.result() for f in futures]
    else:
        runs = [_run_one(spec, candles, symbol, cfg) for spec in cfg.strategies]

    return LabRun(
        name=cfg.name,
        candles=candles,
        symbol=symbol,
        runs=runs,
        starting_balance=cfg.backtest.starting_balance,
    )