import pandas as pd
import numpy as np
from typing import Dict, List
from datetime import datetime

from src.strategy.base import BaseStrategy
from src.core.base import StrategySignal


class MultiTimeframeStrategy(BaseStrategy):
    """多时间框架分析：检查日线/60分/15分趋势一致性"""
    name = "multi_timeframe"
    weight = 0.3

    def get_required_data(self) -> List[str]:
        return ["kline_daily", "kline_60min", "kline_15min"]

    def generate(self, data: Dict) -> StrategySignal:
        df_d = data.get("kline_daily")
        df_60 = data.get("kline_60min")
        df_15 = data.get("kline_15min")
        code = data.get("code", "")
        name = data.get("name", "")
        price = data.get("price", 0)

        score = self._analyze_alignment(df_d, df_60, df_15, price)

        confidence = min(abs(score) * 1.5, 100)

        if score >= 20:
            action = "buy"
        elif score <= -20:
            action = "sell"
        else:
            action = "hold"

        return StrategySignal(
            code=code, name=name, strategy_name=self.name,
            action=action, score=round(score, 1),
            confidence=round(confidence, 1),
            detail={"daily_trend": self._trend_direction(df_d),
                    "tf60_trend": self._trend_direction(df_60),
                    "tf15_trend": self._trend_direction(df_15)},
            timestamp=datetime.now().isoformat(),
        )

    def _trend_direction(self, df: pd.DataFrame) -> int:
        if df is None or df.empty or len(df) < 20:
            return 0
        close = df["close"]
        ma5 = close.rolling(5).mean().iloc[-1]
        ma20 = close.rolling(20).mean().iloc[-1]
        price = close.iloc[-1]
        if price > ma5 > ma20:
            return 1
        if price < ma5 < ma20:
            return -1
        return 0

    def _analyze_alignment(self, df_d, df_60, df_15, price: float) -> float:
        score = 0.0
        d_trend = self._trend_direction(df_d)
        t60_trend = self._trend_direction(df_60)
        t15_trend = self._trend_direction(df_15)
        trends = [d_trend, t60_trend, t15_trend]
        num_bull = sum(1 for t in trends if t == 1)
        num_bear = sum(1 for t in trends if t == -1)

        if num_bull == 3:
            score += 30
        elif num_bull == 2:
            score += 15
        elif num_bear == 3:
            score -= 30
        elif num_bear == 2:
            score -= 15

        if df_15 is not None and len(df_15) >= 5:
            close_15 = df_15["close"]
            if len(close_15) >= 5:
                slope_15 = (close_15.iloc[-1] / close_15.iloc[-5] - 1) * 100
                if abs(slope_15) > 2:
                    score += slope_15 * 3 if slope_15 > 0 else slope_15 * 2

        if df_60 is not None and len(df_60) >= 5:
            close_60 = df_60["close"]
            if len(close_60) >= 5:
                slope_60 = (close_60.iloc[-1] / close_60.iloc[-5] - 1) * 100
                if abs(slope_60) > 2:
                    score += slope_60 * 2 if slope_60 > 0 else slope_60 * 1.5

        return max(min(score, 40), -40)
