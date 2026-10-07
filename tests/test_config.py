"""Config loading: env expansion, singular/plural symbol, notifications."""
import os
from pathlib import Path

import pytest

from bot.config import load_config

_BASE = """
bot: {{name: t, strategy: sma_crossover, mode: paper, log_level: INFO}}
exchange: {{name: binance, testnet: true, api_key: "${{TEST_API_KEY}}"}}
market:
{market}
  timeframe: "1m"
  candles_lookback: 100
risk:
  starting_balance: 10000
  max_position_pct: 0.1
  max_daily_loss_pct: 0.05
  max_open_positions: 3
  stop_loss_pct: 0.02
  take_profit_pct: 0.04
  fee_rate: 0.001
  slippage_bps: 5
storage: {{db_path: "data/bot.db"}}
"""


def _write(tmp_path: Path, market: str) -> Path:
    p = tmp_path / "c.yaml"
    p.write_text(_BASE.format(market=market))
    return p


def test_singular_symbol_is_normalized(tmp_path):
    p = _write(tmp_path, '  symbol: "BTC/USDT"')
    cfg = load_config(p)
    assert cfg.market.symbols == ["BTC/USDT"]
    assert cfg.market.symbol == "BTC/USDT"


def test_plural_symbols_pass_through(tmp_path):
    p = _write(tmp_path, '  symbols: ["BTC/USDT", "ETH/USDT"]')
    cfg = load_config(p)
    assert cfg.market.symbols == ["BTC/USDT", "ETH/USDT"]


def test_missing_symbol_and_symbols_raises(tmp_path):
    p = _write(tmp_path, "")
    with pytest.raises(ValueError, match="symbol"):
        load_config(p)


def test_env_expansion(tmp_path, monkeypatch):
    monkeypatch.setenv("TEST_API_KEY", "secret123")
    p = _write(tmp_path, '  symbol: "BTC/USDT"')
    cfg = load_config(p)
    assert cfg.exchange.api_key == "secret123"


def test_missing_env_expands_to_empty(tmp_path):
    os.environ.pop("TEST_API_KEY", None)
    p = _write(tmp_path, '  symbol: "BTC/USDT"')
    cfg = load_config(p)
    assert cfg.exchange.api_key == ""


def test_notifications_defaults_when_missing(tmp_path):
    p = _write(tmp_path, '  symbol: "BTC/USDT"')
    cfg = load_config(p)
    assert cfg.notifications.enabled is False
    assert cfg.notifications.telegram.bot_token == ""


def test_repr_redacts_secrets(tmp_path):
    p = _write(tmp_path, '  symbol: "BTC/USDT"')
    cfg = load_config(p)
    cfg.exchange.api_key = "abcdef123456"
    text = repr(cfg)
    assert "abcdef123456" not in text
    assert "abcd" in text  # first chars visible