# A股量化交易系统重构实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将现有A股监控系统重构为完整的量化交易系统，包含回测、风控、策略管理、绩效分析

**Architecture:** 四层架构（数据层→策略层→风控层→执行层），SQLite统一存储，信号总线解耦

**Tech Stack:** Python 3.11+, SQLite, Pandas, Plotly, Streamlit, akshare

---

## 文件结构总览

```
src/
├── core/
│   ├── base.py              # 基础类型：TradeSignal, Order, Position, StrategySignal
│   └── config.py             # 配置管理
├── data/
│   ├── collector.py          # [保留改造] 行情采集
│   ├── news.py               # [保留] 新闻采集
│   ├── store.py              # [新增] SQLite存储
│   ├── cache.py              # [新增] 内存缓存
│   └── manager.py            # [新增] 数据调度
├── strategy/
│   ├── base.py               # [新增] 策略基类
│   ├── technical.py          # [新增] 技术策略(多时间框架)
│   ├── capital_flow.py       # [新增] 资金流策略
│   ├── news_sentiment.py     # [新增] 新闻情绪策略
│   └── ensemble.py           # [新增] 集成策略
├── risk/
│   ├── manager.py            # [新增] 风控管理器
│   └── rules.py              # [新增] 风控规则集合
├── execution/
│   ├── order.py              # [新增] 订单模型
│   ├── broker.py             # [新增] 券商接口(Mock)
│   └── position.py           # [新增] 持仓管理
├── engine/
│   ├── signal_bus.py         # [新增] 信号总线
│   ├── backtest.py           # [新增] 回测引擎
│   └── live.py               # [新增] 实盘引擎
├── analytics/
│   ├── metrics.py            # [新增] 绩效指标
│   └── report.py             # [新增] 报告生成
├── analysis/
│   ├── technical.py          # [保留] 旧技术分析(过渡)
│   └── signal_engine.py      # [保留] 旧信号引擎(过渡)
├── llm/
│   └── client.py             # [保留] LLM客户端
├── notify/
│   └── notifier.py           # [保留] 通知推送(全保留)
└── web/
    ├── app.py                # [新增] 主面板
    ├── dashboard.py          # [保留] 旧面板
    └── pages/
        ├── backtest.py       # [新增] 回测页面
        └── analytics.py      # [新增] 绩效页面
```

---

## Phase 1: 基础设施

### Task 1.1: 核心类型定义

**Files:**
- Create: `src/core/__init__.py`
- Create: `src/core/base.py`
- Create: `src/core/config.py`

- [ ] **Step 1: Create `src/core/__init__.py`** (空文件)
- [ ] **Step 2: Create `src/core/base.py`** with all core data types

```python
from dataclasses import dataclass, field
from typing import Optional, Literal
from datetime import datetime


ActionType = Literal["strong_buy", "buy", "hold", "sell", "strong_sell"]
OrderDirection = Literal["buy", "sell"]
OrderType = Literal["market", "limit"]
PeriodType = Literal["daily", "weekly", "monthly", "60min", "15min"]
RegimeType = Literal["bull", "oscillate", "bear"]


@dataclass
class TradeSignal:
    code: str
    name: str
    timestamp: str
    action: ActionType
    score: float
    technical_score: float
    capital_score: float
    news_score: float
    fundamental_score: float
    confidence: float
    strategy_name: str = ""
    reasons: list = field(default_factory=list)
    stop_loss: float = 0.0
    take_profit_1: float = 0.0
    take_profit_2: float = 0.0
    position_pct: float = 0.0
    price: float = 0.0
    support_levels: list = field(default_factory=list)
    resistance_levels: list = field(default_factory=list)


@dataclass
class StrategySignal:
    code: str
    name: str
    strategy_name: str
    action: ActionType
    score: float
    confidence: float
    detail: dict = field(default_factory=dict)
    timestamp: str = ""


@dataclass
class Order:
    code: str
    name: str
    direction: OrderDirection
    order_type: OrderType
    price: float
    volume: int
    amount: float
    reason: str = ""
    signal_id: Optional[int] = None
    status: str = "pending"
    created_at: str = ""
    executed_at: str = ""
    fee: float = 0.0


@dataclass
class Position:
    code: str
    name: str
    volume: int
    cost_price: float
    current_price: float = 0.0
    market_value: float = 0.0
    profit_pct: float = 0.0
    profit_amount: float = 0.0
    updated_at: str = ""


@dataclass
class BacktestResult:
    total_return: float = 0.0
    annual_return: float = 0.0
    max_drawdown: float = 0.0
    sharpe_ratio: float = 0.0
    win_rate: float = 0.0
    profit_loss_ratio: float = 0.0
    total_trades: int = 0
    equity_curve: list = field(default_factory=list)


@dataclass
class BarData:
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    code: str = ""
    period: PeriodType = "daily"
```

