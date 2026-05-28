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
