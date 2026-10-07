# Trading Bot — Handoff Guide

A modular crypto trading bot with backtesting, a multi-strategy research lab, and a live engine that shares the same execution pipeline.

---

## What it is

You give it price history and a rule, and it tells you whether that rule would have made money — realistically accounting for fees and slippage — and lets you compare many rules side by side. When you're ready, the same rule runs against a live exchange (paper, testnet, or mainnet) with risk controls that can halt trading automatically.

**Three things it does:**

1. **Backtest** a strategy over historical or synthetic candles with realistic fills
2. **Lab** — run many strategies in parallel, produce a leaderboard, charts, and a shareable HTML report
3. **Live** — trade real candles on paper, testnet, or mainnet with stop-loss, take-profit, position sizing, and a daily-loss halt

**Safety is the default.** Everything runs in paper mode unless you explicitly pass `--live`. There's a kill switch, a dry-run flag, and a preflight balance check.

---

## Install

Requires **Python 3.10+** and **git**.

```bash
# 1. clone (or unzip the handoff package)
git clone <repo-url> trading-bot
cd trading-bot

# 2. create a virtual environment
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

# 3. install
pip install -e .
```

That's it. Three commands. The `-e .` install creates three console commands:

- `bot-run` — run the bot (paper / testnet / live)
- `bot-lab` — run the multi-strategy research lab
- `bot-smoke` — place one live order to verify exchange connectivity

---

## Configure

Two files matter: `config.yaml` and `.env`. Both live in the project root.

### `config.yaml`

```yaml
bot:
  name: "alpha-1"
  strategy: "sma_crossover"
  mode: "paper"                    # paper | live
  log_level: "INFO"

exchange:
  name: "binance"                  # any ccxt exchange id
  api_key: "${BINANCE_API_KEY}"
  api_secret: "${BINANCE_API_SECRET}"
  testnet: true

market:
  symbols: ["BTC/USDT", "ETH/USDT"]
  timeframe: "1m"
  candles_lookback: 200

risk:
  starting_balance: 10000.0
  max_position_pct: 0.10           # max 10% of equity per position
  max_daily_loss_pct: 0.05         # halt for the day at -5%
  max_open_positions: 3
  stop_loss_pct: 0.02              # 2% stop-loss
  take_profit_pct: 0.04            # 4% take-profit
  fee_rate: 0.001                  # 0.1% per fill
  slippage_bps: 5                  # 0.05% adverse slippage

storage:
  db_path: "data/bot.db"

notifications:
  enabled: true
  notify_fills: false              # true -> Telegram ping on every fill
  min_interval_seconds: 5
  telegram:
    bot_token: "${TELEGRAM_BOT_TOKEN}"
    chat_id:   "${TELEGRAM_CHAT_ID}"
```

The `${VAR}` syntax is expanded from environment variables at load time.

### `.env` — copy from `.env.example` and fill in

```env
# Binance testnet (free, virtual funds) — get from https://testnet.binance.vision/
BINANCE_API_KEY=
BINANCE_API_SECRET=

# Telegram notifications — free
# 1. Talk to @BotFather -> /newbot -> copy the token
# 2. Talk to @userinfobot -> copy your numeric chat ID
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
```

**`.env` is gitignored. Never commit it. Never share the tokens.**

### Getting API keys

**Binance testnet (start here — free, virtual funds):**
1. Go to https://testnet.binance.vision/
2. Log in with GitHub
3. Click "Generate HMAC_SHA256 Key"
4. Paste both values into `.env`
5. Keep `testnet: true` in `config.yaml`

**Telegram bot token:**
1. Search `@BotFather` in Telegram, hit Start
2. Send `/newbot`, give it a name and username
3. Copy the token BotFather gives you into `.env`

**Telegram chat ID:**
1. Search `@userinfobot`, hit Start
2. It replies with your numeric ID
3. Paste into `.env`

---

## Run

### 1. Paper mode — real candles, no keys, no orders

```bash
bot-run --ticks 20 --poll 60
```

