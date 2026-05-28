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
        else:
            score = max(main_pct * 5, -100)

        if score >= 30:
            action = "buy"
        elif score <= -30:
            action = "sell"
        else:
            action = "hold"

        return StrategySignal(
            code=code, name=name, strategy_name=self.name,
            action=action, score=round(score, 1),
            confidence=min(abs(score), 100),
            detail={"main_net": main_net, "main_pct": main_pct},
            timestamp=datetime.now().isoformat(),
        )
