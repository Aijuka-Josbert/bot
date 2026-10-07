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


# --- bot / exchange / market ---

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
    symbols: list[str]
    timeframe: str
    candles_lookback: int

    @property
    def symbol(self) -> str:
        """Backwards-compat: first symbol. Prefer `symbols` in new code."""
        return self.symbols[0]


# --- risk / storage ---

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


# --- notifications ---

@dataclass
class TelegramConfig:
    bot_token: str = ""
    chat_id: str = ""


@dataclass
class NotificationConfig:
    enabled: bool = False
    notify_fills: bool = False
    min_interval_seconds: float = 5.0
    telegram: TelegramConfig = field(default_factory=TelegramConfig)


# --- top-level ---

@dataclass
class Config:
    bot: BotConfig
    exchange: ExchangeConfig
    market: MarketConfig
    risk: RiskConfig
    storage: StorageConfig
    notifications: NotificationConfig = field(default_factory=NotificationConfig)

    def __repr__(self) -> str:
        def redact(v: str) -> str:
            if not v:
                return "<empty>"
            return v[:4] + "…" + v[-4:] if len(v) > 8 else "<set>"

        return (
            "Config(\n"
            f"  bot={self.bot!r},\n"
            f"  exchange=ExchangeConfig("
            f"name={self.exchange.name!r}, "
            f"api_key={redact(self.exchange.api_key)!r}, "
            f"api_secret={redact(self.exchange.api_secret)!r}, "
            f"testnet={self.exchange.testnet}),\n"
            f"  market={self.market!r},\n"
            f"  risk={self.risk!r},\n"
            f"  storage={self.storage!r},\n"
            f"  notifications=NotificationConfig("
            f"enabled={self.notifications.enabled}, "
            f"notify_fills={self.notifications.notify_fills}, "
            f"min_interval_seconds={self.notifications.min_interval_seconds}, "
            f"telegram=TelegramConfig("
            f"bot_token={redact(self.notifications.telegram.bot_token)!r}, "
            f"chat_id={redact(self.notifications.telegram.chat_id)!r})),\n"
            ")"
        )

def load_config(path: str | Path = "config.yaml") -> Config:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    raw = yaml.safe_load(path.read_text())
    raw = _expand_env(raw)

    # market: accept either `symbol:` (singular) or `symbols:` (list)
    market_raw = dict(raw["market"])
    if "symbols" not in market_raw:
        if "symbol" not in market_raw:
            raise ValueError("market block requires 'symbol' or 'symbols'")
        market_raw["symbols"] = [market_raw.pop("symbol")]
    elif "symbol" in market_raw:
        market_raw.pop("symbol")  # prefer symbols if both are present
    market = MarketConfig(**market_raw)

    # notifications: optional block, telegram sub-block optional
    raw_notif = dict(raw.get("notifications", {}) or {})
    telegram_cfg = TelegramConfig(**(raw_notif.pop("telegram", {}) or {}))
    notifications = NotificationConfig(telegram=telegram_cfg, **raw_notif)

    return Config(
        bot=BotConfig(**raw["bot"]),
        exchange=ExchangeConfig(**raw["exchange"]),
        market=market,
        risk=RiskConfig(**raw["risk"]),
        storage=StorageConfig(**raw["storage"]),
        notifications=notifications,
    )