Best first run. Uses real Binance market data, simulates fills, nothing is sent to the exchange.

### 2. Dry-run — real candles, orders logged but not submitted

```bash
bot-run --live --dry-run --ticks 20 --poll 60
```

Uses your testnet keys for data and preflight, but doesn't submit orders.

### 3. Live on testnet — real orders, virtual funds

```bash
bot-run --live --ticks 20 --poll 60
```

Places real orders on Binance testnet. The preflight checks your keys and balance first.

### 4. Long-running service

```bash
bot-run --ticks 0 --poll 60          # 0 = run forever
```

Stop with `Ctrl+C`, or:

```bash
touch KILL                            # engine halts within one tick
rm KILL                               # clear when done
```

### 5. Verify live connectivity

```bash
bot-smoke --yes                       # places one buy + one sell on testnet
```

If it prints `live order path verified`, everything is wired correctly.

---

## The virtual lab

The lab runs many strategies on the same candle set, in parallel, and saves every run to disk with metrics, trades, equity curves, charts, and an HTML report.

```bash
# run a lab experiment
bot-lab run --config labs/mixed_risk.yaml

# skip disk writes (fast)
bot-lab run --config labs/mixed_risk.yaml --no-save

# skip chart generation (fastest)
bot-lab run --config labs/mixed_risk.yaml --no-charts

# list every saved run and its best strategy
bot-lab list

# show the path to a saved run's HTML report
bot-lab report --latest

# open it
xdg-open "$(bot-lab report --latest)"
```

Each saved run lives in `data/lab_runs/<timestamp>-<id>/`:

```
summary.json              # config + metrics per strategy
equity_<strategy>.csv     # equity curve per strategy
trades_<strategy>.csv     # every closed trade
chart_<strategy>.png      # equity + drawdown + trade markers
overview_equity.png       # all strategies on one plot
report.html               # self-contained HTML — email it, open it offline
```

### Lab config (`labs/*.yaml`)

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

Sample configs live in `labs/`: `compare.yaml`, `mixed.yaml`, `mixed_risk.yaml`.

---

## Included strategies

| Name | Class | Logic |
|---|---|---|
| `sma_crossover` | `SmaCrossover` | Buy on golden cross, sell on death cross |
| `rsi_mean_reversion` | `RsiMeanReversion` | Buy oversold, sell overbought |
| `bollinger_breakout` | `BollingerBreakout` | Buy close above upper band, exit below middle |

To add a new one: subclass `bot.strategy.Strategy`, implement `on_candle(self, candle, ctx) -> list[Order]`, register in `bot/strategies/__init__.py`, add a test in `tests/`.

---

## Risk controls

All enforced before an order reaches the exchange:

| Rule | Config key | Effect |
|---|---|---|
| Max position size | `max_position_pct` | Order is resized down, or rejected |
| Max open positions | `max_open_positions` | New position rejected |
| Stop-loss | `stop_loss_pct` | Auto-exit if price hits the level |
| Take-profit | `take_profit_pct` | Auto-exit at the target |
| Daily loss limit | `max_daily_loss_pct` | Engine halts and flattens, resets next day |
| Minimum notional | `min_notional` | Orders below exchange floor rejected |

`rejected_orders` and `halt_events` are recorded in backtest metrics so you can see when they fire.

---

## Deployment

Two supported paths. Full guide in `deploy/README.md`.

### Docker

```bash
mkdir -p data runtime
cp .env.example .env && $EDITOR .env
docker compose build
docker compose up -d
docker compose logs -f bot
```

Stop remotely: `docker compose stop`, or `touch runtime/KILL`.

### systemd (bare metal)

```bash
sudo cp deploy/bot.service /etc/systemd/system/bot@.service
sudo systemctl daemon-reload
sudo systemctl start bot@YOUR_USER.service
sudo systemctl enable bot@YOUR_USER.service
journalctl -u bot@YOUR_USER.service -f
```

---

## Safety notes

