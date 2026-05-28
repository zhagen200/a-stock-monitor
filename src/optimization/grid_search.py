from typing import Dict, List, Optional, Callable
from dataclasses import dataclass, field
from itertools import product
import pandas as pd

from src.core.base import BacktestResult
from src.core.config import settings
from src.data.manager import DataManager
from src.data.store import SignalStore
from src.strategy.technical import TechnicalStrategy
from src.strategy.capital_flow import CapitalFlowStrategy
from src.strategy.ensemble import EnsembleStrategy
from src.risk.manager import RiskManager
from src.risk.rules import PositionLimitRule, MarketRegimeFilter, ConsecutiveLossRule, VolatilityRule


@dataclass
class ParamGrid:
    name: str
    values: list


@dataclass
class GridSearchResult:
    params: dict
    score: float
    result: BacktestResult


class BacktestRunner:
    """简化的回测执行器，供参数搜索使用"""

    def __init__(self, codes: List[str], initial_cash: float = 100000):
        self.codes = codes
        self.initial_cash = initial_cash
        self.commission_rate = 0.00025
        self.data_manager = DataManager()
        self.signal_store = SignalStore()

    def run(self, strategy_weights: Dict[str, float]) -> BacktestResult:
        from src.engine.backtest import BacktestEngine

        strategies = [
            TechnicalStrategy(),
            CapitalFlowStrategy(),
        ]
        for s in strategies:
            w = strategy_weights.get(s.name)
            if w is not None:
                s.weight = w

        ensemble = EnsembleStrategy(strategies)
        risk_manager = RiskManager([
            PositionLimitRule(max_single_pct=20),
            MarketRegimeFilter(),
            ConsecutiveLossRule(max_losses=3),
            VolatilityRule(),
        ])

        engine = BacktestEngine(
            ensemble=ensemble,
            risk_manager=risk_manager,
            initial_cash=self.initial_cash,
            commission_rate=self.commission_rate,
        )

        end = pd.Timestamp.now().strftime("%Y-%m-%d")
        start = (pd.Timestamp.now() - pd.DateOffset(years=1)).strftime("%Y-%m-%d")

        return engine.run(self.codes, start_date=start, end_date=end)


class GridSearchOptimizer:
    """参数网格搜索优化器"""

    def __init__(self, codes: List[str], initial_cash: float = 100000):
        self.codes = codes
        self.initial_cash = initial_cash

    def search(self, param_grids: List[ParamGrid],
               objective: str = "sharpe") -> List[GridSearchResult]:
        """执行网格搜索，按目标函数排序"""
        results = []
        runner = BacktestRunner(self.codes, self.initial_cash)
        keys = [g.name for g in param_grids]
        value_lists = [g.values for g in param_grids]

        for combo in product(*value_lists):
            params = dict(zip(keys, combo))
            try:
                result = runner.run(params)
                score = self._objective_score(result, objective)
                results.append(GridSearchResult(
                    params=params, score=score, result=result,
                ))
            except Exception:
                continue

        results.sort(key=lambda r: r.score, reverse=True)
        return results

    @staticmethod
    def _objective_score(result: BacktestResult, objective: str) -> float:
        if objective == "sharpe":
            return result.sharpe_ratio
        elif objective == "total_return":
            return result.total_return
        elif objective == "win_rate":
            return result.win_rate
        elif objective == "profit_loss_ratio":
            return result.profit_loss_ratio
        elif objective == "composite":
            score = 0
            score += result.total_return / 10 if result.total_return > 0 else result.total_return / 5
            score += max(0, result.sharpe_ratio) * 5
            score += result.win_rate * 0.3
            score += result.profit_loss_ratio * 3
            score -= abs(result.max_drawdown) * 0.5
            return score
        return result.total_return
