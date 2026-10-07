# Changelog

All notable changes to this project are documented here.
Format based on [Keep a Changelog](https://keepachangelog.com/).

## [0.1.0] - 2026-10-07

### Added
- Modular bot core: `bot/`
  - Config loading with env-var expansion
  - Portfolio accounting (long/short, partial close, flip)
  - PaperExchange with realistic slippage + fees
  - Risk manager: position sizing, SL/TP, daily loss halt
  - Strategies: SMA crossover, RSI mean reversion, Bollinger breakout
  - Backtester with metrics (Sharpe, Sortino, max DD, win rate, PF)
  - Live engine with multi-symbol support
  - ccxt adapter for real orders (testnet + mainnet)
  - Safety layer: kill switch, dry-run, preflight, notifications
- Virtual lab: `lab/`
  - Parallel multi-strategy runner
  - Per-run persistence: summary.json, trades.csv, equity.csv
  - Charts (matplotlib) and self-contained HTML report
  - CLI: `bot-lab run|list|charts|report`
- CLI: `bot-run`, `bot-lab`, `bot-smoke`
- Deployment: Dockerfile, docker-compose.yml, systemd unit
- 60+ pytest tests
- Packaging: `pyproject.toml`, editable install, console scripts

### Security
- API keys and secrets redacted in `Config.__repr__`