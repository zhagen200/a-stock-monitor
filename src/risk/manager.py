from typing import List
from src.core.base import TradeSignal
from src.risk.rules import RiskRule, RiskResult


class RiskManager:
    def __init__(self, rules: List[RiskRule] = None):
        self.rules = rules or []

    def add_rule(self, rule: RiskRule):
        self.rules.append(rule)

    def check(self, signal: TradeSignal, context: dict = None) -> RiskResult:
        if context is None:
            context = {}
        for rule in self.rules:
            result = rule.check(signal, context)
            if not result.passed:
                return result
        return RiskResult(passed=True)
