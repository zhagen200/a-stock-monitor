from abc import ABC, abstractmethod
from typing import Optional
from dataclasses import dataclass

from src.core.base import TradeSignal


@dataclass
class RiskResult:
    passed: bool
    reason: str = ""
    code: str = ""


class RiskRule(ABC):
    name: str = ""

    @abstractmethod
    def check(self, signal: TradeSignal, context: dict) -> RiskResult:
        ...


class PositionLimitRule(RiskRule):
    name = "仓位限制"

    def __init__(self, max_single_pct: float = 20, max_industry_pct: float = 30):
        self.max_single_pct = max_single_pct
        self.max_industry_pct = max_industry_pct

    def check(self, signal: TradeSignal, context: dict) -> RiskResult:
        if signal.action not in ("strong_buy", "buy"):
            return RiskResult(passed=True)
        if signal.position_pct > self.max_single_pct:
            return RiskResult(
                passed=False,
                reason=f"建议仓位{signal.position_pct:.0f}%超过单票上限{self.max_single_pct}%",
            )
        return RiskResult(passed=True)


class MarketRegimeFilter(RiskRule):
    name = "市场状态过滤"

    def __init__(self):
        self._regime = "oscillate"

    def set_regime(self, regime: str):
        self._regime = regime

    def check(self, signal: TradeSignal, context: dict) -> RiskResult:
        if self._regime == "bear" and signal.action == "buy":
            return RiskResult(
                passed=False,
                reason="熊市中仅允许strong_buy级别信号",
            )
        return RiskResult(passed=True)


class ConsecutiveLossRule(RiskRule):
    name = "连续亏损停盘"

    def __init__(self, max_losses: int = 3):
        self.max_losses = max_losses
        self._consecutive_losses = 0

    def check(self, signal: TradeSignal, context: dict) -> RiskResult:
        if self._consecutive_losses >= self.max_losses:
            return RiskResult(
                passed=False,
                reason=f"连续亏损{self._consecutive_losses}次，暂停交易",
            )
        return RiskResult(passed=True)

    def record_result(self, is_profit: bool):
        if is_profit:
            self._consecutive_losses = 0
        else:
            self._consecutive_losses += 1


class VolatilityRule(RiskRule):
    name = "波动率过滤"

    def __init__(self, max_change_pct: float = 9.0):
        self.max_change_pct = max_change_pct

    def check(self, signal: TradeSignal, context: dict) -> RiskResult:
        change_pct = abs(context.get("change_pct", 0))
        if change_pct > self.max_change_pct:
            return RiskResult(
                passed=False,
                reason=f"当日涨跌幅{change_pct:.1f}%过大，禁止开仓",
            )
        return RiskResult(passed=True)
