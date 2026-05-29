"""
AI 量化分析引擎
多模型协作分析：信号归因、新闻解读、荐股推理、策略进化
"""

import json
import time
from datetime import datetime, date
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict
from rich.console import Console

console = Console()


@dataclass
class SignalAnalysis:
    """信号分析结果"""
    code: str
    name: str
    timestamp: str
    action: str
    score: float
    # AI分析
    ai_reasoning: str          # AI推理过程
    key_factors: List[str]     # 关键因素
    risk_level: str            # 风险等级: low/medium/high
    confidence_adjustment: float  # AI置信度调整
    suggested_position: float  # 建议仓位%
    stop_loss_reason: str      # 止损逻辑
    take_profit_reason: str    # 止盈逻辑
    market_context: str        # 市场环境判断
    # 归因
    attribution: Dict = None   # 信号归因 {factor: contribution}

    def __post_init__(self):
        if self.attribution is None:
            self.attribution = {}


@dataclass
class NewsAnalysis:
    """新闻分析结果"""
    code: str
    name: str
    timestamp: str
    news_count: int
    overall_sentiment: str     # positive/negative/neutral
    sentiment_score: float     # -100 ~ 100
    key_events: List[str]      # 关键事件
    impact_assessment: str     # 影响评估
    sector_impact: str         # 板块影响
    trading_suggestion: str    # 交易建议
    confidence: float          # 置信度


@dataclass
class BacktestRecord:
    """回测记录"""
    id: str
    date: str
    code: str
    name: str
    # 信号
    signal_action: str
    signal_score: float
    signal_price: float
    # AI分析
    ai_analysis: str
    ai_confidence: float
    # 实际结果
    actual_return_1d: float = 0
    actual_return_3d: float = 0
    actual_return_5d: float = 0
    actual_return_10d: float = 0
    max_drawdown: float = 0
    # 归因
    correct_factors: List[str] = None
    wrong_factors: List[str] = None
    # 进化
    lesson_learned: str = ""

    def __post_init__(self):
        if self.correct_factors is None:
            self.correct_factors = []
        if self.wrong_factors is None:
            self.wrong_factors = []


