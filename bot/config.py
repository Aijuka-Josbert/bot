"""Config loading with environment-variable expansion."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

load_dotenv()

_ENV_PATTERN = re.compile(r"\$\{([A-Z0-9_]+)\}")


def _expand_env(value: Any) -> Any:
    """Recursively replace '${VAR}' strings with os.environ values."""
    if isinstance(value, str):
        def repl(m: re.Match) -> str:
            return os.environ.get(m.group(1), "")
        return _ENV_PATTERN.sub(repl, value)
    if isinstance(value, dict):
        return {k: _expand_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_expand_env(v) for v in value]
    return value


@dataclass
class BotConfig:
    name: str
    strategy: str
    mode: str
    log_level: str


@dataclass
class ExchangeConfig:
    name: str
    api_key: str = ""
    api_secret: str = ""
    testnet: bool = True


@dataclass
class MarketConfig:
    symbol: str
    timeframe: str
    candles_lookback: int


@dataclass
class RiskConfig:
    starting_balance: float
    max_position_pct: float
    max_daily_loss_pct: float
    max_open_positions: int
    stop_loss_pct: float
    take_profit_pct: float
    fee_rate: float
    slippage_bps: int


@dataclass
class StorageConfig:
    db_path: str


@dataclass
class Config:
    bot: BotConfig
    exchange: ExchangeConfig
    market: MarketConfig
    risk: RiskConfig
    storage: StorageConfig


def load_config(path: str | Path = "config.yaml") -> Config:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    raw = yaml.safe_load(path.read_text())
    raw = _expand_env(raw)
    return Config(
        bot=BotConfig(**raw["bot"]),
        exchange=ExchangeConfig(**raw["exchange"]),
        market=MarketConfig(**raw["market"]),
        risk=RiskConfig(**raw["risk"]),
        storage=StorageConfig(**raw["storage"]),
    )