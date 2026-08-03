"""SQLite-backed persistence for open position, trade history and daily
risk counters. A file-based DB (rather than in-memory state) means the
bot can be killed and restarted without losing track of an open position
or already-hit daily loss limit.
"""
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

SCHEMA = """
CREATE TABLE IF NOT EXISTS position (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    symbol TEXT NOT NULL,
    entry_price REAL NOT NULL,
    quantity REAL NOT NULL,
    stop_price REAL NOT NULL,
    take_profit_price REAL NOT NULL,
    opened_at TEXT NOT NULL,
    order_id TEXT
);

CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    entry_price REAL NOT NULL,
    exit_price REAL NOT NULL,
    quantity REAL NOT NULL,
    opened_at TEXT NOT NULL,
    closed_at TEXT NOT NULL,
    pnl_quote REAL NOT NULL,
    pnl_pct REAL NOT NULL,
    fee_quote REAL NOT NULL DEFAULT 0,
    exit_reason TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS daily_stats (
    trade_date TEXT PRIMARY KEY,
    starting_equity REAL NOT NULL,
    realized_pnl REAL NOT NULL DEFAULT 0,
    trades_count INTEGER NOT NULL DEFAULT 0,
    halted INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


@dataclass
class Position:
    symbol: str
    entry_price: float
    quantity: float
    stop_price: float
    take_profit_price: float
    opened_at: str
    order_id: Optional[str]


class StateStore:
    def __init__(self, db_path: str):
        self.db_path = db_path
        with self._conn() as conn:
            conn.executescript(SCHEMA)

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    # ---------- position ----------

    def get_open_position(self) -> Optional[Position]:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM position WHERE id = 1").fetchone()
        if row is None:
            return None
        return Position(
            symbol=row["symbol"], entry_price=row["entry_price"], quantity=row["quantity"],
            stop_price=row["stop_price"], take_profit_price=row["take_profit_price"],
            opened_at=row["opened_at"], order_id=row["order_id"],
        )

    def open_position(self, symbol: str, entry_price: float, quantity: float,
                       stop_price: float, take_profit_price: float, order_id: str = "") -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO position "
                "(id, symbol, entry_price, quantity, stop_price, take_profit_price, opened_at, order_id) "
                "VALUES (1, ?, ?, ?, ?, ?, ?, ?)",
                (symbol, entry_price, quantity, stop_price, take_profit_price,
                 datetime.now(timezone.utc).isoformat(), order_id),
            )

    def close_position(self, exit_price: float, exit_reason: str, fee_quote: float = 0.0) -> dict:
        pos = self.get_open_position()
        if pos is None:
            raise RuntimeError("close_position called with no open position")
        pnl_quote = (exit_price - pos.entry_price) * pos.quantity - fee_quote
        pnl_pct = (exit_price - pos.entry_price) / pos.entry_price
        closed_at = datetime.now(timezone.utc).isoformat()
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO trades (symbol, entry_price, exit_price, quantity, opened_at, "
                "closed_at, pnl_quote, pnl_pct, fee_quote, exit_reason) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (pos.symbol, pos.entry_price, exit_price, pos.quantity, pos.opened_at,
                 closed_at, pnl_quote, pnl_pct, fee_quote, exit_reason),
            )
            conn.execute("DELETE FROM position WHERE id = 1")
        self.record_trade_pnl(pnl_quote)
        return {
            "symbol": pos.symbol, "entry_price": pos.entry_price, "exit_price": exit_price,
            "quantity": pos.quantity, "pnl_quote": pnl_quote, "pnl_pct": pnl_pct,
            "exit_reason": exit_reason,
        }

    # ---------- daily stats / risk halt ----------

    def _ensure_today_row(self, conn, starting_equity: float) -> None:
        conn.execute(
            "INSERT OR IGNORE INTO daily_stats (trade_date, starting_equity) VALUES (?, ?)",
            (_today(), starting_equity),
        )

    def get_today_stats(self, starting_equity: float) -> dict:
        with self._conn() as conn:
            self._ensure_today_row(conn, starting_equity)
            row = conn.execute(
                "SELECT * FROM daily_stats WHERE trade_date = ?", (_today(),)
            ).fetchone()
        return dict(row)

    def record_trade_pnl(self, pnl_quote: float) -> None:
        with self._conn() as conn:
            self._ensure_today_row(conn, 0.0)
            conn.execute(
                "UPDATE daily_stats SET realized_pnl = realized_pnl + ?, "
                "trades_count = trades_count + 1 WHERE trade_date = ?",
                (pnl_quote, _today()),
            )

    def set_halted_today(self) -> None:
        with self._conn() as conn:
            self._ensure_today_row(conn, 0.0)
            conn.execute("UPDATE daily_stats SET halted = 1 WHERE trade_date = ?", (_today(),))

    def is_halted_today(self) -> bool:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT halted FROM daily_stats WHERE trade_date = ?", (_today(),)
            ).fetchone()
        return bool(row["halted"]) if row else False

    # ---------- cooldown / last processed candle ----------

    def get_meta(self, key: str) -> Optional[str]:
        with self._conn() as conn:
            row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else None

    def set_meta(self, key: str, value: str) -> None:
        with self._conn() as conn:
            conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", (key, value))

    # ---------- metrics reporting ----------

    def compute_metrics(self) -> dict:
        with self._conn() as conn:
            rows = conn.execute("SELECT * FROM trades ORDER BY closed_at ASC").fetchall()
        trades = [dict(r) for r in rows]
        if not trades:
            return {
                "total_trades": 0, "win_rate": 0.0, "avg_win": 0.0, "avg_loss": 0.0,
                "net_profit": 0.0, "max_drawdown": 0.0, "fees_paid": 0.0,
            }
        wins = [t["pnl_quote"] for t in trades if t["pnl_quote"] > 0]
        losses = [t["pnl_quote"] for t in trades if t["pnl_quote"] <= 0]
        cumulative, running_max, max_dd = 0.0, 0.0, 0.0
        for t in trades:
            cumulative += t["pnl_quote"]
            running_max = max(running_max, cumulative)
            max_dd = max(max_dd, running_max - cumulative)
        return {
            "total_trades": len(trades),
            "win_rate": len(wins) / len(trades),
            "avg_win": sum(wins) / len(wins) if wins else 0.0,
            "avg_loss": sum(losses) / len(losses) if losses else 0.0,
            "net_profit": sum(t["pnl_quote"] for t in trades),
            "max_drawdown": max_dd,
            "fees_paid": sum(t["fee_quote"] for t in trades),
        }
