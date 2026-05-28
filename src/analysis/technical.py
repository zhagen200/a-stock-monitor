"""
技术分析模块
计算各种技术指标、识别K线形态
"""

import pandas as pd
import numpy as np
from typing import Optional
from dataclasses import dataclass, field


@dataclass
class TechnicalSignal:
    """技术分析信号"""
    name: str
    value: float
    signal: str  # "bullish"/"bearish"/"neutral"
    strength: float  # -1.0 ~ 1.0
    description: str


@dataclass
class TechnicalAnalysis:
    """技术分析结果"""
    trend_score: float = 0.0      # 趋势得分 -20~20
    momentum_score: float = 0.0   # 动量得分 -15~15
    volume_score: float = 0.0     # 成交量得分 -5~5
    pattern_score: float = 0.0    # 形态得分 -5~5
    total_score: float = 0.0      # 总分 -45~45
    signals: list = field(default_factory=list)
    support_levels: list = field(default_factory=list)
    resistance_levels: list = field(default_factory=list)
    stop_loss: float = 0.0
    take_profit_1: float = 0.0
    take_profit_2: float = 0.0


class TechnicalAnalyzer:
    """技术分析器"""

    def analyze(self, df: pd.DataFrame, current_price: float = 0) -> TechnicalAnalysis:
        """执行完整技术分析"""
        if df.empty or len(df) < 60:
            return TechnicalAnalysis()

        result = TechnicalAnalysis()
        if current_price == 0:
            current_price = df["close"].iloc[-1]

        # 1. 趋势分析
        trend_score, trend_signals = self._analyze_trend(df, current_price)
        result.trend_score = trend_score
        result.signals.extend(trend_signals)

        # 2. 动量分析
        momentum_score, momentum_signals = self._analyze_momentum(df, current_price)
        result.momentum_score = momentum_score
        result.signals.extend(momentum_signals)

        # 3. 成交量分析
        volume_score, volume_signals = self._analyze_volume(df)
        result.volume_score = volume_score
        result.signals.extend(volume_signals)

        # 4. K线形态
        pattern_score, pattern_signals = self._analyze_patterns(df)
        result.pattern_score = pattern_score
        result.signals.extend(pattern_signals)

        # 5. 支撑阻力位
        result.support_levels = self._find_support(df, current_price)
        result.resistance_levels = self._find_resistance(df, current_price)

        # 6. 止盈止损计算
        result.stop_loss = self._calc_stop_loss(df, current_price)
        result.take_profit_1 = self._calc_take_profit(df, current_price, 1)
        result.take_profit_2 = self._calc_take_profit(df, current_price, 2)

        result.total_score = result.trend_score + result.momentum_score +                             result.volume_score + result.pattern_score

        return result

    def _analyze_trend(self, df: pd.DataFrame, price: float) -> tuple:
        """趋势分析 (得分: -20 ~ 20)"""
        score = 0.0
        signals = []
        close = df["close"]

        # MA排列
        ma5 = close.rolling(5).mean().iloc[-1]
        ma10 = close.rolling(10).mean().iloc[-1]
        ma20 = close.rolling(20).mean().iloc[-1]
        ma60 = close.rolling(60).mean().iloc[-1]

        # 多头排列: price > ma5 > ma10 > ma20 > ma60
        if price > ma5 > ma10 > ma20 > ma60:
            score += 15
            signals.append(TechnicalSignal(
                "MA排列", 0, "bullish", 0.9,
                "完美多头排列，趋势强劲"
            ))
        elif price > ma5 > ma10 > ma20:
            score += 10
            signals.append(TechnicalSignal(
                "MA排列", 0, "bullish", 0.7,
                "短期多头排列，趋势向好"
            ))
        # 空头排列
        elif price < ma5 < ma10 < ma20 < ma60:
            score -= 15
            signals.append(TechnicalSignal(
                "MA排列", 0, "bearish", -0.9,
                "空头排列，趋势向下"
            ))
        elif price < ma5 < ma10 < ma20:
            score -= 10
            signals.append(TechnicalSignal(
                "MA排列", 0, "bearish", -0.7,
                "短期空头排列，趋势偏弱"
            ))

        # MACD
        ema12 = close.ewm(span=12).mean()
        ema26 = close.ewm(span=26).mean()
        dif = ema12 - ema26
        dea = dif.ewm(span=9).mean()
        macd_hist = (dif - dea) * 2

        # MACD金叉/死叉
        if len(dif) >= 2:
            if dif.iloc[-2] < dea.iloc[-2] and dif.iloc[-1] > dea.iloc[-1]:
                score += 5
                signals.append(TechnicalSignal(
                    "MACD", float(dif.iloc[-1]), "bullish", 0.6,
                    "MACD金叉，看多信号"
                ))
            elif dif.iloc[-2] > dea.iloc[-2] and dif.iloc[-1] < dea.iloc[-1]:
                score -= 5
                signals.append(TechnicalSignal(
                    "MACD", float(dif.iloc[-1]), "bearish", -0.6,
                    "MACD死叉，看空信号"
                ))

        # MACD柱状图趋势
        if len(macd_hist) >= 3:
            if macd_hist.iloc[-1] > macd_hist.iloc[-2] > macd_hist.iloc[-3]:
                if macd_hist.iloc[-1] > 0:
                    score += 3
                    signals.append(TechnicalSignal(
                        "MACD柱", float(macd_hist.iloc[-1]), "bullish", 0.4,
                        "MACD红柱放大，多头增强"
                    ))
            elif macd_hist.iloc[-1] < macd_hist.iloc[-2] < macd_hist.iloc[-3]:
                if macd_hist.iloc[-1] < 0:
                    score -= 3
                    signals.append(TechnicalSignal(
                        "MACD柱", float(macd_hist.iloc[-1]), "bearish", -0.4,
                        "MACD绿柱放大，空头增强"
                    ))

        # 价格相对MA位置
        if price > ma20:
            pct_above = (price - ma20) / ma20 * 100
            if pct_above > 15:
                score -= 3  # 偏离过远，有回调风险
                signals.append(TechnicalSignal(
                    "乖离率", pct_above, "bearish", -0.3,
                    f"价格偏离MA20达{pct_above:.1f}%，注意回调风险"
                ))

        return max(min(score, 20), -20), signals

    def _analyze_momentum(self, df: pd.DataFrame, price: float) -> tuple:
        """动量分析 (得分: -15 ~ 15)"""
        score = 0.0
        signals = []
        close = df["close"]

        # RSI
        delta = close.diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        avg_gain = gain.rolling(14).mean()
        avg_loss = loss.rolling(14).mean()
        rs = avg_gain / avg_loss.replace(0, np.nan)
        rsi = 100 - (100 / (1 + rs))
        rsi_val = rsi.iloc[-1]

        if rsi_val < 30:
            score += 8
            signals.append(TechnicalSignal(
                "RSI", float(rsi_val), "bullish", 0.8,
                f"RSI={rsi_val:.1f}，严重超卖，反弹概率大"
            ))
        elif rsi_val < 40:
            score += 4
            signals.append(TechnicalSignal(
                "RSI", float(rsi_val), "bullish", 0.4,
                f"RSI={rsi_val:.1f}，接近超卖区"
            ))
        elif rsi_val > 70:
            score -= 8
            signals.append(TechnicalSignal(
                "RSI", float(rsi_val), "bearish", -0.8,
                f"RSI={rsi_val:.1f}，严重超买，回调风险大"
            ))
        elif rsi_val > 60:
            score -= 4
            signals.append(TechnicalSignal(
                "RSI", float(rsi_val), "bearish", -0.4,
                f"RSI={rsi_val:.1f}，接近超买区"
            ))

        # KDJ
        low_min = df["low"].rolling(9).min()
        high_max = df["high"].rolling(9).max()
        rsv = (close - low_min) / (high_max - low_min).replace(0, np.nan) * 100
        k = rsv.ewm(alpha=1/3).mean()
        d = k.ewm(alpha=1/3).mean()
        j = 3 * k - 2 * d

        k_val, d_val, j_val = k.iloc[-1], d.iloc[-1], j.iloc[-1]

        # KDJ金叉
        if len(k) >= 2:
            if k.iloc[-2] < d.iloc[-2] and k.iloc[-1] > d.iloc[-1]:
                score += 5
                signals.append(TechnicalSignal(
                    "KDJ", float(k_val), "bullish", 0.5,
                    f"KDJ金叉，K={k_val:.1f} D={d_val:.1f}"
                ))
            elif k.iloc[-2] > d.iloc[-2] and k.iloc[-1] < d.iloc[-1]:
                score -= 5
                signals.append(TechnicalSignal(
                    "KDJ", float(k_val), "bearish", -0.5,
                    f"KDJ死叉，K={k_val:.1f} D={d_val:.1f}"
                ))

        if j_val < 0:
            score += 3
            signals.append(TechnicalSignal(
                "J值", float(j_val), "bullish", 0.4,
                f"J值={j_val:.1f}，极度超卖"
            ))
        elif j_val > 100:
            score -= 3
            signals.append(TechnicalSignal(
                "J值", float(j_val), "bearish", -0.4,
                f"J值={j_val:.1f}，极度超买"
            ))

        return max(min(score, 15), -15), signals

    def _analyze_volume(self, df: pd.DataFrame) -> tuple:
        """成交量分析 (得分: -5 ~ 5)"""
        score = 0.0
        signals = []
        
        vol = df["volume"]
        close = df["close"]
        vol_ma20 = vol.rolling(20).mean().iloc[-1]
        vol_ratio = vol.iloc[-1] / vol_ma20 if vol_ma20 > 0 else 1

        price_up = close.iloc[-1] > close.iloc[-2]

        if vol_ratio > 2.0 and price_up:
            score += 5
            signals.append(TechnicalSignal(
                "成交量", float(vol_ratio), "bullish", 0.8,
                f"放量上涨，量比={vol_ratio:.1f}倍"
            ))
        elif vol_ratio > 1.5 and price_up:
            score += 3
            signals.append(TechnicalSignal(
                "成交量", float(vol_ratio), "bullish", 0.5,
                f"温和放量上涨，量比={vol_ratio:.1f}倍"
            ))
        elif vol_ratio > 2.0 and not price_up:
            score -= 5
            signals.append(TechnicalSignal(
                "成交量", float(vol_ratio), "bearish", -0.8,
                f"放量下跌，量比={vol_ratio:.1f}倍，恐慌抛售"
            ))
        elif vol_ratio < 0.5:
            score -= 2
            signals.append(TechnicalSignal(
                "成交量", float(vol_ratio), "neutral", -0.2,
                f"成交量萎缩，量比={vol_ratio:.1f}倍"
            ))

        return max(min(score, 5), -5), signals

    def _analyze_patterns(self, df: pd.DataFrame) -> tuple:
        """K线形态识别 (得分: -5 ~ 5)"""
        score = 0.0
        signals = []
        
        o, h, l, c = df["open"].iloc[-1], df["high"].iloc[-1],                       df["low"].iloc[-1], df["close"].iloc[-1]
        
        body = abs(c - o)
        upper_shadow = h - max(o, c)
        lower_shadow = min(o, c) - l
        total_range = h - l

        if total_range == 0:
            return 0, signals

        # 锤子线 (底部看涨)
        if lower_shadow > body * 2 and upper_shadow < body * 0.3:
            if df["close"].iloc[-5:-1].min() < c:  # 之前在下跌
                score += 3
                signals.append(TechnicalSignal(
                    "K线形态", 0, "bullish", 0.6,
                    "锤子线形态，底部反转信号"
                ))

        # 上吊线 (顶部看跌)
        if lower_shadow > body * 2 and upper_shadow < body * 0.3:
            if df["close"].iloc[-5:-1].max() > c:  # 之前在上涨
                score -= 3
                signals.append(TechnicalSignal(
                    "K线形态", 0, "bearish", -0.6,
                    "上吊线形态，顶部反转信号"
                ))

        # 吞没形态
        if len(df) >= 2:
            prev_o, prev_c = df["open"].iloc[-2], df["close"].iloc[-2]
            # 看涨吞没
            if prev_c < prev_o and c > o and c > prev_o and o < prev_c:
                score += 4
                signals.append(TechnicalSignal(
                    "K线形态", 0, "bullish", 0.7,
                    "看涨吞没形态，强烈反转信号"
                ))
            # 看跌吞没
            elif prev_c > prev_o and c < o and c < prev_o and o > prev_c:
                score -= 4
                signals.append(TechnicalSignal(
                    "K线形态", 0, "bearish", -0.7,
                    "看跌吞没形态，强烈反转信号"
                ))

        # 十字星
        if body < total_range * 0.1:
            score += 0.5  # 中性偏反转
            signals.append(TechnicalSignal(
                "K线形态", 0, "neutral", 0.1,
                "十字星，多空平衡，等待方向选择"
            ))

        return max(min(score, 5), -5), signals

    def _find_support(self, df: pd.DataFrame, price: float) -> list:
        """识别支撑位"""
        supports = []
        lows = df["low"].tail(60)
        
        # 近期低点
        for i in range(2, len(lows) - 2):
            if lows.iloc[i] < lows.iloc[i-1] and lows.iloc[i] < lows.iloc[i-2] and                lows.iloc[i] < lows.iloc[i+1] and lows.iloc[i] < lows.iloc[i+2]:
                if lows.iloc[i] < price:
                    supports.append(round(float(lows.iloc[i]), 2))
        
        # MA支撑
        for ma_period in [20, 60, 120]:
            if len(df) >= ma_period:
                ma_val = df["close"].rolling(ma_period).mean().iloc[-1]
                if ma_val < price:
                    supports.append(round(float(ma_val), 2))
        
        return sorted(set(supports), reverse=True)[:3]

    def _find_resistance(self, df: pd.DataFrame, price: float) -> list:
        """识别阻力位"""
        resistances = []
        highs = df["high"].tail(60)
        
        for i in range(2, len(highs) - 2):
            if highs.iloc[i] > highs.iloc[i-1] and highs.iloc[i] > highs.iloc[i-2] and                highs.iloc[i] > highs.iloc[i+1] and highs.iloc[i] > highs.iloc[i+2]:
                if highs.iloc[i] > price:
                    resistances.append(round(float(highs.iloc[i]), 2))
        
        for ma_period in [20, 60, 120, 250]:
            if len(df) >= ma_period:
                ma_val = df["close"].rolling(ma_period).mean().iloc[-1]
                if ma_val > price:
                    resistances.append(round(float(ma_val), 2))
        
        return sorted(set(resistances))[:3]

    def _calc_stop_loss(self, df: pd.DataFrame, price: float) -> float:
        """计算止损价"""
        atr = self._calc_atr(df, 14)
        # 取ATR止损和固定止损(6%)的较高者
        atr_stop = price - 2 * atr
        fixed_stop = price * 0.94
        return round(max(atr_stop, fixed_stop), 2)

    def _calc_take_profit(self, df: pd.DataFrame, price: float, level: int) -> float:
        """计算止盈价"""
        atr = self._calc_atr(df, 14)
        if level == 1:
            return round(price + 3 * atr, 2)  # 第一止盈: 3倍ATR
        else:
            return round(price + 5 * atr, 2)  # 第二止盈: 5倍ATR

    def _calc_atr(self, df: pd.DataFrame, period: int = 14) -> float:
        """计算ATR"""
        high = df["high"]
        low = df["low"]
        close = df["close"].shift(1)
        tr = pd.concat([
            high - low,
            (high - close).abs(),
            (low - close).abs(),
        ], axis=1).max(axis=1)
        return float(tr.rolling(period).mean().iloc[-1])
