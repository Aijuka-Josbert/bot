# bot

A modular crypto trading bot with backtesting, a multi-strategy research
lab, and a live engine that shares the exact same pipeline.

## What it does

- Loads candle data from CSV, synthetic generators, or a live exchange (ccxt)
- Runs one or many strategies over the same data
- Fills orders through a paper exchange with realistic fees and slippage,
  or through a real exchange (testnet or mainnet)
- Enforces risk limits: position sizing, stop-loss, take-profit, daily loss halt
- Persists every lab run to disk with full metrics, trade list, and equity curve
- Halts on demand via a kill switch file

## Layout

```
bot/
├── main.py                 # entry point (paper / live / dry-run)
├── config.yaml             # bot + exchange + risk config
├── .env.example            # copy to .env and fill in API keys
├── requirements.txt
├── bot/                    # core package
│   ├── config.py           # YAML + env loader
│   ├── models.py           # Candle, Order, Fill, Position, ...
│   ├── portfolio.py        # cash, positions, realized/unrealized PnL
│   ├── exchange.py         # Exchange ABC + PaperExchange
│   ├── exchanges/          # ccxt-backed live adapter
│   ├── risk.py             # RiskManager (SL/TP/halt/size cap)
│   ├── executor.py         # shared per-candle pipeline
│   ├── strategy.py         # Strategy ABC + StrategyContext
│   ├── strategies/         # sma_crossover, rsi_mean_reversion, bollinger
│   ├── backtest.py         # single-strategy runner
│   ├── metrics.py          # Sharpe, Sortino, max DD, win rate, ...
│   ├── data.py             # CSV / synthetic / ccxt loaders
│   ├── engine.py           # long-running live loop
│   └── safety.py           # kill switch + preflight checks
├── lab/                    # virtual lab
│   ├── config.py           # lab YAML schema
│   ├── runner.py           # parallel strategy runner
│   ├── storage.py          # save runs to data/lab_runs/<id>/
│   ├── report.py           # leaderboard printer
│   └── __main__.py         # CLI: python -m lab ...
├── labs/                   # lab experiment configs
│   ├── compare.yaml
│   ├── mixed.yaml
│   └── mixed_risk.yaml
└── data/                   # runtime output (gitignored)
    ├── bot.db
    └── lab_runs/
```

## Install

Requires Python 3.10 or newer.

```bash
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

## Configuration

### `config.yaml`

```yaml
bot:
  name: "alpha-1"
  strategy: "sma_crossover"     # name from bot/strategies/REGISTRY
  mode: "paper"                 # paper | live
  log_level: "INFO"

exchange:
  name: "binance"               # any ccxt exchange id
  api_key: "${BINANCE_API_KEY}"
  api_secret: "${BINANCE_API_SECRET}"
  testnet: true                 # true -> sandbox / testnet

market:
  symbol: "BTC/USDT"
  timeframe: "1m"
  candles_lookback: 200

risk:
  starting_balance: 10000.0
  max_position_pct: 0.10        # max 10% of equity per position
  max_daily_loss_pct: 0.05      # halt for the day at -5%
  max_open_positions: 3
  stop_loss_pct: 0.02           # 2% stop-loss
  take_profit_pct: 0.04         # 4% take-profit
  fee_rate: 0.001               # 0.1% per fill
  slippage_bps: 5               # 5 bps = 0.05% adverse slippage

storage:
  db_path: "data/bot.db"
```

`${VAR}` syntax is expanded from environment variables (loaded from `.env`).

### `.env`

Copy `.env.example` to `.env` and fill in your keys. `.env` is gitignored.

#### Getting API keys

**Binance testnet (recommended for first runs) — free, virtual funds**

1. Go to https://testnet.binance.vision/
2. Log in with GitHub (create a GitHub account if you don't have one)
3. Click "Generate HMAC_SHA256 Key"
4. Copy both the API Key and Secret Key into `.env`
5. Keep `testnet: true` in `config.yaml`

**Binance mainnet — real money**

1. Create and verify a Binance account
2. Enable 2FA, then go to API Management and create an API key
3. Enable **IP whitelist**, disable **withdrawals**
4. Paste into `.env`, set `testnet: false` in `config.yaml`

**Do not use mainnet keys until you have run `--dry-run` successfully at least
once and understand what orders the strategy will place.**

## Running the bot

### Paper mode (real candles, no keys, no orders)

```bash
python main.py --ticks 20 --poll 5
```

### Dry-run against testnet (real candles, orders logged, nothing submitted)

```bash
python main.py --live --dry-run --ticks 20 --poll 60
```

### Live on testnet (real orders, virtual funds)

```bash
python main.py --live --ticks 20 --poll 60
```

The engine will refuse to start if API keys are missing or the balance is
below the minimum. Fix the reported issue and retry.

### Kill switch

From another terminal:

```bash
touch KILL
```

The engine halts within one tick and exits cleanly. Remove the file when done:

```bash
rm KILL
```

### Stop

Ctrl+C. The engine catches SIGINT/SIGTERM and shuts down gracefully.

## Running the virtual lab

The lab runs multiple strategies over the same candles, in parallel, saves
each run to `data/lab_runs/<timestamp>-<id>/`, and prints a leaderboard.

```bash
python -m lab run --config labs/mixed_risk.yaml
python -m lab run --config labs/mixed_risk.yaml --no-save
python -m lab run --config labs/mixed_risk.yaml --sequential
python -m lab list
```

### Lab config

```yaml
name: my_experiment

