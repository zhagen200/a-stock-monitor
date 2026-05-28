import pandas as pd
import numpy as np
from typing import Dict, List
from datetime import datetime

from src.strategy.base import BaseStrategy
from src.core.base import StrategySignal, RegimeType


def detect_market_regime(index_kline: pd.DataFrame) -> RegimeType:
    if index_kline.empty or len(index_kline) < 120:
        return "oscillate"
    close = index_kline["close"]
    ma120 = close.rolling(120).mean().iloc[-1]
    ma60 = close.rolling(60).mean().iloc[-1]
    price = close.iloc[-1]
    if price > ma120 and ma60 > ma120:
        return "bull"
    elif price < ma120 and ma60 < ma120:
        return "bear"
    return "oscillate"


class TechnicalStrategy(BaseStrategy):
    name = "technical"
    weight = 0.4

    def get_required_data(self) -> List[str]:
        return ["kline_daily"]

    def generate(self, data: Dict) -> StrategySignal:
        df = data.get("kline_daily")
        code = data.get("code", "")
        name = data.get("name", "")
        price = data.get("price", 0)

        if df is None or df.empty or len(df) < 60:
            return StrategySignal(
                code=code, name=name, strategy_name=self.name,
                action="hold", score=0, confidence=0,
                detail={"error": "数据不足"},
            )

        regime = detect_market_regime(df)
        trend_score = self._analyze_trend(df, price)
        momentum_score = self._analyze_momentum(df)
        volume_score = self._analyze_volume(df)
        total = trend_score + momentum_score + volume_score

        # 归一化到 -100 ~ 100 范围
        # 理论极值 50+30+20=100，但实际常落在 -40~40
        # 使用 soft 缩放让中间值有合理区分度
        normalized = max(min(total * 1.5, 100), -100)

        regime_multiplier = {"bull": 1.0, "oscillate": 0.9, "bear": 0.7}
        score = normalized * regime_multiplier.get(regime, 0.9)

        confidence = min(abs(score) * 1.2, 100)

        if score >= 55:
            action = "strong_buy"
        elif score >= 25:
            action = "buy"
        elif score <= -55:
            action = "strong_sell"
        elif score <= -25:
            action = "sell"
        else:
            action = "hold"

        return StrategySignal(
            code=code, name=name, strategy_name=self.name,
            action=action, score=round(score, 1),
            confidence=round(confidence, 1),
            detail={
                "regime": regime, "trend": trend_score,
                "momentum": momentum_score, "volume": volume_score,
            },
            timestamp=datetime.now().isoformat(),
        )

    def _analyze_trend(self, df: pd.DataFrame, price: float) -> float:
        """趋势分析 (-50 ~ 50)"""
        score = 0.0
        close = df["close"]

        # ---- MA 排列评分 ----
        ma5 = close.rolling(5).mean().iloc[-1]
        ma10 = close.rolling(10).mean().iloc[-1]
        ma20 = close.rolling(20).mean().iloc[-1]
        ma60 = close.rolling(60).mean().iloc[-1]

        # 计算多头/空头排列强度
        bull_count = sum([
            price > ma5, ma5 > ma10, ma10 > ma20, ma20 > ma60,
        ])
        bear_count = sum([
            price < ma5, ma5 < ma10, ma10 < ma20, ma20 < ma60,
        ])

        if bull_count == 4:
            score += 35
        elif bull_count == 3:
            score += 25
        elif bull_count == 2:
            score += 12
        elif bull_count == 1:
            score += 5

        if bear_count == 4:
            score -= 35
        elif bear_count == 3:
            score -= 25
        elif bear_count == 2:
            score -= 12
        elif bear_count == 1:
            score -= 5

        # ---- MACD 评分 ----
        ema12 = close.ewm(span=12).mean()
        ema26 = close.ewm(span=26).mean()
        dif = ema12 - ema26
        dea = dif.ewm(span=9).mean()
        macd_hist = (dif - dea) * 2

        if len(dif) >= 2:
            if dif.iloc[-2] < dea.iloc[-2] and dif.iloc[-1] > dea.iloc[-1]:
                score += 12
            elif dif.iloc[-2] > dea.iloc[-2] and dif.iloc[-1] < dea.iloc[-1]:
                score -= 12

        if len(macd_hist) >= 3:
            if macd_hist.iloc[-1] > macd_hist.iloc[-2] > macd_hist.iloc[-3]:
                if macd_hist.iloc[-1] > 0:
                    score += 6
            elif macd_hist.iloc[-1] < macd_hist.iloc[-2] < macd_hist.iloc[-3]:
                if macd_hist.iloc[-1] < 0:
                    score -= 6

        # ---- 价格相对于 MA20 的位置 ----
        ma20_val = close.rolling(20).mean().iloc[-1]
        ma20_dist = (price - ma20_val) / max(ma20_val, 0.01) * 100

        if ma20_dist > 12:
            score -= 4
        elif ma20_dist < -12:
            score += 6
        elif ma20_dist < -3:
            score += 3

        return max(min(score, 50), -50)

    def _analyze_momentum(self, df: pd.DataFrame) -> float:
        """动量分析 (-30 ~ 30)"""
        score = 0.0
        close = df["close"]

        # ---- RSI ----
        delta = close.diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        avg_gain = gain.rolling(14).mean()
        avg_loss = loss.rolling(14).mean()
        rs = avg_gain / avg_loss.replace(0, np.nan)
        rsi = 100 - (100 / (1 + rs))
        rsi_val = rsi.iloc[-1]

        if rsi_val < 25:
            score += 20
        elif rsi_val < 35:
            score += 12
        elif rsi_val < 45:
            score += 5
        elif rsi_val > 75:
            score -= 20
        elif rsi_val > 65:
            score -= 12
        elif rsi_val > 55:
            score -= 5

        # ---- KDJ ----
        low_min = df["low"].rolling(9).min()
        high_max = df["high"].rolling(9).max()
        rsv = (close - low_min) / (high_max - low_min).replace(0, np.nan) * 100
        k = rsv.ewm(alpha=1/3).mean()
        d = k.ewm(alpha=1/3).mean()
        j = 3 * k - 2 * d

        if len(k) >= 2:
            if k.iloc[-2] < d.iloc[-2] and k.iloc[-1] > d.iloc[-1]:
                score += 8
            elif k.iloc[-2] > d.iloc[-2] and k.iloc[-1] < d.iloc[-1]:
                score -= 8

        j_val = j.iloc[-1]
        if j_val < 0:
            score += 5
        elif j_val > 100:
            score -= 5

        return max(min(score, 30), -30)

    def _analyze_volume(self, df: pd.DataFrame) -> float:
        """成交量分析 (-20 ~ 20)"""
        score = 0.0
        vol = df["volume"]
        close = df["close"]

        vol_ma5 = vol.rolling(5).mean().iloc[-1]
        vol_ma20 = vol.rolling(20).mean().iloc[-1]
        vol_ratio = vol.iloc[-1] / max(vol_ma20, 1)
        vol_trend_ratio = vol_ma5 / max(vol_ma20, 1)

        price_up = close.iloc[-1] > close.iloc[-2]
        price_ma5_up = close.iloc[-1] > close.rolling(5).mean().iloc[-1]

        # 放量上涨
        if vol_ratio > 2.0 and price_up:
            score += 15
        elif vol_ratio > 1.5 and price_up:
            score += 8
        elif vol_ratio > 1.2 and price_up:
            score += 3

        # 放量下跌
        if vol_ratio > 2.0 and not price_up:
            score -= 15
        elif vol_ratio > 1.5 and not price_up:
            score -= 8

        # 量能趋势
        if vol_trend_ratio > 1.3 and price_ma5_up:
            score += 5
        elif vol_trend_ratio < 0.7:
            score -= 3

        return max(min(score, 20), -20)
