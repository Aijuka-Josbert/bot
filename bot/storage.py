"""
Persistent storage for runs, fills, equity curves and closed trades.

Design notes:
  - Uses stdlib sqlite3 only. No ORM. Schema is created on first open.
  - Every write is inside a transaction (atomic).
  - All timestamps stored as ISO 8601 strings (sortable, human-readable).
  - Enums stored as their string values, decoded back on read.
  - Deleting a run cascades to its children (FOREIGN KEY ... ON DELETE CASCADE).

Why sqlite?
  - Zero setup, single file, fast enough for millions of rows.
  - The lab will run hundreds of backtests and query them — sqlite handles it.
  - Easy to move to Postgres later if we need multi-user access.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from .models import ClosedTrade, Fill, Side
from .portfolio import Portfolio
from .strategy import Strategy


# ---------------------------------------------------------------------------
# Schema. One big string, executed idempotently with IF NOT EXISTS.
# ---------------------------------------------------------------------------
SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    name                TEXT    NOT NULL,
    strategy            TEXT    NOT NULL,
    symbol              TEXT    NOT NULL,
    params_json         TEXT    NOT NULL,
    started_at          TEXT    NOT NULL,
    finished_at         TEXT    NOT NULL,
    starting_balance    REAL    NOT NULL,
    final_equity        REAL    NOT NULL,
    realized_pnl        REAL    NOT NULL,
    total_fees          REAL    NOT NULL,
    candles_processed   INTEGER NOT NULL,
    error_count         INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS fills (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id      INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    timestamp   TEXT    NOT NULL,
    symbol      TEXT    NOT NULL,
    side        TEXT    NOT NULL,
    quantity    REAL    NOT NULL,
    price       REAL    NOT NULL,
    fee         REAL    NOT NULL,
    order_id    TEXT
);

CREATE TABLE IF NOT EXISTS equity_curve (
    run_id      INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    timestamp   TEXT    NOT NULL,
    equity      REAL    NOT NULL
);

CREATE TABLE IF NOT EXISTS closed_trades (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id      INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    symbol      TEXT    NOT NULL,
    side        TEXT    NOT NULL,
    quantity    REAL    NOT NULL,
    entry_price REAL    NOT NULL,
    exit_price  REAL    NOT NULL,
    pnl         REAL    NOT NULL,
    fees        REAL    NOT NULL,
    opened_at   TEXT    NOT NULL,
    closed_at   TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_fills_run    ON fills(run_id);
CREATE INDEX IF NOT EXISTS idx_equity_run   ON equity_curve(run_id);
CREATE INDEX IF NOT EXISTS idx_trades_run   ON closed_trades(run_id);
CREATE INDEX IF NOT EXISTS idx_runs_name    ON runs(name);
CREATE INDEX IF NOT EXISTS idx_runs_created ON runs(finished_at);
"""