data:
  source: synthetic          # csv | synthetic | ccxt
  symbol: BTC/USDT
  timeframe: 1m
  n: 2000
  start_price: 30000
  drift: 0.00002
  volatility: 0.004
  step_seconds: 60
  seed: 42
  # path: data/BTCUSDT_1m.csv     # for source: csv

backtest:
  starting_balance: 10000
  fee_rate: 0.001
  slippage_bps: 5
  periods_per_year: 525600

risk:
  enabled: true
  max_position_pct: 0.10
  max_daily_loss_pct: 0.02
  max_open_positions: 1
  stop_loss_pct: 0.01
  take_profit_pct: 0.02

strategies:
  - name: sma_med
    class: sma_crossover
    params: { fast: 10, slow: 30, quantity: 0.05 }
  - name: rsi_14
    class: rsi_mean_reversion
    params: { period: 14, oversold: 30, overbought: 70, quantity: 0.05 }
  - name: boll_20_2
    class: bollinger_breakout
    params: { period: 20, num_std: 2.0, quantity: 0.05 }

output:
  dir: data/lab_runs
```

### Lab output

Each run writes:

```
data/lab_runs/20260919-011530-a1b2c3/
├── summary.json                  # config + metrics per strategy
├── equity_sma_med.csv
├── equity_rsi_14.csv
├── equity_boll_20_2.csv
├── trades_sma_med.csv
├── trades_rsi_14.csv
└── trades_boll_20_2.csv
```

## Available strategies

| Name | Class | Description |
|---|---|---|
| `sma_crossover` | `SmaCrossover` | Buy on golden cross, sell on death cross |
| `rsi_mean_reversion` | `RsiMeanReversion` | Buy oversold, sell overbought |
| `bollinger_breakout` | `BollingerBreakout` | Buy close above upper band, exit below middle |

Add a new strategy: subclass `bot.strategy.Strategy`, implement `on_candle`,
and register it in `bot/strategies/__init__.py`.

## Safety notes

- Everything runs in **paper mode by default**. Nothing is submitted unless
  you pass `--live`.
- `--dry-run` on live mode logs orders without submitting them.
- The **kill switch** (`KILL` file in project root) halts the engine within
  one tick.
- **Preflight** checks API keys and balance before starting live; refuses if
  either is missing.
- `.env` is gitignored. **Never commit API keys.**
- On mainnet API keys: enable IP whitelist, disable withdrawals.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `ModuleNotFoundError: ccxt` | `pip install -r requirements.txt` |
| `preflight: API key missing` | Fill `.env` with testnet keys |
| `cannot reach exchange` | Check network; some regions block Binance — try `exchange.name: kraken` in `config.yaml` |
| `insufficient USDT balance` | Testnet balance resets monthly — regenerate keys |
| `no candles to backtest` | Increase `data.n` in the lab config |
| `max_open_positions` never hits | Expected with single-symbol configs |

## Install as a package

For a proper install (creates `bot-run` and `bot-lab` commands):

```bash
# from the project root
pip install -e .

# optional: dev tools (pytest, ruff)
pip install -e ".[dev]"
```

After install, the CLI is available system-wide:

```bash
bot-run --ticks 20 --poll 5
bot-run --live --dry-run --ticks 20
bot-lab run --config labs/mixed_risk.yaml
bot-lab list
bot-lab report --latest
```

`python main.py` and `python -m lab` still work — the console scripts
are just aliases.