- [ ] **Step 3: Create `src/core/config.py`**

```python
from pathlib import Path
from typing import Any
import yaml


class Settings:
    _instance = None
    _data: dict = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def load(self, path: str = "config/settings.yaml") -> dict:
        config_path = Path(__file__).parent.parent.parent / path
        with open(config_path, "r", encoding="utf-8") as f:
            self._data = yaml.safe_load(f) or {}
        return self._data

    @property
    def data(self) -> dict:
        return self._data

    def get(self, key: str, default: Any = None) -> Any:
        keys = key.split(".")
        val = self._data
        for k in keys:
            if isinstance(val, dict):
                val = val.get(k)
            else:
                return default
        return val if val is not None else default

    def get_watchlist(self) -> list:
        return self._data.get("watchlist", {}).get("stocks", [])

    def get_funds(self) -> list:
        return self._data.get("watchlist", {}).get("funds", [])

    def get_notify_config(self) -> dict:
        return self._data.get("notify", {})

    def get_llm_config(self) -> dict:
        return self._data.get("llm", {})


settings = Settings()
```

---

### Task 1.2: 数据存储层

**Files:**
- Create: `src/data/store.py`

- [ ] **Step 1: Create `src/data/store.py`**

```python
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
        query = "SELECT date, open, close, high, low, volume FROM kline_data WHERE code=? AND period=?"
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
    def save_signal(self, signal: TradeSignal, is_backtest: int = 0):
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
```

- [ ] **Step 2: Create SQLite schema initialization**

```python
# 在 store.py 中增加 init_database() 函数
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
```

---

### Task 1.3: 内存缓存层

**Files:**
- Create: `src/data/cache.py`

- [ ] **Step 1: Create `src/data/cache.py`**

```python
import time
from typing import Any, Optional


class DataCache:
    def __init__(self, default_ttl: int = 60):
        self._store: dict[str, tuple[Any, float]] = {}
        self._default_ttl = default_ttl

    def get(self, key: str) -> Optional[Any]:
        if key not in self._store:
            return None
        value, expire_at = self._store[key]
        if time.time() > expire_at:
            del self._store[key]
            return None
        return value

    def set(self, key: str, value: Any, ttl: Optional[int] = None):
        ttl = ttl if ttl is not None else self._default_ttl
        self._store[key] = (value, time.time() + ttl)

    def invalidate(self, pattern: str = ""):
        if not pattern:
            self._store.clear()
            return
        keys = [k for k in self._store if pattern in k]
        for k in keys:
            del self._store[k]

    def get_or_set(self, key: str, fn, ttl: Optional[int] = None) -> Any:
        cached = self.get(key)
        if cached is not None:
            return cached
        value = fn()
        self.set(key, value, ttl)
        return value


cache = DataCache()
```

---

### Task 1.4: 数据管理器

**Files:**
- Create: `src/data/manager.py`

- [ ] **Step 1: Create `src/data/manager.py`**

