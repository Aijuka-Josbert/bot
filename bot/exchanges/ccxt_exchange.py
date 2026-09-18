"""ccxt-backed exchange adapter implementing the same Exchange interface."""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from ..exchange import Exchange
from ..models import Candle, Fill, Order, OrderStatus, OrderType, Side

logger = logging.getLogger(__name__)


class CcxtExchange(Exchange):
    """
    Live exchange via ccxt.

    dry_run=True: orders are logged but never submitted.
    A synthetic Fill is returned using the last known price plus slippage
    so the portfolio/risk layers behave identically to a real trade.
    """

    def __init__(
        self,
        name: str,
        symbol: str,
        timeframe: str,
        api_key: str = "",
        api_secret: str = "",
        testnet: bool = True,
        dry_run: bool = False,
        fee_rate: float = 0.001,
        slippage_bps: int = 5,
    ) -> None:
        import ccxt  # lazy so paper-only users don't need ccxt installed

        if not hasattr(ccxt, name):
            raise ValueError(f"ccxt has no exchange named {name!r}")

        self.name = name
        self.symbol = symbol
        self.timeframe = timeframe
        self.dry_run = dry_run
        self.fee_rate = fee_rate
        self.slippage_bps = slippage_bps
        self._prices: dict[str, float] = {}

        params = {"enableRateLimit": True}
        if api_key:
            params["apiKey"] = api_key
        if api_secret:
            params["secret"] = api_secret

        self.client = getattr(ccxt, name)(params)
        if testnet:
            self.client.set_sandbox_mode(True)
            logger.info("ccxt sandbox mode enabled for %s", name)
        if dry_run:
            logger.warning("DRY RUN: orders will be logged but not submitted")

        self.client.load_markets()

    # --- public data ---

    def fetch_ohlcv(self, limit: int = 200) -> list[Candle]:
        raw = self.client.fetch_ohlcv(self.symbol, timeframe=self.timeframe, limit=limit)
        candles = [
            Candle(
                timestamp=datetime.fromtimestamp(row[0] / 1000.0, tz=timezone.utc),
                open=float(row[1]),
                high=float(row[2]),
                low=float(row[3]),
                close=float(row[4]),
                volume=float(row[5]),
            )
            for row in raw
        ]
        if candles:
            self._prices[self.symbol] = candles[-1].close
        return candles

    # --- Exchange interface ---

    def update_price(self, symbol: str, price: float) -> None:
        self._prices[symbol] = float(price)

    def get_last_price(self, symbol: str) -> Optional[float]:
        return self._prices.get(symbol)

    def submit(self, order: Order) -> Optional[Fill]:
        if order.order_type is not OrderType.MARKET:
            logger.warning("only market orders supported; got %s", order.order_type)
            order.status = OrderStatus.REJECTED
            return None

        if self.dry_run:
            return self._simulated_fill(order)

        try:
            resp = self.client.create_order(
                symbol=order.symbol,
                type="market",
                side=order.side.value,
                amount=order.quantity,
            )
        except Exception as e:
            logger.error("order failed: %s", e)
            order.status = OrderStatus.REJECTED
            return None

        price = resp.get("average") or resp.get("price")
        if price is None:
            cost = resp.get("cost")
            amount = resp.get("amount") or order.quantity
            price = (cost / amount) if cost else None
        if price is None:
            price = self._prices.get(order.symbol)
        if price is None:
            order.status = OrderStatus.REJECTED
            return None

        fee_info = resp.get("fee") or {}
        fee = float(fee_info.get("cost", 0.0) or 0.0)
        filled_qty = float(resp.get("filled") or order.quantity)

        order.id = str(resp.get("id") or uuid.uuid4())
        order.status = OrderStatus.FILLED

        return Fill(
            order_id=order.id,
            symbol=order.symbol,
            side=order.side,
            quantity=filled_qty,
            price=float(price),
            fee=fee,
        )

    # --- dry-run helper ---

    def _simulated_fill(self, order: Order) -> Optional[Fill]:
        ref = self._prices.get(order.symbol)
        if ref is None:
            logger.error("dry-run: no reference price for %s", order.symbol)
            order.status = OrderStatus.REJECTED
            return None

        slip = self.slippage_bps / 10_000.0
        price = ref * (1 + slip) if order.side is Side.BUY else ref * (1 - slip)
        fee = price * order.quantity * self.fee_rate

        order.id = f"dry-{uuid.uuid4()}"
        order.status = OrderStatus.FILLED
        logger.info(
            "[DRY RUN] %s %s qty=%.6f @ %.4f fee=%.4f",
            order.side.value.upper(), order.symbol,
            order.quantity, price, fee,
        )

        return Fill(
            order_id=order.id,
            symbol=order.symbol,
            side=order.side,
            quantity=order.quantity,
            price=price,
            fee=fee,
        )