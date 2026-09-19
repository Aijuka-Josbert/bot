# Deployment

Two supported paths. Pick one.

## Option 1 — Docker

### Setup

```bash
# on the server
git clone <your-repo> trading-bot
cd trading-bot

# create runtime + data directories
mkdir -p data runtime

# config + secrets (not in git)
cp .env.example .env
$EDITOR .env
$EDITOR config.yaml

# build
docker compose build
```

### Run

```bash
# foreground
docker compose up

# detached
docker compose up -d

# follow logs
docker compose logs -f bot

# stop gracefully
docker compose down
```

### Stop the bot remotely

Either:

```bash
docker compose stop           # SIGTERM -> engine stops cleanly
```

Or with the file-based kill switch:

```bash
touch runtime/KILL            # engine halts within one tick
rm runtime/KILL                # clear when done
```

### Update

```bash
git pull
docker compose build
docker compose up -d
```

## Option 2 — systemd (bare metal)

### Setup

```bash
# 1. install into a venv at a fixed path
cd /home/$USER/Desktop/bot
python -m venv .venv
source .venv/bin/activate
pip install -e .

# 2. fill in config + secrets
cp .env.example .env
$EDITOR .env
$EDITOR config.yaml

# 3. install the service (system-wide; needs sudo)
sudo cp deploy/bot.service /etc/systemd/system/bot@.service
sudo systemctl daemon-reload
```

### Run

```bash
# start (replace 'josbert' with your username)
sudo systemctl start bot@josbert.service

# enable at boot
sudo systemctl enable bot@josbert.service

# status
sudo systemctl status bot@josbert.service

# logs
sudo journalctl -u bot@josbert.service -f
```

### Stop

```bash
sudo systemctl stop bot@josbert.service
```

Or use the kill switch:

```bash
touch /home/$USER/Desktop/bot/KILL
```

### Update

```bash
cd /home/$USER/Desktop/bot
git pull
source .venv/bin/activate
pip install -e .
sudo systemctl restart bot@josbert.service
```

## Switching to mainnet

**Do not do this lightly.** Before flipping live:

1. Run for at least a week in paper mode with real candles
2. Run `bot-run --live --dry-run` against testnet and confirm the orders are sensible
3. Run `bot-smoke --yes` against testnet and confirm fills land
4. Create **mainnet** API keys with **IP whitelist** and **withdrawals disabled**
5. Set `testnet: false` in `config.yaml`
6. Replace `.env` with mainnet keys
7. Start with the smallest position size your config allows
8. Watch the first few fills manually

In `docker-compose.yml`, change the command to add `--live`:

```yaml
command: ["--config", "config.yaml", "--live", "--ticks", "0", "--poll", "60"]
```

In `bot@.service`, add `--live` to `ExecStart`.

**The kill switch and `docker stop` / `systemctl stop` both work in live mode. Use them if anything looks wrong.**