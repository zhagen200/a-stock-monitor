from typing import Dict, List
from datetime import datetime

from src.strategy.base import BaseStrategy
from src.core.base import StrategySignal, TradeSignal


class EnsembleStrategy:
    def __init__(self, strategies: List[BaseStrategy]):
        self.strategies = strategies

    def generate(self, code: str, name: str, price: float, data: Dict) -> TradeSignal:
        signals: Dict[str, StrategySignal] = {}

        for strategy in self.strategies:
            strategy_data = {
                k: v for k, v in data.items()
                if k in strategy.get_required_data()
            }
            strategy_data.update({"code": code, "name": name, "price": price})
            try:
                sig = strategy.generate(strategy_data)
                signals[sig.strategy_name] = sig
            except Exception:
                continue

        if not signals:
            return TradeSignal(
                code=code, name=name, timestamp=datetime.now().isoformat(),
                action="hold", score=0, technical_score=0,
                capital_score=0, news_score=0, fundamental_score=0,
                confidence=0,
            )

        weighted_score = 0.0
        total_weight = 0.0
        reasons = []

        for strategy in self.strategies:
            sig = signals.get(strategy.name)
            if sig is None:
                continue
            weighted_score += sig.score * strategy.weight
            total_weight += strategy.weight
            if abs(sig.score) > 20:
                reasons.append(f"{strategy.name}: {sig.score:.0f}分")

        if total_weight > 0:
            weighted_score /= total_weight
        weighted_score = max(min(weighted_score, 100), -100)

        if weighted_score >= 55:
            action = "strong_buy"
        elif weighted_score >= 25:
            action = "buy"
        elif weighted_score <= -55:
            action = "strong_sell"
        elif weighted_score <= -25:
            action = "sell"
        else:
            action = "hold"

        same_direction = all(
            (s.score > 0) == (weighted_score > 0) or abs(s.score) < 10
            for s in signals.values()
        )
        confidence = min(abs(weighted_score) * 1.2, 100)
        if same_direction and len(signals) >= 2:
            confidence = min(confidence * 1.2, 100)

        position_pct = 0.0
        if action == "strong_buy":
            position_pct = min(20, abs(weighted_score) / 4)
        elif action == "buy":
            position_pct = min(10, abs(weighted_score) / 6)

        tech_sig = signals.get("technical")
        cap_sig = signals.get("capital_flow")
        news_sig = signals.get("news_sentiment")

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
