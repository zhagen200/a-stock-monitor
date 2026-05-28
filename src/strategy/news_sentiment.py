from typing import Dict, List
from datetime import datetime

from src.strategy.base import BaseStrategy
from src.core.base import StrategySignal


class NewsSentimentStrategy(BaseStrategy):
    name = "news_sentiment"
    weight = 0.25

    def get_required_data(self) -> List[str]:
        return ["news_score"]

    def generate(self, data: Dict) -> StrategySignal:
        code = data.get("code", "")
        name = data.get("name", "")
        news_score = data.get("news_score", 0.0)

        score = max(min(news_score, 100), -100)

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
            detail={"raw_score": news_score},
            timestamp=datetime.now().isoformat(),
        )
