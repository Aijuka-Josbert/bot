"""Safety guards: kill switch and pre-flight checks."""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class KillSwitch:
    """
    Halt the engine if a sentinel file exists.

    Checked at the top of every tick. Create the file to stop, delete to resume.
    Default location: ./KILL (project root).
    """

    def __init__(self, path: str | Path = "KILL") -> None:
        self.path = Path(path)

    def is_triggered(self) -> bool:
        return self.path.exists()

    def trigger(self) -> None:
        self.path.write_text("triggered\n")
        logger.warning("kill switch triggered at %s", self.path)

    def clear(self) -> None:
        if self.path.exists():
            self.path.unlink()
            logger.info("kill switch cleared")


def preflight_live(
    exchange,
    symbol: str,
    min_balance: float = 10.0,
) -> tuple[bool, str]:
    """
    Pre-flight checks before going live.

    Returns (ok, message). If ok is False, the caller must not proceed.
    """
    # 1. keys present?
    api_key = getattr(exchange, "client", None)
    if api_key is None:
        return False, "exchange client missing"

    creds = getattr(exchange.client, "apiKey", None)
    if not creds:
        return False, "API key missing (check .env)"

    # 2. can we reach the exchange?
    try:
        exchange.client.load_markets()
    except Exception as e:
        return False, f"cannot reach exchange: {e}"

    # 3. do we have a balance?
    try:
        bal = exchange.client.fetch_balance()
    except Exception as e:
        return False, f"cannot fetch balance: {e}"

    base = symbol.split("/")[0]
    quote = symbol.split("/")[1] if "/" in symbol else "USDT"
    free_quote = (bal.get("free") or {}).get(quote, 0.0)

    if free_quote < min_balance:
        return False, (
            f"insufficient {quote} balance: "
            f"{free_quote:.4f} < {min_balance:.4f}"
        )

    return True, f"ok (free {quote}: {free_quote:.4f})"


def summarize_balances(exchange, quote: str = "USDT") -> Optional[dict]:
    """Best-effort balance summary. Returns None if the call fails."""
    try:
        bal = exchange.client.fetch_balance()
    except Exception as e:
        logger.error("balance fetch failed: %s", e)
        return None
    free = (bal.get("free") or {})
    total = (bal.get("total") or {})
    return {
        "quote": quote,
        "free": float(free.get(quote, 0.0)),
        "total": float(total.get(quote, 0.0)),
    }