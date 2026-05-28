import sqlite3
import json
from pathlib import Path
from datetime import datetime, date
from typing import Optional, List
import pandas as pd

from src.core.base import TradeSignal, Order, Position


DB_PATH = Path(__file__).parent.parent.parent / "data" / "stock_monitor.db"


def get_conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_database():
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS kline_data (
            code TEXT NOT NULL,
            period TEXT NOT NULL DEFAULT 'daily',
            date TEXT NOT NULL,
            open REAL, close REAL, high REAL, low REAL, volume REAL,
            PRIMARY KEY (code, period, date)
        );
        CREATE TABLE IF NOT EXISTS signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL, name TEXT,
            timestamp TEXT NOT NULL,
            action TEXT, score REAL, price REAL,
            technical_score REAL, capital_score REAL,
            news_score REAL, fundamental_score REAL,
            confidence REAL, position_pct REAL,
            stop_loss REAL, take_profit_1 REAL, take_profit_2 REAL,
            reasons TEXT,
            strategy_name TEXT DEFAULT '',
            is_backtest INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL, name TEXT,
            direction TEXT NOT NULL,
            price REAL, volume INTEGER, amount REAL,
            timestamp TEXT NOT NULL,
            signal_id INTEGER,
            fee REAL DEFAULT 0,
            note TEXT
        );
        CREATE TABLE IF NOT EXISTS positions (
            code TEXT PRIMARY KEY,
            name TEXT,
            volume INTEGER NOT NULL DEFAULT 0,
            cost_price REAL NOT NULL DEFAULT 0,
            current_price REAL DEFAULT 0,
            profit_pct REAL DEFAULT 0,
            profit_amount REAL DEFAULT 0,
            updated_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_kline_code_period ON kline_data(code, period);
        CREATE INDEX IF NOT EXISTS idx_signals_code ON signals(code);
        CREATE INDEX IF NOT EXISTS idx_signals_timestamp ON signals(timestamp);
        CREATE INDEX IF NOT EXISTS idx_trades_code ON trades(code);
    """)
    conn.commit()
    conn.close()


class KlineStore:
    def save_kline(self, code: str, period: str, df: pd.DataFrame):
        if df.empty:
            return
        conn = get_conn()
        data = []
        for idx, row in df.iterrows():
            date_str = idx if isinstance(idx, str) else idx.strftime("%Y-%m-%d")
            data.append((
                code, period, date_str,
                float(row.get("open", 0)), float(row.get("close", 0)),
                float(row.get("high", 0)), float(row.get("low", 0)),
                float(row.get("volume", 0)),
            ))
        conn.executemany(
            """INSERT OR REPLACE INTO kline_data
               (code, period, date, open, close, high, low, volume)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            data,
        )
        conn.commit()
        conn.close()

    def load_kline(self, code: str, period: str = "daily",
                   start: str = "", end: str = "") -> pd.DataFrame:
        conn = get_conn()
        query = ("SELECT date, open, close, high, low, volume "
                 "FROM kline_data WHERE code=? AND period=?")
        params = [code, period]
        if start:
            query += " AND date>=?"
            params.append(start)
        if end:
            query += " AND date<=?"
            params.append(end)
        query += " ORDER BY date ASC"
        df = pd.read_sql_query(query, conn, params=params)
        conn.close()
        if df.empty:
            return df
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date").sort_index()
        for col in ["open", "close", "high", "low", "volume"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        return df

    def has_data(self, code: str, period: str, date_str: str) -> bool:
        conn = get_conn()
        cur = conn.execute(
            "SELECT COUNT(*) FROM kline_data WHERE code=? AND period=? AND date=?",
            (code, period, date_str),
        )
        count = cur.fetchone()[0]
        conn.close()
        return count > 0

    def get_latest_date(self, code: str, period: str) -> Optional[str]:
        conn = get_conn()
        cur = conn.execute(
            "SELECT MAX(date) FROM kline_data WHERE code=? AND period=?",
            (code, period),
        )
        row = cur.fetchone()[0]
        conn.close()
        return row


class SignalStore:
    def save_signal(self, signal: TradeSignal, is_backtest: int = 0) -> int:
        conn = get_conn()
        conn.execute(
            """INSERT INTO signals
               (code, name, timestamp, action, score, price,
                technical_score, capital_score, news_score, fundamental_score,
                confidence, position_pct, stop_loss, take_profit_1, take_profit_2,
                reasons, strategy_name, is_backtest)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                signal.code, signal.name, signal.timestamp, signal.action,
                signal.score, signal.price, signal.technical_score,
                signal.capital_score, signal.news_score, signal.fundamental_score,
                signal.confidence, signal.position_pct, signal.stop_loss,
                signal.take_profit_1, signal.take_profit_2,
                json.dumps(signal.reasons, ensure_ascii=False),
                signal.strategy_name, is_backtest,
            ),
        )
        conn.commit()
        signal_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.close()
        return signal_id

    def get_signals(self, code: str = "", limit: int = 100) -> List[dict]:
        conn = get_conn()
        query = "SELECT * FROM signals"
        params = []
        if code:
            query += " WHERE code=?"
            params.append(code)
        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)
        cur = conn.execute(query, params)
        rows = [dict(row) for row in cur.fetchall()]
        conn.close()
        return rows


class TradeStore:
    def save_order(self, order: Order) -> int:
        conn = get_conn()
        cur = conn.execute(
            """INSERT INTO trades
               (code, name, direction, price, volume, amount,
                timestamp, signal_id, fee, note)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                order.code, order.name, order.direction, order.price,
                order.volume, order.amount, order.created_at,
                order.signal_id, order.fee, order.reason,
            ),
        )
        conn.commit()
        order_id = cur.lastrowid
        conn.close()
        return order_id

    def get_trades(self, code: str = "", limit: int = 100) -> List[dict]:
        conn = get_conn()
        query = "SELECT * FROM trades"
        params = []
        if code:
            query += " WHERE code=?"
            params.append(code)
        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)
        cur = conn.execute(query, params)
        rows = [dict(row) for row in cur.fetchall()]
        conn.close()
        return rows


class PositionStore:
    def save_position(self, pos: Position):
        conn = get_conn()
        conn.execute(
            """INSERT OR REPLACE INTO positions
               (code, name, volume, cost_price, current_price,
                profit_pct, profit_amount, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                pos.code, pos.name, pos.volume, pos.cost_price,
                pos.current_price, pos.profit_pct, pos.profit_amount,
                pos.updated_at,
            ),
        )
        conn.commit()
        conn.close()

    def get_all_positions(self) -> List[dict]:
        conn = get_conn()
        cur = conn.execute("SELECT * FROM positions ORDER BY profit_amount DESC")
        rows = [dict(row) for row in cur.fetchall()]
        conn.close()
        return rows

    def get_position(self, code: str) -> Optional[dict]:
        conn = get_conn()
        cur = conn.execute("SELECT * FROM positions WHERE code=?", (code,))
        row = cur.fetchone()
        conn.close()
        return dict(row) if row else None