def _iso(dt: Optional[datetime]) -> str:
    """Serialize a datetime to ISO 8601. Always UTC-aware on the way in."""
    if dt is None:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {k: row[k] for k in row.keys()}


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------
class Storage:
    def __init__(self, db_path: str | Path = "data/bot.db") -> None:
        self.db_path = Path(db_path)
        # Make sure the parent directory exists — sqlite won't create it.
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # check_same_thread=False so the lab can reuse one connection across
        # threads later. row_factory=Row gives us dict-like access.
        self.conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        # Enforce foreign keys (off by default in sqlite for legacy reasons).
        self.conn.execute("PRAGMA foreign_keys = ON;")
        # WAL = better concurrency when the lab writes in parallel.
        self.conn.execute("PRAGMA journal_mode = WAL;")
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    # ---- lifecycle ----

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "Storage":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # ---- write: one full run ----

    def save_run(
        self,
        *,
        name: str,
        strategy: Strategy,
        symbol: str,
        starting_balance: float,
        final_equity: float,
        realized_pnl: float,
        total_fees: float,
        candles_processed: int,
        error_count: int,
        fills: list[Fill],
        equity_curve: list[Any],          # list[EquityPoint] from engine.py
        closed_trades: list[ClosedTrade],
        started_at: Optional[datetime] = None,
        finished_at: Optional[datetime] = None,
    ) -> int:
        """
        Persist one run + its children inside a single transaction.
        Returns the new run_id.
        """
        started_at = started_at or datetime.now(timezone.utc)
        finished_at = finished_at or datetime.now(timezone.utc)
        params_json = json.dumps(strategy.params, sort_keys=True, default=str)

        cur = self.conn.cursor()
        try:
            cur.execute("BEGIN")

            # -- header row --
            cur.execute(
                """
                INSERT INTO runs (
                    name, strategy, symbol, params_json,
                    started_at, finished_at,
                    starting_balance, final_equity, realized_pnl,
                    total_fees, candles_processed, error_count
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    name, strategy.name, symbol, params_json,
                    _iso(started_at), _iso(finished_at),
                    starting_balance, final_equity, realized_pnl,
                    total_fees, candles_processed, error_count,
                ),
            )
            run_id = cur.lastrowid
            assert run_id is not None

            # -- fills --
            cur.executemany(
                """
                INSERT INTO fills (
                    run_id, timestamp, symbol, side,
                    quantity, price, fee, order_id
                ) VALUES (?,?,?,?,?,?,?,?)
                """,
                [
                    (
                        run_id, _iso(f.timestamp), f.symbol, f.side.value,
                        f.quantity, f.price, f.fee, f.order_id,
                    )
                    for f in fills
                ],
            )

            # -- equity curve --
            cur.executemany(
                "INSERT INTO equity_curve (run_id, timestamp, equity) VALUES (?,?,?)",
                [(run_id, _iso(p.timestamp), p.equity) for p in equity_curve],
            )

            # -- closed trades --
            cur.executemany(
                """
                INSERT INTO closed_trades (
                    run_id, symbol, side, quantity,
                    entry_price, exit_price, pnl, fees,
                    opened_at, closed_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?)
                """,
                [
                    (
                        run_id, t.symbol, t.side.value, t.quantity,
                        t.entry_price, t.exit_price, t.pnl, t.fees,
                        _iso(t.opened_at), _iso(t.closed_at),
                    )
                    for t in closed_trades
                ],
            )

            self.conn.commit()
            return run_id

        except Exception:
            self.conn.rollback()
            raise

    # ---- read ----

    def list_runs(self, limit: int = 50) -> list[dict]:
        """Newest runs first, without the child rows."""
        cur = self.conn.execute(
            """
            SELECT id, name, strategy, symbol,
                   started_at, finished_at,
                   starting_balance, final_equity,
                   realized_pnl, total_fees,
                   candles_processed, error_count
            FROM runs
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        )
        return [_row_to_dict(r) for r in cur.fetchall()]

    def get_run(self, run_id: int) -> Optional[dict]:
        cur = self.conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,))
        row = cur.fetchone()
        if row is None:
            return None
        d = _row_to_dict(row)
        d["params"] = json.loads(d.pop("params_json"))
        return d

    def get_fills(self, run_id: int) -> list[dict]:
        cur = self.conn.execute(
            "SELECT * FROM fills WHERE run_id = ? ORDER BY id", (run_id,)
        )
        return [_row_to_dict(r) for r in cur.fetchall()]

    def get_equity_curve(self, run_id: int) -> list[dict]:
        cur = self.conn.execute(
            "SELECT timestamp, equity FROM equity_curve WHERE run_id = ? ORDER BY timestamp",
            (run_id,),
        )
        return [_row_to_dict(r) for r in cur.fetchall()]

    def get_closed_trades(self, run_id: int) -> list[dict]:
        cur = self.conn.execute(
            "SELECT * FROM closed_trades WHERE run_id = ? ORDER BY id", (run_id,)
        )
        return [_row_to_dict(r) for r in cur.fetchall()]

    # ---- maintenance ----

    def delete_run(self, run_id: int) -> bool:
        cur = self.conn.execute("DELETE FROM runs WHERE id = ?", (run_id,))
        self.conn.commit()
        return cur.rowcount > 0

    def count_runs(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0]