class AIAnalysisEngine:
    """AI量化分析引擎"""

    def __init__(self, llm_depot, config: dict = None):
        self.depot = llm_depot
        self.config = config or {}

    def analyze_signal(self, signal_data: dict, tech_data: dict,
                       fund_flow: dict, news_list: list,
                       market_indices: dict) -> SignalAnalysis:
        """
        深度分析交易信号
        综合技术面、资金面、消息面、市场环境进行推理
        """
        prompt = f"""你是资深A股量化分析师，请深度分析以下交易信号。

## 股票信息
- 代码: {signal_data['code']}
- 名称: {signal_data['name']}
- 当前价: ¥{signal_data['price']:.2f}
- 综合评分: {signal_data['score']:.1f}
- 信号: {signal_data['action']}
- 置信度: {signal_data['confidence']:.0f}%
- 止损: ¥{signal_data['stop_loss']:.2f}
- 止盈1: ¥{signal_data['take_profit_1']:.2f}
- 止盈2: ¥{signal_data['take_profit_2']:.2f}

## 技术指标
{json.dumps(tech_data, ensure_ascii=False, indent=2) if tech_data else '无数据'}

## 资金流向
{json.dumps(fund_flow, ensure_ascii=False, indent=2) if fund_flow else '无数据'}

## 相关新闻
{chr(10).join([f"- {n.get('title', '')}" for n in news_list[:5]]) if news_list else '无新闻'}

## 大盘环境
{json.dumps(market_indices, ensure_ascii=False, indent=2) if market_indices else '无数据'}

请用JSON格式输出分析结果：
{{
    "reasoning": "详细的推理过程，分析为什么给出这个信号",
    "key_factors": ["关键因素1", "关键因素2", ...],
    "risk_level": "low/medium/high",
    "confidence_adjustment": -20到20的调整值,
    "suggested_position": 建议仓位百分比(0-30),
    "stop_loss_reason": "止损逻辑说明",
    "take_profit_reason": "止盈逻辑说明",
    "market_context": "当前市场环境对这只股票的影响",
    "attribution": {{"技术面": 贡献度, "资金面": 贡献度, "消息面": 贡献度, "市场环境": 贡献度}}
}}"""

        system = "你是资深A股量化分析师，擅长多因子分析和风险评估。请基于数据客观分析，不要臆测。输出必须是合法JSON。"

        response = self.depot.call(prompt, system, task_type="analysis", json_mode=True)

        try:
            result = json.loads(response.content)
        except (json.JSONDecodeError, Exception):
            result = {
                "reasoning": response.content or "分析失败",
                "key_factors": [],
                "risk_level": "medium",
                "confidence_adjustment": 0,
                "suggested_position": 10,
                "stop_loss_reason": "",
                "take_profit_reason": "",
                "market_context": "",
                "attribution": {},
            }

        return SignalAnalysis(
            code=signal_data['code'],
            name=signal_data['name'],
            timestamp=datetime.now().isoformat(),
            action=signal_data['action'],
            score=signal_data['score'],
            ai_reasoning=result.get("reasoning", ""),
            key_factors=result.get("key_factors", []),
            risk_level=result.get("risk_level", "medium"),
            confidence_adjustment=result.get("confidence_adjustment", 0),
            suggested_position=result.get("suggested_position", 10),
            stop_loss_reason=result.get("stop_loss_reason", ""),
            take_profit_reason=result.get("take_profit_reason", ""),
            market_context=result.get("market_context", ""),
            attribution=result.get("attribution", {}),
        )

    def analyze_news_batch(self, code: str, name: str,
                           news_list: list, market_context: str = "") -> NewsAnalysis:
        """批量分析新闻"""
        if not news_list:
            return NewsAnalysis(
                code=code, name=name, timestamp=datetime.now().isoformat(),
                news_count=0, overall_sentiment="neutral", sentiment_score=0,
                key_events=[], impact_assessment="无新闻", sector_impact="无",
                trading_suggestion="无", confidence=0,
            )

        news_text = "\n".join([f"- {n.get('title', '')}: {n.get('content', '')[:200]}"
                               for n in news_list[:10]])

        prompt = f"""分析以下{name}({code})的新闻，评估对股价的影响。

## 新闻列表
{news_text}

## 市场环境
{market_context or '无'}

用JSON格式输出：
{{
    "overall_sentiment": "positive/negative/neutral",
    "sentiment_score": -100到100,
    "key_events": ["关键事件1", "关键事件2"],
    "impact_assessment": "短期/中期/长期影响评估",
    "sector_impact": "对板块的影响",
    "trading_suggestion": "具体交易建议",
    "confidence": 0-100
}}"""

        response = self.depot.call(prompt, "你是A股新闻分析师，擅长从新闻中提取交易信号。输出必须是合法JSON。",
                                   task_type="news", json_mode=True)

        try:
            result = json.loads(response.content)
        except (json.JSONDecodeError, Exception):
            result = {
                "overall_sentiment": "neutral", "sentiment_score": 0,
                "key_events": [], "impact_assessment": response.content or "分析失败",
                "sector_impact": "", "trading_suggestion": "", "confidence": 0,
            }

        return NewsAnalysis(
            code=code, name=name, timestamp=datetime.now().isoformat(),
            news_count=len(news_list),
            overall_sentiment=result.get("overall_sentiment", "neutral"),
            sentiment_score=result.get("sentiment_score", 0),
            key_events=result.get("key_events", []),
            impact_assessment=result.get("impact_assessment", ""),
            sector_impact=result.get("sector_impact", ""),
            trading_suggestion=result.get("trading_suggestion", ""),
            confidence=result.get("confidence", 0),
        )

    def generate_stock_report(self, code: str, name: str,
                              quote: dict, tech_result: dict,
                              fund_flow: dict, news_analysis: NewsAnalysis,
                              signal_analysis: SignalAnalysis) -> str:
        """生成个股深度分析报告"""
        prompt = f"""基于以下数据，生成{name}({code})的深度分析报告。

## 行情
{json.dumps(quote, ensure_ascii=False)}

## 技术分析
{json.dumps(tech_result, ensure_ascii=False) if tech_result else '无'}

## 资金流向
{json.dumps(fund_flow, ensure_ascii=False) if fund_flow else '无'}

## 新闻分析
{json.dumps(asdict(news_analysis), ensure_ascii=False) if news_analysis else '无'}

## 信号分析
{json.dumps(asdict(signal_analysis), ensure_ascii=False) if signal_analysis else '无'}

请生成简洁的分析报告，包含：
1. 当前状态概述
2. 关键信号解读
3. 风险提示
4. 操作建议（含具体价位）
5. 后续关注点

报告要简洁专业，适合快速决策。"""

        response = self.depot.call(prompt, "你是A股资深分析师，生成简洁专业的分析报告。", task_type="analysis")
        return response.content or "报告生成失败"

    def evaluate_signal_accuracy(self, backtest_records: List[BacktestRecord]) -> Dict:
        """评估信号准确性，为策略进化提供依据"""
        if not backtest_records:
            return {"accuracy": 0, "lessons": []}

        records_text = "\n".join([
            f"- {r.code} {r.name}: 信号{r.action} 评分{r.score:.0f} "
            f"1日收益{r.actual_return_1d:+.2f}% 3日{r.actual_return_3d:+.2f}% "
            f"5日{r.actual_return_5d:+.2f}% 最大回撤{r.max_drawdown:.2f}%"
            for r in backtest_records[-50:]  # 最近50条
        ])

        prompt = f"""分析以下量化信号的历史表现，找出规律和改进方向。

## 信号记录（最近50条）
{records_text}

用JSON格式输出：
{{
    "overall_accuracy": 0-100,
    "buy_accuracy": 买入信号准确率0-100,
    "sell_accuracy": 卖出信号准确率0-100,
    "best_factors": ["最有效的因子1", "最有效的因子2"],
    "worst_factors": ["最不准的因子1"],
    "pattern_insights": ["发现的规律1", "发现的规律2"],
    "parameter_adjustments": {{
        "technical_weight": 建议调整值,
        "capital_weight": 建议调整值,
        "news_weight": 建议调整值,
        "buy_threshold": 建议调整值,
        "sell_threshold": 建议调整值
    }},
    "lessons": ["教训1", "教训2"]
}}"""

        response = self.depot.call(prompt, "你是量化策略评估专家，基于历史数据客观评估。输出必须是合法JSON。",
                                   task_type="backtest", json_mode=True)

        try:
            return json.loads(response.content)
        except (json.JSONDecodeError, Exception):
            return {"overall_accuracy": 0, "lessons": [response.content or "评估失败"]}
