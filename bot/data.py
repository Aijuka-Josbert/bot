"""Candle loaders: CSV, synthetic, and exchange download."""
from __future__ import annotations

import csv
import math
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, Optional

from .models import Candle


# --- helpers ---

def _parse_ts(raw: str) -> datetime:
    """Accept ISO-8601 or epoch milliseconds."""
    raw = raw.strip()
    if raw.isdigit():
        return datetime.fromtimestamp(int(raw) / 1000.0, tz=timezone.utc)
    dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


# --- CSV ---

def load_csv(path: str | Path) -> list[Candle]:
    """
    Read candles from a CSV with columns:
        timestamp,open,high,low,close,volume
    Header row is required. Rows are returned in file order.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(path)

    out: list[Candle] = []
    with path.open() as f:
        reader = csv.DictReader(f)
        required = {"timestamp", "open", "high", "low", "close", "volume"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"CSV missing columns: {sorted(missing)}")
        for row in reader:
            out.append(Candle(
                timestamp=_parse_ts(row["timestamp"]),
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=float(row["volume"]),
            ))
    return out


# --- synthetic ---

def generate_synthetic(
    n: int = 1000,
    start_price: float = 30_000.0,
    drift: float = 0.0,
    volatility: float = 0.005,
    start_time: Optional[datetime] = None,
    step_seconds: int = 60,
    seed: Optional[int] = None,
) -> list[Candle]:
    """
    Geometric Brownian Motion candle generator.

    Each step multiplies the price by exp(drift + volatility * N(0,1)).
    High/low are derived from the intrabar range so they always contain open/close.
    """
    if n <= 0:
        raise ValueError("n must be > 0")
    if start_price <= 0:
        raise ValueError("start_price must be > 0")
    if volatility < 0:
        raise ValueError("volatility must be >= 0")

    rng = random.Random(seed)
    t0 = start_time or datetime.now(timezone.utc)
    price = float(start_price)
    candles: list[Candle] = []

    for i in range(n):
        ts = t0 + timedelta(seconds=step_seconds * i)
        open_ = price
        shock = rng.gauss(0.0, 1.0)
        close = open_ * math.exp(drift + volatility * shock)
        wick = abs(close - open_) * rng.uniform(0.2, 1.0)
        high = max(open_, close) + wick
        low = min(open_, close) - wick
        volume = rng.uniform(1.0, 100.0)
        candles.append(Candle(ts, open_, high, low, close, volume))
        price = close

    return candles


# --- exchange download ---

def download_ccxt(
    symbol: str,
    timeframe: str = "1m",
    since_iso: Optional[str] = None,
    limit: int = 1000,
    exchange_name: str = "binance",
) -> list[Candle]:
    """
    Download OHLCV from ccxt. Requires network and the `ccxt` package.
    `since_iso` is an ISO date string; defaults to 30 days back.
    """
    import ccxt  # local import so the rest of the module works offline

    exchange_cls = getattr(ccxt, exchange_name)
    ex = exchange_cls({"enableRateLimit": True})

    since_dt = (
        datetime.fromisoformat(since_iso).replace(tzinfo=timezone.utc)
        if since_iso else datetime.now(timezone.utc) - timedelta(days=30)
    )
    since_ms = int(since_dt.timestamp() * 1000)

    raw = ex.fetch_ohlcv(symbol, timeframe=timeframe, since=since_ms, limit=limit)
    return [
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