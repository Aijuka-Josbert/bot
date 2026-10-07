"""Multi-symbol portfolio and engine-adjacent checks."""
from bot.models import Fill, Side
from bot.portfolio import Portfolio
from bot.risk import RiskLimits, RiskManager


def _fill(symbol, side, qty, price):
    return Fill(order_id="x", symbol=symbol, side=side, quantity=qty, price=price, fee=0.0)


def test_portfolio_holds_multiple_symbols():
    p = Portfolio(starting_balance=10_000.0)
    p.apply_fill(_fill("BTC/USDT", Side.BUY, 0.01, 30_000.0))
    p.apply_fill(_fill("ETH/USDT", Side.BUY, 0.1, 3_000.0))

    assert set(p.positions.keys()) == {"BTC/USDT", "ETH/USDT"}
    eq = p.equity({"BTC/USDT": 31_000.0, "ETH/USDT": 3_100.0})
    # 10000 - 300 - 300 = 9400 cash; + 310 + 310 = 10020 equity
    assert round(eq, 2) == 10_020.00


def test_risk_max_open_positions_counts_globally(ctx):
    risk = RiskManager(RiskLimits(max_open_positions=1))
    risk.on_start(ctx)

    # pretend a position already exists on another symbol
    from bot.models import Order, Position
    ctx.portfolio.positions["ETH/USDT"] = Position(
        symbol="ETH/USDT", side=Side.BUY, quantity=0.1, entry_price=3_000.0,
    )
    order = Order(symbol="BTC/USDT", side=Side.BUY, quantity=0.001)
    assert risk.check_order(order, ctx) is None


def test_config_normalizes_singular_symbol(tmp_path):
    from bot.config import load_config

    cfg_yaml = """
bot: {name: t, strategy: sma_crossover, mode: paper, log_level: INFO}
exchange: {name: binance, testnet: true}
market: {symbol: "BTC/USDT", timeframe: "1m", candles_lookback: 100}
risk:
  starting_balance: 10000
  max_position_pct: 0.1
  max_daily_loss_pct: 0.05
  max_open_positions: 1
  stop_loss_pct: 0.02
  take_profit_pct: 0.04
  fee_rate: 0.001
  slippage_bps: 5
storage: {db_path: "data/bot.db"}
"""
    p = tmp_path / "c.yaml"
    p.write_text(cfg_yaml)
    cfg = load_config(p)
    assert cfg.market.symbols == ["BTC/USDT"]


def test_config_reads_symbols_list(tmp_path):
    from bot.config import load_config

    cfg_yaml = """
bot: {name: t, strategy: sma_crossover, mode: paper, log_level: INFO}
exchange: {name: binance, testnet: true}
market:
  symbols: ["BTC/USDT", "ETH/USDT", "SOL/USDT"]
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
storage: {db_path: "data/bot.db"}
"""
    p = tmp_path / "c.yaml"
    p.write_text(cfg_yaml)
    cfg = load_config(p)
    assert cfg.market.symbols == ["BTC/USDT", "ETH/USDT", "SOL/USDT"]