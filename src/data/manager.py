from typing import Optional
import pandas as pd
from datetime import datetime, timedelta

from src.data.collector import StockDataCollector
from src.data.news import NewsCollector
from src.data.store import KlineStore, init_database
from src.data.cache import cache


class DataManager:
    def __init__(self):
        self.collector = StockDataCollector()
        self.news = NewsCollector()
        self.kline_store = KlineStore()
        init_database()

    def get_realtime_quote(self, code: str, force_refresh: bool = False) -> dict:
        return cache.get_or_set(
            f"quote:{code}",
            lambda: self.collector.get_realtime_quote(code),
            ttl=30,
            force_refresh=force_refresh,
        )

    def get_kline(self, code: str, period: str = "daily",
                  days: int = 250, force_refresh: bool = False) -> pd.DataFrame:
        if period in ("60min", "15min", "30min"):
            df = self.kline_store.load_kline(code, period)
            if not df.empty and not force_refresh:
                return df
            df = self.collector.get_intraday_kline(code, period=period, days=days)
            if not df.empty:
                self.kline_store.save_kline(code, period, df)
            return df
        df = self.kline_store.load_kline(code, period)
        if not df.empty and not force_refresh:
            latest = df.index[-1].strftime("%Y-%m-%d")
            today = datetime.now().strftime("%Y-%m-%d")
            if latest == today:
                return df
        df = self.collector.get_kline(code, period=period, days=days)
        if not df.empty:
            self.kline_store.save_kline(code, period, df)
        return df

    def get_fund_flow(self, code: str) -> dict:
        return cache.get_or_set(
            f"fund_flow:{code}",
            lambda: self.collector.get_fund_flow(code),
            ttl=300,
        )

    def get_market_index(self) -> dict:
        return cache.get_or_set(
            "market_index",
            lambda: self.collector.get_market_index(),
            ttl=60,
        )

    def get_stock_news(self, code: str, limit: int = 10) -> list:
        return self.news.get_stock_news(code, limit)

    def get_market_news(self, limit: int = 20) -> list:
        return self.news.get_market_news(limit)
