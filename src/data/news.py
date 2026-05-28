"""
新闻采集模块
从东方财富、新浪财经等获取新闻
"""

import akshare as ak
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from typing import Optional
from rich.console import Console

console = Console()


class NewsCollector:
    """新闻采集器"""

    def get_stock_news(self, stock_code: str, limit: int = 10) -> list:
        """获取个股新闻"""
        news_list = []
        
        try:
            # 东方财富个股新闻
            df = ak.stock_news_em(symbol=stock_code)
            if not df.empty:
                # 兼容不同版本 akshare 的列名
                title_col = "新闻标题" if "新闻标题" in df.columns else df.columns[0]
                content_col = "新闻内容" if "新闻内容" in df.columns else (df.columns[1] if len(df.columns) > 1 else None)
                source_col = "文章来源" if "文章来源" in df.columns else None
                time_col = "发布时间" if "发布时间" in df.columns else None
                url_col = "新闻链接" if "新闻链接" in df.columns else None
                
                for _, row in df.head(limit).iterrows():
                    item = {"title": str(row.get(title_col, ""))}
                    if content_col:
                        item["content"] = str(row.get(content_col, ""))[:500]
                    if source_col:
                        item["source"] = str(row.get(source_col, ""))
                    if time_col:
                        item["time"] = str(row.get(time_col, ""))
                    if url_col:
                        item["url"] = str(row.get(url_col, ""))
                    news_list.append(item)
        except Exception as e:
            console.print(f"[yellow]获取{stock_code}新闻失败: {e}[/yellow]")

        return news_list

    def get_market_news(self, limit: int = 20) -> list:
        """获取市场要闻"""
        news_list = []
        
        try:
            # 东方财富财经要闻
            df = ak.stock_info_global_em()
            if not df.empty:
                for _, row in df.head(limit).iterrows():
                    news_list.append({
                        "title": str(row.get("标题", "")),
                        "content": str(row.get("摘要", "")),
                        "time": str(row.get("时间", "")),
                    })
        except Exception as e:
            console.print(f"[yellow]获取市场新闻失败: {e}[/yellow]")

        return news_list

    def get_policy_news(self, limit: int = 10) -> list:
        """获取政策法规新闻"""
        news_list = []
        
        try:
            # 新浪财经政策解读
            df = ak.stock_info_global_em()
            keywords = ["政策", "监管", "央行", "国务院", "证监会", "发改委", "财政部", "降息", "降准"]
            if not df.empty:
                for _, row in df.iterrows():
                    title = str(row.get("标题", ""))
                    if any(kw in title for kw in keywords):
                        news_list.append({
                            "title": title,
                            "content": str(row.get("摘要", "")),
                            "time": str(row.get("时间", "")),
                        })
                    if len(news_list) >= limit:
                        break
        except Exception as e:
            console.print(f"[yellow]获取政策新闻失败: {e}[/yellow]")

        return news_list

    def get_hot_concepts(self) -> list:
        """获取热门概念板块"""
        try:
            df = ak.stock_board_concept_name_em()
            if not df.empty:
                df = df.sort_values("涨跌幅", ascending=False)
                return [
                    {"name": row["板块名称"], "change_pct": float(row["涨跌幅"]),
                     "leader": str(row.get("领涨股票", ""))}
                    for _, row in df.head(10).iterrows()
                ]
        except Exception as e:
            console.print(f"[yellow]获取热门概念失败: {e}[/yellow]")
        return []
