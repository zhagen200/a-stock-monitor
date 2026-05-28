"""
信号融合引擎
多因子加权评分，生成买卖信号
"""

from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime
from rich.console import Console

console = Console()


@dataclass
class TradeSignal:
    """交易信号"""
    code: str
    name: str
    timestamp: str
    action: str          # "strong_buy"/"buy"/"hold"/"sell"/"strong_sell"
    score: float         # -100 ~ 100
    technical_score: float
    capital_score: float
    news_score: float
    fundamental_score: float
    confidence: float    # 0~100%
    reasons: list = field(default_factory=list)
    stop_loss: float = 0.0
    take_profit_1: float = 0.0
    take_profit_2: float = 0.0
    position_pct: float = 0.0  # 建议仓位比例
    price: float = 0.0
    support_levels: list = field(default_factory=list)
    resistance_levels: list = field(default_factory=list)


class SignalEngine:
    """信号融合引擎"""

    def __init__(self, config: dict = None):
        config = config or {}
        weights = config.get("signal", {}).get("weights", {})
        self.w_technical = weights.get("technical", 0.40)
        self.w_capital = weights.get("capital", 0.20)
        self.w_news = weights.get("news", 0.25)
        self.w_fundamental = weights.get("fundamental", 0.15)

        thresholds = config.get("signal", {}).get("thresholds", {})
        self.t_strong_buy = thresholds.get("strong_buy", 60)
        self.t_buy = thresholds.get("buy", 30)
        self.t_sell = thresholds.get("sell", -30)
        self.t_strong_sell = thresholds.get("strong_sell", -60)

    def generate_signal(
        self,
        code: str,
        name: str,
        price: float,
        technical_result,  # TechnicalAnalysis
        fund_flow: dict = None,
        news_sentiment: float = 0.0,  # -100 ~ 100
        pe_percentile: float = 50.0,  # PE历史百分位 0~100
        roe: float = 0.0,
    ) -> TradeSignal:
        """生成综合交易信号"""

        reasons = []

        # 1. 技术面得分 (归一化到 -100 ~ 100)
        tech_score = (technical_result.total_score / 45) * 100

        # 2. 资金面得分
        capital_score = 0.0
        if fund_flow:
            main_net = fund_flow.get("main_net_inflow", 0)
            main_pct = fund_flow.get("main_net_pct", 0)
            if main_net > 0:
                capital_score = min(main_pct * 5, 100)
                reasons.append(f"主力净流入{main_pct:.1f}%")
            else:
                capital_score = max(main_pct * 5, -100)
                reasons.append(f"主力净流出{abs(main_pct):.1f}%")

        # 3. 消息面得分 (来自LLM分析)
        news_score = news_sentiment

        # 4. 基本面得分
        fundamental_score = 0.0
        if pe_percentile < 30:
            fundamental_score = 50
            reasons.append(f"估值偏低(PE历史{pe_percentile:.0f}%分位)")
        elif pe_percentile < 50:
            fundamental_score = 20
        elif pe_percentile > 80:
            fundamental_score = -40
            reasons.append(f"估值偏高(PE历史{pe_percentile:.0f}%分位)")
        elif pe_percentile > 70:
            fundamental_score = -20

        if roe > 15:
            fundamental_score += 20
            reasons.append(f"ROE={roe:.1f}%，盈利能力强")
        elif roe > 10:
            fundamental_score += 10

        fundamental_score = max(min(fundamental_score, 100), -100)

        # 加权总分
        total_score = (
            tech_score * self.w_technical +
            capital_score * self.w_capital +
            news_score * self.w_news +
            fundamental_score * self.w_fundamental
        )

        # 确定操作
        if total_score >= self.t_strong_buy:
            action = "strong_buy"
        elif total_score >= self.t_buy:
            action = "buy"
        elif total_score <= self.t_strong_sell:
            action = "strong_sell"
        elif total_score <= self.t_sell:
            action = "sell"
        else:
            action = "hold"

        # 置信度 (基于各因子一致性)
        scores = [tech_score, capital_score, news_score, fundamental_score]
        non_zero = [s for s in scores if abs(s) > 10]
        if non_zero:
            same_direction = all(s > 0 for s in non_zero) or all(s < 0 for s in non_zero)
            confidence = min(abs(total_score), 100)
            if same_direction:
                confidence = min(confidence * 1.2, 100)
        else:
            confidence = 20

        # 仓位建议
        if action in ("strong_buy",):
            position_pct = min(20, abs(total_score) / 5)
        elif action in ("buy",):
            position_pct = min(10, abs(total_score) / 8)
        else:
            position_pct = 0

        # 添加技术面原因
        for sig in technical_result.signals[:3]:
            reasons.append(sig.description)

        return TradeSignal(
            code=code,
            name=name,
            timestamp=datetime.now().isoformat(),
            action=action,
            score=round(total_score, 1),
            technical_score=round(tech_score, 1),
            capital_score=round(capital_score, 1),
            news_score=round(news_score, 1),
            fundamental_score=round(fundamental_score, 1),
            confidence=round(confidence, 1),
            reasons=reasons,
            stop_loss=technical_result.stop_loss,
            take_profit_1=technical_result.take_profit_1,
            take_profit_2=technical_result.take_profit_2,
            position_pct=round(position_pct, 1),
            price=price,
            support_levels=technical_result.support_levels,
            resistance_levels=technical_result.resistance_levels,
        )
