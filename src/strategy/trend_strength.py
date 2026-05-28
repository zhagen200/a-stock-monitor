import pandas as pd
import numpy as np
from typing import Dict, List
from datetime import datetime

from src.strategy.base import BaseStrategy
from src.core.base import StrategySignal


class TrendStrengthStrategy(BaseStrategy):
    """趋势强度分析：ADX/DMI + 布林带位置"""
    name = "trend_strength"
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

        score = self._analyze_trend_strength(df, price)

        confidence = min(abs(score) * 1.5, 100)

        if score >= 18:
            action = "buy"
        elif score <= -18:
            action = "sell"
        else:
            action = "hold"

        return StrategySignal(
            code=code, name=name, strategy_name=self.name,
            action=action, score=round(score, 1),
            confidence=round(confidence, 1),
            detail={"adx": round(self._calc_adx(df), 1)},
            timestamp=datetime.now().isoformat(),
        )

    def _calc_adx(self, df: pd.DataFrame, period: int = 14) -> float:
        high = df["high"]
        low = df["low"]
        close = df["close"]

        up_move = high.diff()
        down_move = low.diff()

        plus_dm = ((up_move > down_move) & (up_move > 0)).astype(float) * up_move
        minus_dm = ((down_move > up_move) & (down_move > 0)).astype(float) * down_move

        tr = pd.concat([
            high - low,
            (high - close.shift()).abs(),
            (low - close.shift()).abs(),
        ], axis=1).max(axis=1)

        atr = tr.rolling(period).mean().replace(0, np.nan)
        plus_di = 100 * plus_dm.rolling(period).mean() / atr
        minus_di = 100 * minus_dm.rolling(period).mean() / atr

        dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
        adx = dx.rolling(period).mean()

        return float(adx.iloc[-1]) if not adx.empty else 0

    def _calc_dmi_direction(self, df: pd.DataFrame) -> int:
        high = df["high"]
        low = df["low"]
        close = df["close"]

        up_move = high.diff()
        down_move = low.diff()

        plus_dm = ((up_move > down_move) & (up_move > 0)).astype(float) * up_move
        minus_dm = ((down_move > up_move) & (down_move > 0)).astype(float) * down_move

        tr = pd.concat([
            high - low,
            (high - close.shift()).abs(),
            (low - close.shift()).abs(),
        ], axis=1).max(axis=1)

        atr = tr.rolling(14).mean().replace(0, np.nan)
        plus_di = 100 * plus_dm.rolling(14).mean() / atr
        minus_di = 100 * minus_dm.rolling(14).mean() / atr

        pd_val = float(plus_di.iloc[-1]) if not plus_di.empty else 0
        md_val = float(minus_di.iloc[-1]) if not minus_di.empty else 0

        if pd_val > md_val and pd_val > 20:
            return 1
        if md_val > pd_val and md_val > 20:
            return -1
        return 0

    def _analyze_trend_strength(self, df: pd.DataFrame, price: float) -> float:
        score = 0.0
        close = df["close"]

        adx = self._calc_adx(df)
        dmi_dir = self._calc_dmi_direction(df)

        # ADX > 25 表示趋势存在
        if adx > 25 and dmi_dir == 1:
            score += 15
        elif adx > 25 and dmi_dir == -1:
            score -= 15
        elif adx > 20 and dmi_dir == 1:
            score += 8
        elif adx > 20 and dmi_dir == -1:
            score -= 8

        # 布林带位置
        bb_mid = close.rolling(20).mean()
        bb_std = close.rolling(20).std()
        bb_upper = bb_mid + 2 * bb_std
        bb_lower = bb_mid - 2 * bb_std

        if not bb_upper.empty and not bb_lower.empty:
            bb_pos = (price - bb_lower.iloc[-1]) / max(bb_upper.iloc[-1] - bb_lower.iloc[-1], 0.01)
            # 布林带下轨附近有支撑
            if bb_pos < 0.05:
                score += 8
            # 上轨附近有压力
            elif bb_pos > 0.95:
                score -= 8
            # 中轨上方
            elif price > bb_mid.iloc[-1]:
                score += 3
            else:
                score -= 3

        # 趋势连续性 (多头排列天数)
        if len(close) >= 10:
            ma5 = close.rolling(5).mean()
            ma10 = close.rolling(10).mean()
            consecutive_up = 0
            for i in range(1, min(11, len(close))):
                if close.iloc[-i] > close.iloc[-i-1]:
                    consecutive_up += 1
                else:
                    break
            if consecutive_up >= 5:
                score += 5
            elif consecutive_up <= -5:
                score -= 5
            # 连续阴线
            consecutive_down = 0
            for i in range(1, min(11, len(close))):
                if close.iloc[-i] < close.iloc[-i-1]:
                    consecutive_down += 1
                else:
                    break
            if consecutive_down >= 5:
                score -= 5

        return max(min(score, 30), -30)
