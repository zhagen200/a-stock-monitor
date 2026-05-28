import pandas as pd
import numpy as np
from typing import Dict, List
from datetime import datetime

from src.strategy.base import BaseStrategy
from src.core.base import StrategySignal


class VolumePatternStrategy(BaseStrategy):
    """成交量形态分析：异常放量/缩量/量价背离"""
    name = "volume_pattern"
    weight = 0.25

    def get_required_data(self) -> List[str]:
        return ["kline_daily"]

    def generate(self, data: Dict) -> StrategySignal:
        df = data.get("kline_daily")
        code = data.get("code", "")
        name = data.get("name", "")
        price = data.get("price", 0)

        if df is None or df.empty or len(df) < 30:
            return StrategySignal(
                code=code, name=name, strategy_name=self.name,
                action="hold", score=0, confidence=0,
                detail={"error": "数据不足"},
            )

        score = self._analyze_volume_patterns(df)

        confidence = min(abs(score) * 2, 100)

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
            detail={"vol_ratio": round(self._vol_ratio(df), 2)},
            timestamp=datetime.now().isoformat(),
        )

    def _vol_ratio(self, df: pd.DataFrame) -> float:
        return float(df["volume"].iloc[-1] / max(df["volume"].rolling(20).mean().iloc[-1], 1))

    def _analyze_volume_patterns(self, df: pd.DataFrame) -> float:
        score = 0.0
        close = df["close"]
        vol = df["volume"]
        vol_ma20 = vol.rolling(20).mean()
        vol_ma5 = vol.rolling(5).mean()
        latest_vol = vol.iloc[-1]
        avg_vol_20 = vol_ma20.iloc[-1] if not vol_ma20.empty else 1
        avg_vol_5 = vol_ma5.iloc[-1] if not vol_ma5.empty else 1

        vol_ratio_20 = latest_vol / max(avg_vol_20, 1)
        vol_ratio_5 = latest_vol / max(avg_vol_5, 1)

        # 缩量见底
        vol_squeeze = vol_ma5.iloc[-1] / max(avg_vol_20, 1) if not vol_ma5.empty and not vol_ma20.empty else 1
        if vol_squeeze < 0.5 and len(df) >= 60:
            price_pos = (close.iloc[-1] - close.iloc[-60:].min()) / max(close.iloc[-60:].max() - close.iloc[-60:].min(), 0.01)
            if price_pos < 0.3:
                score += 15

        # 量价齐升
        if vol_ratio_20 > 1.3 and vol_ratio_5 > 1.1:
            price_up_days = sum(1 for i in range(1, 6) if close.iloc[-i] > close.iloc[-i-1])
            if price_up_days >= 4:
                score += 12

        # 放量滞涨
        if vol_ratio_20 > 2.0 and abs(close.iloc[-1] / close.iloc[-5] - 1) < 0.01:
            score -= 12

        # 量价背离 (价格新高但量萎缩)
        if len(df) >= 20:
            high_20 = close.iloc[-20:].max()
            if close.iloc[-1] >= high_20 * 0.99:
                vol_20_avg = vol.iloc[-20:].mean()
                if latest_vol < vol_20_avg * 0.7:
                    score -= 8

        # 底部放量
        if len(df) >= 30:
            low_30 = close.iloc[-30:].min()
            near_low = close.iloc[-1] < low_30 * 1.05
            if near_low and vol_ratio_20 > 1.8:
                score += 10

        return max(min(score, 30), -30)