```python
from typing import Optional
import pandas as pd
from datetime import datetime, timedelta

from src.data.collector import StockDataCollector
from src.data.news import NewsCollector
from src.data.store import KlineStore, init_database
from src.data.cache import cache


class DataManager:
    def __init__(self):
        self.collector = StockDataCollector()
        self.news = NewsCollector()
        self.kline_store = KlineStore()
        init_database()

    def get_realtime_quote(self, code: str) -> dict:
        return cache.get_or_set(
            f"quote:{code}",
            lambda: self.collector.get_realtime_quote(code),
            ttl=30,
        )

    def get_kline(self, code: str, period: str = "daily",
                  days: int = 250, force_refresh: bool = False) -> pd.DataFrame:
        df = self.kline_store.load_kline(code, period)
        if not df.empty and not force_refresh:
            latest = df.index[-1].strftime("%Y-%m-%d")
            today = datetime.now().strftime("%Y-%m-%d")
            if latest == today:
                return df

        df = self.collector.get_kline(code, period=period, days=days)
        if not df.empty:
            self.kline_store.save_kline(code, period, df)
        return df

    def get_fund_flow(self, code: str) -> dict:
        return cache.get_or_set(
            f"fund_flow:{code}",
            lambda: self.collector.get_fund_flow(code),
            ttl=300,
        )

    def get_market_index(self) -> dict:
        return cache.get_or_set(
            "market_index",
            lambda: self.collector.get_market_index(),
            ttl=60,
        )

    def get_stock_news(self, code: str, limit: int = 10) -> list:
        return self.news.get_stock_news(code, limit)

    def get_market_news(self, limit: int = 20) -> list:
        return self.news.get_market_news(limit)
```

---

## Phase 2: 策略系统

### Task 2.1: 策略基类

**Files:**
- Create: `src/strategy/__init__.py`
- Create: `src/strategy/base.py`

- [ ] **Step 1: Create `src/strategy/__init__.py`** (空)
- [ ] **Step 2: Create `src/strategy/base.py`**

```python
from abc import ABC, abstractmethod
from typing import Dict, List
from dataclasses import dataclass

from src.core.base import StrategySignal


class BaseStrategy(ABC):
    name: str = ""
    weight: float = 1.0

    @abstractmethod
    def generate(self, data: Dict) -> StrategySignal:
        ...

    @abstractmethod
    def get_required_data(self) -> List[str]:
        ...
```

---

### Task 2.2: 技术策略（多时间框架）

**Files:**
- Create: `src/strategy/technical.py`

- [ ] **Step 1: Create `src/strategy/technical.py`**

```python
import pandas as pd
import numpy as np
from typing import Dict, List, Optional
from datetime import datetime

from src.strategy.base import BaseStrategy
from src.core.base import StrategySignal, RegimeType


def detect_market_regime(index_kline: pd.DataFrame) -> RegimeType:
    if index_kline.empty or len(index_kline) < 120:
        return "oscillate"
    close = index_kline["close"]
    ma120 = close.rolling(120).mean().iloc[-1]
    ma60 = close.rolling(60).mean().iloc[-1]
    price = close.iloc[-1]
    if price > ma120 and ma60 > ma120:
        return "bull"
    elif price < ma120 and ma60 < ma120:
        return "bear"
    return "oscillate"


class TechnicalStrategy(BaseStrategy):
    name = "technical"
    weight = 0.4

    def get_required_data(self) -> List[str]:
        return ["kline_daily"]

    def generate(self, data: Dict) -> StrategySignal:
        df = data.get("kline_daily")
        code = data.get("code", "")
        name = data.get("name", "")
        price = data.get("price", 0)

        if df is None or df.empty or len(df) < 60:
            return StrategySignal(
                code=code, name=name, strategy_name=self.name,
                action="hold", score=0, confidence=0,
                detail={"error": "数据不足"},
            )

        regime = detect_market_regime(df)
        trend_score = self._analyze_trend(df, price)
        momentum_score = self._analyze_momentum(df)
        volume_score = self._analyze_volume(df)
        total = trend_score + momentum_score + volume_score

        regime_multiplier = {"bull": 1.0, "oscillate": 0.8, "bear": 0.6}
        total *= regime_multiplier.get(regime, 1.0)

        score = max(min(total, 100), -100)

        if score >= 60:
            action = "strong_buy"
        elif score >= 30:
            action = "buy"
        elif score <= -60:
            action = "strong_sell"
        elif score <= -30:
            action = "sell"
        else:
            action = "hold"

        return StrategySignal(
            code=code, name=name, strategy_name=self.name,
            action=action, score=round(score, 1),
            confidence=round(min(abs(score), 100), 1),
            detail={"regime": regime, "trend": trend_score, "momentum": momentum_score},
            timestamp=datetime.now().isoformat(),
        )

    def _analyze_trend(self, df: pd.DataFrame, price: float) -> float:
        score = 0.0
        close = df["close"]
        ma5 = close.rolling(5).mean().iloc[-1]
        ma10 = close.rolling(10).mean().iloc[-1]
        ma20 = close.rolling(20).mean().iloc[-1]
        ma60 = close.rolling(60).mean().iloc[-1]

        if price > ma5 > ma10 > ma20 > ma60:
            score += 35
        elif price > ma5 > ma10 > ma20:
            score += 20
        elif price < ma5 < ma10 < ma20 < ma60:
            score -= 35
        elif price < ma5 < ma10 < ma20:
            score -= 20

        ema12 = close.ewm(span=12).mean()
        ema26 = close.ewm(span=26).mean()
        dif = ema12 - ema26
        dea = dif.ewm(span=9).mean()
        if len(dif) >= 2:
            if dif.iloc[-2] < dea.iloc[-2] and dif.iloc[-1] > dea.iloc[-1]:
                score += 15
            elif dif.iloc[-2] > dea.iloc[-2] and dif.iloc[-1] < dea.iloc[-1]:
                score -= 15
        return max(min(score, 50), -50)

    def _analyze_momentum(self, df: pd.DataFrame) -> float:
        score = 0.0
        close = df["close"]
        delta = close.diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        avg_gain = gain.rolling(14).mean()
        avg_loss = loss.rolling(14).mean()
        rs = avg_gain / avg_loss.replace(0, np.nan)
        rsi = 100 - (100 / (1 + rs))
        rsi_val = rsi.iloc[-1]
        if rsi_val < 30:
            score += 25
        elif rsi_val < 40:
            score += 10
        elif rsi_val > 70:
            score -= 25
        elif rsi_val > 60:
            score -= 10
        return max(min(score, 30), -30)

    def _analyze_volume(self, df: pd.DataFrame) -> float:
        score = 0.0
        vol = df["volume"]
        close = df["close"]
        vol_ma20 = vol.rolling(20).mean().iloc[-1]
        vol_ratio = vol.iloc[-1] / vol_ma20 if vol_ma20 > 0 else 1
        price_up = close.iloc[-1] > close.iloc[-2]
        if vol_ratio > 2.0 and price_up:
            score += 15
        elif vol_ratio > 1.5 and price_up:
            score += 8
        elif vol_ratio > 2.0 and not price_up:
            score -= 15
        return max(min(score, 20), -20)
```

