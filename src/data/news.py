"""
新闻采集模块
从东方财富、新浪财经等获取新闻
避免使用被 Surge 拦截的域名（search-api-web.eastmoney.com 等）
"""

import time
import requests
from datetime import datetime
from typing import Optional
from rich.console import Console

console = Console()


class NewsCollector:
    """新闻采集器 - 使用可直连的 API"""

    def __init__(self):
        self.session = requests.Session()
        self.session.trust_env = False  # 绕过 Surge HTTP 代理
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Referer": "https://so.eastmoney.com/news/s",
        })

    def get_stock_news(
        self, stock_code: str, stock_name: str = "", limit: int = 5
    ) -> list:
        """获取个股相关新闻"""
        news_list = []

        # ── 1. 尝试新浪财经新闻（feed.mix.sina.com.cn 可直连） ──
        try:
            news_list = self._fetch_sina_news(stock_code, stock_name, limit)
        except Exception as e:
            console.print(f"[dim]新浪财经新闻失败: {e}[/dim]")

        # ── 2. 如果新浪没结果，尝试东方财富快讯（np-weblist 可直连） ──
        if not news_list:
            try:
                news_list = self._fetch_eastmoney_news(stock_code, stock_name, limit)
            except Exception as e:
                console.print(f"[dim]东方财富快讯失败: {e}[/dim]")

        # ── 3. 最终兜底：返回最新财经资讯 ──
        if not news_list:
            try:
                news_list = self._fetch_fallback_news(limit)
            except Exception as e:
                console.print(f"[dim]兜底新闻源失败: {e}[/dim]")

        return news_list[:limit]

    # ──────────────────────────────────────────────
    # 新浪财经新闻（feed.mix.sina.com.cn ✓ 可直连）
    # ──────────────────────────────────────────────
    def _fetch_sina_news(
        self, stock_code: str, stock_name: str, limit: int
    ) -> list:
        url = "https://feed.mix.sina.com.cn/api/roll/get"
        params = {
            "pageid": "153",
            "lid": "2509",
            "knum": str(max(limit * 2, 20)),
            "page": "1",
        }
        r = self.session.get(url, params=params, timeout=10)
        data = r.json()
        items = data.get("result", {}).get("data", [])
        if not items:
            return []

        result = []
        for item in items:
            title = item.get("title", "")
            # 优先匹配股票名称或代码
            if (stock_name and stock_name in title) or stock_code in title:
                result.append({
                    "title": title,
                    "content": item.get("summary", ""),
                    "source": "新浪财经",
                    "time": self._ts_to_str(item.get("ctime", "")),
                    "url": item.get("url", ""),
                })
            if len(result) >= limit:
                break

        return result

    # ──────────────────────────────────────────────
    # 东方财富快讯（np-weblist.eastmoney.com ✓ 可直连）
    # ──────────────────────────────────────────────
    def _fetch_eastmoney_news(
        self, stock_code: str, stock_name: str, limit: int
    ) -> list:
        url = "https://np-weblist.eastmoney.com/comm/web/getFastNewsList"
        params = {
            "client": "web",
            "biz": "web_724",
            "fastColumn": "102",
            "sortEnd": "",
            "pageSize": str(max(limit * 2, 30)),
            "req_trace": str(int(time.time() * 1000)),
        }
        r = self.session.get(url, params=params, timeout=10)
        data = r.json()
        items = data.get("data", {}).get("fastNewsList", [])
        if not items:
            return []

        result = []
        for item in items:
            title = item.get("title", "")
            # 优先匹配股票名称或代码
            if (stock_name and stock_name in title) or stock_code in title:
                result.append({
                    "title": title,
                    "content": item.get("summary", ""),
                    "source": "东方财富",
                    "time": item.get("showTime", ""),
                    "url": "",
                })
            if len(result) >= limit:
                break

        return result

    # ──────────────────────────────────────────────
    # 兜底：东方财富快讯（不经过滤）
    # ──────────────────────────────────────────────
    def _fetch_fallback_news(self, limit: int) -> list:
        url = "https://np-weblist.eastmoney.com/comm/web/getFastNewsList"
        params = {
            "client": "web",
            "biz": "web_724",
            "fastColumn": "102",
            "sortEnd": "",
            "pageSize": str(limit),
            "req_trace": str(int(time.time() * 1000)),
        }
        r = self.session.get(url, params=params, timeout=10)
        data = r.json()
        items = data.get("data", {}).get("fastNewsList", [])
        return [
            {
                "title": item.get("title", ""),
                "content": item.get("summary", ""),
                "source": "东方财富",
                "time": item.get("showTime", ""),
                "url": "",
            }
            for item in items[:limit]
        ]

    @staticmethod
    def _ts_to_str(ts) -> str:
        """转换时间戳为字符串"""
        try:
            ts_int = int(ts) // 1000 if len(str(int(ts))) > 10 else int(ts)
            return datetime.fromtimestamp(ts_int).strftime("%Y-%m-%d %H:%M:%S")
        except (ValueError, OSError):
            return str(ts)

    # ──────────────────────────────────────────────
    # 市场要闻 & 政策新闻（原有 akshare 实现可直连，保留）
    # ──────────────────────────────────────────────
    def get_market_news(self, limit: int = 20) -> list:
        """获取市场要闻"""
        try:
            import akshare as ak

            df = ak.stock_info_global_em()
            if not df.empty:
                return [
                    {
                        "title": str(row.get("标题", "")),
                        "content": str(row.get("摘要", "")),
                        "time": str(row.get("发布时间", "")),
                    }
                    for _, row in df.head(limit).iterrows()
                ]
        except Exception as e:
            console.print(f"[yellow]获取市场新闻失败: {e}[/yellow]")
        return []

    def get_policy_news(self, limit: int = 10) -> list:
        """获取政策法规新闻"""
        try:
            import akshare as ak

            df = ak.stock_info_global_em()
            keywords = [
                "政策", "监管", "央行", "国务院", "证监会",
                "发改委", "财政部", "降息", "降准",
            ]
            if not df.empty:
                news_list = []
                for _, row in df.iterrows():
                    title = str(row.get("标题", ""))
                    if any(kw in title for kw in keywords):
                        news_list.append({
                            "title": title,
                            "content": str(row.get("摘要", "")),
                            "time": str(row.get("发布时间", "")),
                        })
                    if len(news_list) >= limit:
                        break
                return news_list
        except Exception as e:
            console.print(f"[yellow]获取政策新闻失败: {e}[/yellow]")
        return []

    def get_hot_concepts(self) -> list:
        """获取热门概念板块"""
        try:
            import akshare as ak

            df = ak.stock_board_concept_name_em()
            if not df.empty:
                df = df.sort_values("涨跌幅", ascending=False)
                return [
                    {
                        "name": row["板块名称"],
                        "change_pct": float(row["涨跌幅"]),
                        "leader": str(row.get("领涨股票", "")),
                    }
                    for _, row in df.head(10).iterrows()
                ]
        except Exception as e:
            console.print(f"[yellow]获取热门概念失败: {e}[/yellow]")
        return []
