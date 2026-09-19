"""
Place one real market order on testnet, verify it fills, then close it.

Usage:
    python scripts/live_smoke.py --yes
    bot-smoke --yes                 # after pip install -e .
"""
from __future__ import annotations

import argparse
import logging
import sys
import time

from bot.config import load_config
from bot.exchanges import CcxtExchange
from bot.models import Order, OrderType, Side


def banner(title: str) -> None:
    print(f"\n=== {title} ===")


def main() -> int:
    parser = argparse.ArgumentParser(description="Live order smoke test")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--symbol", default=None, help="override symbol")
    parser.add_argument("--quantity", type=float, default=0.001)
    parser.add_argument("--yes", action="store_true", help="skip confirmation")
    args = parser.parse_args()

    logging.basicConfig(level=logging.WARNING, format="%(levelname)s | %(message)s")

    cfg = load_config(args.config)
    symbol = args.symbol or cfg.market.symbol
    base, quote = symbol.split("/")

    banner(f"Live smoke test on {cfg.exchange.name} (testnet={cfg.exchange.testnet})")
    print(f"  symbol   : {symbol}")
    print(f"  quantity : {args.quantity} {base}")

    if not cfg.exchange.api_key:
        print("  API key missing; fill .env first")
        return 1

    ex = CcxtExchange(
        name=cfg.exchange.name,
        symbol=symbol,
        timeframe=cfg.market.timeframe,
        api_key=cfg.exchange.api_key,
        api_secret=cfg.exchange.api_secret,
        testnet=cfg.exchange.testnet,
    )

    # --- balances before ---

    bal = ex.client.fetch_balance()
    free = bal.get("free") or {}
    free_before_quote = float(free.get(quote, 0.0))
    free_before_base = float(free.get(base, 0.0))

    banner("Before")
    print(f"  free {quote}: {free_before_quote:.4f}")
    print(f"  free {base}: {free_before_base:.8f}")

    # --- price ---

    candles = ex.fetch_ohlcv(limit=2)
    if not candles:
        print("  no candles returned")
        return 1
    price = candles[-1].close
    notional = price * args.quantity
    print(f"  last price: {price:.4f}  (est notional {notional:.2f} {quote})")

    # --- confirmation ---

    banner("Plan")
    print(f"  BUY  {args.quantity} {base} at market")
    print(f"  then SELL {args.quantity} {base} at market")
    if not args.yes:
        reply = input("  proceed? [y/N]: ").strip().lower()
        if reply != "y":
            print("  aborted")
            return 0

    # --- buy ---

    banner("BUY")
    buy_order = Order(symbol=symbol, side=Side.BUY,
                      quantity=args.quantity, order_type=OrderType.MARKET)
    fill_buy = ex.submit(buy_order)
    if fill_buy is None:
        print("  BUY rejected")
        return 2
    print(f"  filled {fill_buy.quantity:.8f} @ {fill_buy.price:.4f} "
          f"fee={fill_buy.fee:.6f} id={fill_buy.order_id}")

    time.sleep(2)

    # --- sell ---

    banner("SELL")
    sell_order = Order(symbol=symbol, side=Side.SELL,
                       quantity=args.quantity, order_type=OrderType.MARKET)
    fill_sell = ex.submit(sell_order)
    if fill_sell is None:
        print("  SELL rejected — you may need to close manually")
        return 3
    print(f"  filled {fill_sell.quantity:.8f} @ {fill_sell.price:.4f} "
          f"fee={fill_sell.fee:.6f} id={fill_sell.order_id}")

    # --- balances after ---

    time.sleep(2)
    bal2 = ex.client.fetch_balance()
    free2 = bal2.get("free") or {}
    free_after_quote = float(free2.get(quote, 0.0))
    free_after_base = float(free2.get(base, 0.0))

    banner("After")
    print(f"  free {quote}: {free_after_quote:.4f}")
    print(f"  free {base}: {free_after_base:.8f}")

    # --- summary ---

    gross = (fill_sell.price - fill_buy.price) * args.quantity
    total_fees = fill_buy.fee + fill_sell.fee
    net = gross - total_fees
    delta_quote = free_after_quote - free_before_quote

    banner("Summary")
    print(f"  gross pnl    : {gross:+.6f} {quote}")
    print(f"  total fees   : {total_fees:.6f} {quote}")
    print(f"  net pnl      : {net:+.6f} {quote}")
    print(f"  quote delta  : {delta_quote:+.6f} {quote}")
    print()
    if abs(delta_quote - net) < 1.0:
        print("  live order path verified")
        return 0
    print("  balance delta does not match expected net; inspect manually")
    return 4


if __name__ == "__main__":
    sys.exit(main())