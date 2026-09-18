"""Lab config: parse a YAML file describing a multi-strategy experiment."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml


@dataclass
class DataSpec:
    source: str                       # csv | synthetic | ccxt
    symbol: str
    timeframe: str = "1m"
    path: Optional[str] = None        # for csv
    since: Optional[str] = None       # for ccxt
    n: int = 2000                     # for synthetic
    start_price: float = 30_000.0
    drift: float = 0.0
    volatility: float = 0.004
    step_seconds: int = 60
    seed: Optional[int] = None


@dataclass
class BacktestSpec:
    starting_balance: float = 10_000.0
    fee_rate: float = 0.001
    slippage_bps: int = 5
    periods_per_year: int = 525_600


@dataclass
class StrategySpec:
    name: str
    cls: str
    params: dict[str, Any] = field(default_factory=dict)


@dataclass
class OutputSpec:
    dir: str = "data/lab_runs"

@dataclass
class RiskSpec:
    enabled: bool = False
    max_position_pct: float = 0.10
    max_daily_loss_pct: float = 0.05
    max_open_positions: int = 3
    stop_loss_pct: Optional[float] = 0.02
    take_profit_pct: Optional[float] = 0.04


@dataclass
class LabConfig:
    name: str
    data: DataSpec
    backtest: BacktestSpec
    strategies: list[StrategySpec]
    output: OutputSpec
    risk: RiskSpec = field(default_factory=RiskSpec)


def load_lab_config(path: str | Path) -> LabConfig:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(path)
    raw = yaml.safe_load(path.read_text())

    data = DataSpec(**raw["data"])
    backtest = BacktestSpec(**raw.get("backtest", {}))
    output = OutputSpec(**raw.get("output", {}))

    strategies = [
        StrategySpec(
            name=s["name"],
            cls=s.get("class", s["name"]),
            params=s.get("params", {}),
        )
        for s in raw["strategies"]
    ]
    risk = RiskSpec(**raw.get("risk", {}))
    return LabConfig(
        name=raw["name"],
        data=data,
        backtest=backtest,
        strategies=strategies,
        output=output,
        risk=risk,
    )
