"""SQLite persistence: decisions journal, trades, MT5 orders (idempotency), reviews, settings."""
from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Optional

log = logging.getLogger("quantpilot.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    instrument TEXT,
    signal_id TEXT,
    outcome TEXT NOT NULL,
    summary TEXT,
    trace TEXT
);
CREATE TABLE IF NOT EXISTS trades (
    id TEXT PRIMARY KEY,
    signal_id TEXT,
    instrument TEXT,
    direction TEXT,
    venue TEXT,
    ticket INTEGER,
    volume REAL,
    entry REAL,
    exit REAL,
    pnl REAL,
    opened_at REAL,
    closed_at REAL,
    reason TEXT
);
CREATE TABLE IF NOT EXISTS mt5_orders (
    signal_id TEXT PRIMARY KEY,
    ts REAL NOT NULL,
    ticket INTEGER,
    status TEXT NOT NULL,
    retcode INTEGER,
    message TEXT,
    price REAL,
    request TEXT
);
CREATE TABLE IF NOT EXISTS mt5_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    kind TEXT,
    symbol TEXT,
    retcode INTEGER,
    ticket INTEGER,
    price REAL,
    volume REAL,
    message TEXT,
    request TEXT
);
CREATE TABLE IF NOT EXISTS reviews (
    day TEXT PRIMARY KEY,
    ts REAL NOT NULL,
    text TEXT
);
CREATE TABLE IF NOT EXISTS kv (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""


class Database:
    """Thread-safe thin wrapper over sqlite3."""

    def __init__(self, path: str) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock:
            self._conn.executescript(SCHEMA)
            self._conn.commit()

    def _exec(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        with self._lock:
            cur = self._conn.execute(sql, params)
            self._conn.commit()
            return cur

    def _all(self, sql: str, params: tuple = ()) -> list[dict]:
        with self._lock:
            return [dict(r) for r in self._conn.execute(sql, params).fetchall()]

    # ---------------------------------------------------------------- decisions
    def log_decision(self, instrument: str, signal_id: Optional[str], outcome: str, summary: str, trace: list[dict]) -> int:
        cur = self._exec(
            "INSERT INTO decisions (ts, instrument, signal_id, outcome, summary, trace) VALUES (?,?,?,?,?,?)",
            (time.time(), instrument, signal_id, outcome, summary, json.dumps(trace, default=str)),
        )
        return int(cur.lastrowid or 0)

    def decisions(self, limit: int = 200, outcome: Optional[str] = None) -> list[dict]:
        if outcome:
            rows = self._all("SELECT * FROM decisions WHERE outcome=? ORDER BY id DESC LIMIT ?", (outcome, limit))
        else:
            rows = self._all("SELECT * FROM decisions ORDER BY id DESC LIMIT ?", (limit,))
        for r in rows:
            r["trace"] = json.loads(r["trace"] or "[]")
        return rows

    def decisions_since(self, ts: float) -> list[dict]:
        rows = self._all("SELECT * FROM decisions WHERE ts>=? ORDER BY id", (ts,))
        for r in rows:
            r["trace"] = json.loads(r["trace"] or "[]")
        return rows

    # ---------------------------------------------------------------- trades
    def record_trade(self, p: dict) -> None:
        self._exec(
            "INSERT OR REPLACE INTO trades VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (p["id"], p["signal_id"], p["instrument"], p["direction"], p.get("venue", "paper"), p.get("ticket"),
             p["initial_volume"], p["entry_price"], p.get("exit_price"), p.get("realized_pnl", 0.0),
             p["opened_at"], p.get("closed_at"), p.get("close_reason")),
        )

    def trades(self, limit: int = 500) -> list[dict]:
        return self._all("SELECT * FROM trades ORDER BY closed_at DESC LIMIT ?", (limit,))

    def trades_since(self, ts: float) -> list[dict]:
        return self._all("SELECT * FROM trades WHERE closed_at>=?", (ts,))

    # ---------------------------------------------------------------- MT5 idempotency
    def claim_signal(self, signal_id: str, request: dict) -> bool:
        """Atomically reserve a signal for MT5 execution. False if it was already claimed."""
        try:
            self._exec(
                "INSERT INTO mt5_orders (signal_id, ts, status, request) VALUES (?,?,?,?)",
                (signal_id, time.time(), "pending", json.dumps(request, default=str)),
            )
            return True
        except sqlite3.IntegrityError:
            return False

    def finish_signal(self, signal_id: str, status: str, retcode: Optional[int], message: str, ticket: Optional[int], price: Optional[float]) -> None:
        self._exec(
            "UPDATE mt5_orders SET status=?, retcode=?, message=?, ticket=?, price=? WHERE signal_id=?",
            (status, retcode, message, ticket, price, signal_id),
        )

    def signal_order(self, signal_id: str) -> Optional[dict]:
        rows = self._all("SELECT * FROM mt5_orders WHERE signal_id=?", (signal_id,))
        return rows[0] if rows else None

    def log_mt5(self, kind: str, symbol: str, retcode: Optional[int], ticket: Optional[int], price: Optional[float],
                volume: Optional[float], message: str, request: Optional[dict] = None) -> dict:
        row = {"ts": time.time(), "kind": kind, "symbol": symbol, "retcode": retcode, "ticket": ticket,
               "price": price, "volume": volume, "message": message, "request": json.dumps(request or {}, default=str)}
        self._exec(
            "INSERT INTO mt5_log (ts, kind, symbol, retcode, ticket, price, volume, message, request) VALUES (?,?,?,?,?,?,?,?,?)",
            tuple(row.values()),
        )
        return row

    def mt5_log(self, limit: int = 100) -> list[dict]:
        return self._all("SELECT * FROM mt5_log ORDER BY id DESC LIMIT ?", (limit,))

    # ---------------------------------------------------------------- reviews / kv
    def save_review(self, day: str, text: str) -> None:
        self._exec("INSERT OR REPLACE INTO reviews VALUES (?,?,?)", (day, time.time(), text))

    def reviews(self, limit: int = 30) -> list[dict]:
        return self._all("SELECT * FROM reviews ORDER BY day DESC LIMIT ?", (limit,))

    def kv_get(self, key: str, default: Any = None) -> Any:
        rows = self._all("SELECT value FROM kv WHERE key=?", (key,))
        return json.loads(rows[0]["value"]) if rows else default

    def kv_set(self, key: str, value: Any) -> None:
        self._exec("INSERT OR REPLACE INTO kv VALUES (?,?)", (key, json.dumps(value, default=str)))
