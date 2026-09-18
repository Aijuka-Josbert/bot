"""Exchange factory. Chooses paper or live based on config."""
from __future__ import annotations

from typing import Optional

from ..config import Config
from ..exchange import PaperExchange
from .ccxt_exchange import CcxtExchange

__all__ = ["make_exchange", "CcxtExchange", "PaperExchange"]


def make_exchange(
    cfg: Config,
    force_mode: Optional[str] = None,
    dry_run: bool = False,
):
    """
    Return an exchange for the given config.

    force_mode="paper"  -> PaperExchange (safe, no network)
    force_mode="live"   -> CcxtExchange (real orders unless dry_run)
    force_mode=None     -> use cfg.bot.mode
    """
    mode = force_mode or cfg.bot.mode
    if mode == "paper":
        return PaperExchange(
            fee_rate=cfg.risk.fee_rate,
            slippage_bps=cfg.risk.slippage_bps,
        )
    if mode == "live":
        return CcxtExchange(
            name=cfg.exchange.name,
            symbol=cfg.market.symbol,
            timeframe=cfg.market.timeframe,
            api_key=cfg.exchange.api_key,
            api_secret=cfg.exchange.api_secret,
            testnet=cfg.exchange.testnet,
            dry_run=dry_run,
            fee_rate=cfg.risk.fee_rate,
            slippage_bps=cfg.risk.slippage_bps,
        )
    raise ValueError(f"unknown mode: {mode!r}")