- **Paper mode is the default.** Nothing is submitted unless you pass `--live`.
- **`--dry-run`** on live mode logs orders without submitting them.
- **Kill switch** — create a file named `KILL` in the project root; the engine halts within one tick.
- **Preflight** — refuses to start live if API keys are missing or the balance is too low.
- **`.env` is gitignored.** Never commit keys.
- **On mainnet keys:** enable IP whitelist, disable withdrawals. A trading bot never needs withdrawal permission.
- **Do not go live until you've**: run paper mode for a week, run `--live --dry-run` successfully, and passed `bot-smoke --yes`.

### Switching to mainnet — the checklist

1. Run paper mode with real candles for at least a week
2. Run `bot-run --live --dry-run` and confirm orders are sensible
3. Run `bot-smoke --yes` on testnet — confirm `live order path verified`
4. Create mainnet keys with **IP whitelist** and **withdrawals disabled**
5. Set `testnet: false` in `config.yaml`
6. Replace `.env` with mainnet keys
7. Start with the smallest position size the config allows
8. Watch the first few fills manually

---

## Development

```bash
pip install -e ".[dev]"      # pytest + ruff
ruff check .                 # lint
ruff check --fix .           # auto-fix
pytest -q                    # full test suite
pytest --cov=bot --cov=lab   # with coverage
```

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `ModuleNotFoundError` | Run `pip install -e .` from the project root |
| `preflight: API key missing` | Fill `.env` with testnet keys |
| `cannot reach exchange` | Check network; some regions block Binance — try `exchange.name: kraken` |
| `insufficient USDT balance` | Testnet balance resets monthly — regenerate keys at testnet.binance.vision |
| `MIN_NOTIONAL` rejection on live | Raise `quantity` for the symbol, or lower `min_notional` guard |
| Empty leaderboard | Increase `data.n` in the lab config; strategies need warmup candles |
| `matplotlib not installed` | `pip install matplotlib`, or pass `--no-charts` |
| Kill switch won't stop engine | Make sure `KILL` is in the project root (not `runtime/KILL` for bare metal) |

---

## Project layout

```
bot/                     core package
├── config.py            YAML + env loader (secrets redacted in repr)
├── models.py            Candle, Order, Fill, Position, ClosedTrade
├── portfolio.py         cash, positions, realized/unrealized PnL
├── exchange.py          Exchange ABC + PaperExchange
├── exchanges/           ccxt live adapter
├── risk.py              SL/TP/halt/size cap/min_notional
├── executor.py          shared per-candle pipeline
├── strategy.py          Strategy ABC + StrategyContext
├── strategies/          sma_crossover, rsi_mean_reversion, bollinger_breakout
├── backtest.py          single-strategy runner
├── metrics.py           Sharpe, Sortino, max DD, win rate, PF
├── data.py              CSV / synthetic / ccxt loaders
├── engine.py            long-running multi-symbol live loop
├── safety.py            kill switch + preflight
├── notify.py            Telegram notifier
└── cli.py               bot-run entry point

lab/                     virtual lab
├── config.py            lab YAML schema
├── runner.py            parallel strategy runner
├── storage.py           save runs to data/lab_runs/<id>/
├── charts.py            matplotlib PNGs
├── html_report.py       self-contained HTML report
├── report.py            leaderboard printer
└── __main__.py          bot-lab CLI

labs/                    experiment configs
tests/                   61 pytest tests
deploy/                  systemd unit + deployment guide
scripts/                 bot-smoke live verification
```

---

## What's next (roadmap)

- Postgres / Timescale persistence for live equity curves
- Web dashboard
- MACD, ATR trailing stop, pairs trading
- Futures / margin support
- Portfolio-level risk (correlation caps, sector limits)
- Slack / Discord / email notifiers

---

**First commands to run, in order:**

```bash
pip install -e .
bot-run --ticks 5 --poll 10                      # paper mode sanity check
bot-lab run --config labs/mixed_risk.yaml        # lab sanity check
bot-smoke --yes                                  # live testnet verification (needs keys)
```

If all three run clean, you're set up.