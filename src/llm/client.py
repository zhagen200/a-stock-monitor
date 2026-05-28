"""
本地大模型客户端
支持OpenAI兼容API (Ollama, vLLM, LM Studio等)
"""

import json
from typing import Optional
from openai import OpenAI
from rich.console import Console

console = Console()


class LLMClient:
    """本地大模型客户端"""

    def __init__(self, api_base: str = "http://localhost:11434/v1",
                 model: str = "qwen2.5", api_key: str = "not-needed"):
        self.client = OpenAI(base_url=api_base, api_key=api_key, timeout=60.0)
        self.model = model
        self.enabled = True

    def _call(self, prompt: str, system: str = "", max_tokens: int = 1000) -> str:
        """调用模型"""
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=0.3,
            )
            return response.choices[0].message.content
        except Exception as e:
            console.print(f"[yellow]LLM调用失败: {e}[/yellow]")
            return ""

    def analyze_news(self, news_text: str, stock_code: str = "") -> dict:
        """分析新闻情感和影响"""
        if not self.enabled:
            return {"sentiment": 0, "impact": "unknown", "confidence": 0}
        
        prompt = f"""分析以下A股新闻对{'股票'+stock_code if stock_code else '市场'}的影响。

新闻内容：
{news_text[:1500]}

请用JSON格式输出（不要输出其他内容）：
{{
    "sentiment": <-2到2的整数，-2=利空, -1=偏空, 0=中性, 1=偏多, 2=利多>,
    "impact": "<low/medium/high>",
    "affected_sectors": ["受影响板块1", "板块2"],
    "reason": "<简要分析原因>",
    "suggestion": "<买入/持有/卖出>"
}}"""
        
        result = self._call(prompt, system="你是专业的A股分析师，擅长新闻情感分析。")
        try:
            # 提取JSON
            start = result.find("{")
            end = result.rfind("}") + 1
            if start >= 0 and end > start:
                data = json.loads(result[start:end])
                # 转换为 -100~100 的分数
                sentiment_map = {-2: -80, -1: -40, 0: 0, 1: 40, 2: 80}
                data["score"] = sentiment_map.get(data.get("sentiment", 0), 0)
                return data
        except:
            pass
        return {"sentiment": 0, "impact": "unknown", "score": 0, "reason": "解析失败"}

    def generate_stock_report(self, stock_info: dict, technical: dict,
                               fund_flow: dict, news_list: list) -> str:
        """生成个股分析报告"""
        if not self.enabled:
            return "LLM未启用，无法生成报告"
        
        prompt = f"""作为专业的A股分析师，请为以下股票生成投资分析报告。

股票信息：
- 代码：{stock_info.get('code', '')}
- 名称：{stock_info.get('name', '')}
- 当前价：{stock_info.get('price', '')}
- 涨跌幅：{stock_info.get('change_pct', '')}%
- PE：{stock_info.get('pe_ratio', '')}
- PB：{stock_info.get('pb_ratio', '')}

技术指标：
{json.dumps(technical, ensure_ascii=False, indent=2)}

资金流向：
{json.dumps(fund_flow, ensure_ascii=False, indent=2)}

近期新闻：
{chr(10).join(news_list[:5])}

请生成简洁的投资分析报告，包含：
1. 趋势判断（上升/震荡/下降）
2. 关键支撑位和阻力位
3. 操作建议（买入/持有/卖出及理由）
4. 风险提示

控制在300字以内。"""
        
        return self._call(prompt, system="你是资深A股投资顾问，分析专业、建议务实。")

    def analyze_market_sentiment(self, news_list: list) -> dict:
        """分析整体市场情绪"""
        if not self.enabled:
            return {"sentiment": "neutral", "score": 0}
        
        news_text = "\n".join([f"- {n}" for n in news_list[:10]])
        prompt = f"""分析以下A股市场新闻，判断当前市场整体情绪。

新闻列表：
{news_text}

请用JSON输出：
{{
    "sentiment": "<极度恐慌/恐慌/中性/乐观/极度乐观>",
    "score": <-100到100的整数>,
    "main_theme": "<当前市场主线>",
    "risk_level": "<低/中/高>",
    "brief": "<一句话总结>"
}}"""
        
        result = self._call(prompt)
        try:
            start = result.find("{")
            end = result.rfind("}") + 1
            if start >= 0 and end > start:
                return json.loads(result[start:end])
        except:
            pass
        return {"sentiment": "neutral", "score": 0}