---

### Task 2.3: 资金流策略

**Files:**
- Create: `src/strategy/capital_flow.py`

```python
from typing import Dict, List
from datetime import datetime

from src.strategy.base import BaseStrategy
from src.core.base import StrategySignal


class CapitalFlowStrategy(BaseStrategy):
    name = "capital_flow"
    weight = 0.2

    def get_required_data(self) -> List[str]:
        return ["fund_flow"]

    def generate(self, data: Dict) -> StrategySignal:
        code = data.get("code", "")
        name = data.get("name", "")
        fund_flow = data.get("fund_flow", {})
        if not fund_flow:
            return StrategySignal(
                code=code, name=name, strategy_name=self.name,
                action="hold", score=0, confidence=0,
            )
        main_net = fund_flow.get("main_net_inflow", 0)
        main_pct = fund_flow.get("main_net_pct", 0)
        if main_net > 0:
            score = min(main_pct * 5, 100)
            action = "buy" if score > 30 else "hold"
        else:
            score = max(main_pct * 5, -100)
            action = "sell" if score < -30 else "hold"
        return StrategySignal(
            code=code, name=name, strategy_name=self.name,
            action=action if abs(score) > 30 else "hold",
            score=round(score, 1),
            confidence=min(abs(score), 100),
            detail={"main_net": main_net, "main_pct": main_pct},
            timestamp=datetime.now().isoformat(),
        )
```

---

### Task 2.4: 集成策略

**Files:**
- Create: `src/strategy/ensemble.py`

```python
from typing import Dict, List
from datetime import datetime

from src.strategy.base import BaseStrategy
from src.core.base import StrategySignal, TradeSignal

ACTION_SCORE_MAP = {
    "strong_buy": 80, "buy": 50, "hold": 0, "sell": -50, "strong_sell": -80,
}


class EnsembleStrategy:
    def __init__(self, strategies: List[BaseStrategy]):
        self.strategies = strategies

    def generate(self, code: str, name: str, price: float, data: Dict) -> TradeSignal:
        signals: List[StrategySignal] = []
        for strategy in self.strategies:
            strategy_data = {
                k: v for k, v in data.items()
                if k in strategy.get_required_data()
            }
            strategy_data.update({"code": code, "name": name, "price": price})
            try:
                sig = strategy.generate(strategy_data)
                signals.append(sig)
            except Exception:
                continue

        if not signals:
            return TradeSignal(
                code=code, name=name, timestamp=datetime.now().isoformat(),
                action="hold", score=0, technical_score=0,
                capital_score=0, news_score=0, fundamental_score=0,
                confidence=0,
            )

        total_weight = sum(s.weight for s in self.strategies if any(
            ss.strategy_name == s.name for ss in signals
        )) or 1.0

        weighted_score = 0.0
        reasons = []
        for sig in signals:
            strat = next((s for s in self.strategies if s.name == sig.strategy_name), None)
            w = strat.weight if strat else 1.0
            weighted_score += sig.score * w / total_weight
            if abs(sig.score) > 20:
                reasons.append(f"{sig.strategy_name}: {sig.score:.0f}分")

        weighted_score = max(min(weighted_score, 100), -100)

        if weighted_score >= 60:
            action = "strong_buy"
        elif weighted_score >= 30:
            action = "buy"
        elif weighted_score <= -60:
            action = "strong_sell"
        elif weighted_score <= -30:
            action = "sell"
        else:
            action = "hold"

        same_direction = all(
            (s.score > 0) == (weighted_score > 0) or abs(s.score) < 10
            for s in signals
        )
        confidence = min(abs(weighted_score), 100)
        if same_direction and len(signals) >= 2:
            confidence = min(confidence * 1.2, 100)

        position_pct = 0.0
        if action == "strong_buy":
            position_pct = min(20, abs(weighted_score) / 5)
        elif action == "buy":
            position_pct = min(10, abs(weighted_score) / 8)

        tech_sig = next((s for s in signals if s.strategy_name == "technical"), None)
        cap_sig = next((s for s in signals if s.strategy_name == "capital_flow"), None)
        news_sig = next((s for s in signals if s.strategy_name == "news_sentiment"), None)

        return TradeSignal(
            code=code, name=name, timestamp=datetime.now().isoformat(),
            action=action, score=round(weighted_score, 1),
            technical_score=round(tech_sig.score if tech_sig else 0, 1),
            capital_score=round(cap_sig.score if cap_sig else 0, 1),
            news_score=round(news_sig.score if news_sig else 0, 1),
            fundamental_score=0,
            confidence=round(confidence, 1),
            reasons=reasons,
            position_pct=round(position_pct, 1),
            price=price,
        )
```

---

## Phase 3: 风控+执行层

### Task 3.1: 风控规则

**Files:**
- Create: `src/risk/__init__.py`
- Create: `src/risk/rules.py`
- Create: `src/risk/manager.py`

(具体代码见后续，确保风控规则可组合)

### Task 3.2: 信号总线

**Files:**
- Create: `src/engine/signal_bus.py`

### Task 3.3: Broker接口

**Files:**
- Create: `src/execution/broker.py`

### Task 3.4: 持仓管理

**Files:**
- Create: `src/execution/position.py`

### Task 3.5: 订单管理

**Files:**
- Create: `src/execution/order.py`

---

## Phase 4: 回测引擎

### Task 4.1: 回测核心

**Files:**
- Create: `src/engine/__init__.py`
- Create: `src/engine/backtest.py`

### Task 4.2: 绩效指标

**Files:**
- Create: `src/analytics/metrics.py`

### Task 4.3: 报告生成

**Files:**
- Create: `src/analytics/__init__.py`
- Create: `src/analytics/report.py`

---

## Phase 5: 实盘引擎

### Task 5.1: 实盘引擎

**Files:**
- Create: `src/engine/live.py`

### Task 5.2: 入口改造

**Files:**
- Modify: `start.py`
- Modify: `main.py`

---

## Phase 6: Web面板升级

### Task 6.1: 主面板

**Files:**
- Create: `src/web/app.py`

### Task 6.2: 回测页面

**Files:**
- Create: `src/web/pages/backtest.py`

### Task 6.3: 绩效页面

**Files:**
- Create: `src/web/pages/analytics.py`
