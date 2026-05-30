"""
A股数据采集模块
使用腾讯行情API获取实时数据，AKShare获取历史数据
"""

import requests
import pandas as pd
import os
import time
import json
from datetime import datetime, timedelta
from typing import Optional
from rich.console import Console

console = Console()
MAX_RETRIES = 2
RETRY_DELAY = 2

# 设置不使用代理
os.environ['NO_PROXY'] = '*'
os.environ['no_proxy'] = '*'


class StockDataCollector:
    """A股数据采集器"""

    def __init__(self):
        self.session = requests.Session()
        self.session.trust_env = False
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/120.0.0.0 Safari/537.36",
        })

    def _get_market_prefix(self, code: str) -> str:
        return "sh" if code.startswith("6") or code.startswith("5") else "sz"

    def _request_with_retry(self, url: str, params: dict = None,
                            timeout: int = 15, method: str = "GET",
                            data: dict = None) -> requests.Response:
        last_err = None
        for attempt in range(MAX_RETRIES + 1):
            try:
                if method == "GET":
                    if params:
                        return self.session.get(url, params=params, timeout=timeout)
                    return self.session.get(url, timeout=timeout)
                else:
                    return self.session.post(url, json=data, timeout=timeout)
            except Exception as e:
                last_err = e
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_DELAY * (attempt + 1))
        raise last_err

    def get_realtime_quote(self, stock_code: str) -> dict:
        """获取个股实时行情 (使用腾讯行情API)"""
        try:
            symbol = f"{self._get_market_prefix(stock_code)}{stock_code}"
            url = f"https://qt.gtimg.cn/q={symbol}"
            resp = self._request_with_retry(url, timeout=10)
            data = resp.text.split("~")

            if len(data) < 50:
                return {}

            # 解析盘口数据（买卖五档）
            def _tf(v, default=0):
                try: return float(v.strip()) if v and v.strip() else default
                except: return default

            bids, asks = [], []
            if len(data) >= 30:
                b1p = _tf(data[11])
                # 检测格式: [18]/[19] 若价格>买一价, 则卖一始于[18]
                sell_start = 18 if _tf(data[19]) > b1p else 20
                for i in range(5):
                    idx = 10 + i*2
                    if idx + 1 < len(data):
                        p, v = _tf(data[idx+1]), _tf(data[idx])
                        if p > 0 and (sell_start != 18 or idx < sell_start):
                            bids.append({"price": p, "volume": v})
                for i in range(5):
                    idx = sell_start + i*2
                    if idx + 1 < len(data):
                        p, v = _tf(data[idx+1]), _tf(data[idx])
                        if p > 0:
                            asks.append({"price": p, "volume": v})

            return {
                "code": stock_code,
                "name": data[1].strip(),
                "price": float(data[3]) if data[3] else 0,
                "pre_close": float(data[4]) if data[4] else 0,
                "open": float(data[5]) if data[5] else 0,
                "volume": float(data[6]) if data[6] else 0,
                "amount": float(data[37]) * 10000 if data[37] else 0,
                "high": float(data[33]) if data[33] else float(data[3] or 0),
                "low": float(data[34]) if data[34] else float(data[3] or 0),
                "change_pct": float(data[32]) if data[32] else 0,
                "change_amount": float(data[31]) if data[31] else 0,
                "turnover_rate": float(data[38]) if data[38] else 0,
                "pe_ratio": float(data[39]) if data[39] else 0,
                "pb_ratio": float(data[46]) if data[46] else 0,
                "total_mv": float(data[45]) if data[45] else 0,
                "circ_mv": float(data[44]) if data[44] else 0,
                "bids": bids,
                "asks": asks,
                "timestamp": datetime.now().isoformat(),
            }
        except Exception as e:
            console.print(f"[red]获取{stock_code}实时行情失败: {e}[/red]")
            return {}

    def get_kline(self, stock_code: str, period: str = "daily",
                  days: int = 250, adjust: str = "qfq") -> pd.DataFrame:
        """获取历史K线数据 (先查缓存, 腾讯API优先, AKShare回退)"""
        try:
            symbol = f"{self._get_market_prefix(stock_code)}{stock_code}"
            period_map = {"daily": "day", "weekly": "week", "monthly": "month"}
            p = period_map.get(period, "day")

            url = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
            params = {"param": f"{symbol},{p},,,{days},{adjust}"}
            resp = self._request_with_retry(url, params=params, timeout=15)
            data = resp.json()

            raw_data = data.get("data", {})
            if isinstance(raw_data, list):
                return self._get_kline_akshare(stock_code, period, days, adjust)

            kline_data = raw_data.get(symbol, {})
            lines = (kline_data.get(f"{adjust}{p}")
                     or kline_data.get(p)
                     or [])

            if not lines:
                return self._get_kline_akshare(stock_code, period, days, adjust)

            if len(lines[0]) >= 6:
                df = pd.DataFrame(
                    [row[:6] for row in lines],
                    columns=["date", "open", "close", "high", "low", "volume"],
                )
            else:
                return self._get_kline_akshare(stock_code, period, days, adjust)

            df["date"] = pd.to_datetime(df["date"])
            df = df.set_index("date").sort_index()
            for col in ["open", "close", "high", "low", "volume"]:
                df[col] = pd.to_numeric(df[col], errors="coerce")

            return df
        except Exception as e:
            console.print(f"[yellow]腾讯K线API失败: {e}[/yellow]")
            return self._get_kline_akshare(stock_code, period, days, adjust)

    def _get_kline_akshare(self, stock_code: str, period: str,
                           days: int, adjust: str) -> pd.DataFrame:
        """AKShare备用K线"""
        try:
            import akshare as ak
            end_date = datetime.now().strftime("%Y%m%d")
            start_date = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")
            df = ak.stock_zh_a_hist(
                symbol=stock_code, period=period,
                start_date=start_date, end_date=end_date, adjust=adjust,
            )
        except Exception:
            return pd.DataFrame()

        if df is None or df.empty:
            return pd.DataFrame()

        col_map = {
            "日期": "date", "开盘": "open", "收盘": "close",
            "最高": "high", "最低": "low", "成交量": "volume",
        }
        rename_map = {k: v for k, v in col_map.items() if k in df.columns}
        df = df.rename(columns=rename_map)
        needed = ["date", "open", "close", "high", "low", "volume"]
        available = [c for c in needed if c in df.columns]
        df = df[available]
        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"])
            df = df.set_index("date").sort_index()
        for col in ["open", "close", "high", "low", "volume"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        return df

    def get_fund_flow(self, stock_code: str) -> dict:
        """获取个股资金流向 (双数据源)"""
        # 方案A: akshare (单次尝试)
        try:
            import akshare as ak
            market = "sh" if stock_code.startswith("6") else "sz"
            df = ak.stock_individual_fund_flow(stock=stock_code, market=market)
            if df is not None and not df.empty:
                latest = df.iloc[-1]
                return {
                    "date": str(latest.get("日期", "")),
                    "main_net_inflow": float(latest.get("主力净流入-净额", 0)),
                    "main_net_pct": float(latest.get("主力净流入-净占比", 0)),
                }
        except Exception:
            pass

        # 方案B: 东方财富HTTP接口直连
        try:
            url = ("https://push2.eastmoney.com/api/qt/stock/fflow/"
                   "daykline/get?secid={}.{}&fields1=f1,f2,f3,f7&fields2=f51,f52,f53,f54,f55")
            market = 1 if stock_code.startswith("6") else 0
            resp = self._request_with_retry(
                url.format(market, stock_code), timeout=10
            )
            result = resp.json()
            data = result.get("data", {}).get("klines", [])
            if data:
                last = data[-1].split(",")
                return {
                    "date": last[0],
                    "main_net_inflow": float(last[1]) if len(last) > 1 else 0,
                    "main_net_pct": float(last[4]) if len(last) > 4 else 0,
                }
        except Exception:
            pass

        # 方案C: 从实时行情估算 (基于涨跌+成交额)
        try:
            quote = self.get_realtime_quote(stock_code)
            if quote:
                change_pct = quote.get("change_pct", 0)
                amount = quote.get("amount", 0)
                estimated_main = amount * (change_pct / 100) * 0.3
                return {
                    "date": datetime.now().strftime("%Y-%m-%d"),
                    "main_net_inflow": round(estimated_main * 10000, 2),
                    "main_net_pct": round(change_pct * 0.5, 2),
                    "estimated": True,
                }
        except Exception:
            pass

        return {}

    def get_fund_nav(self, fund_code: str) -> dict:
        """获取基金净值 (使用腾讯行情API)"""
        try:
            symbol = f"sh{fund_code}" if fund_code.startswith("5") else f"sz{fund_code}"
            url = f"https://qt.gtimg.cn/q={symbol}"
            resp = self._request_with_retry(url, timeout=10)
            data = resp.text.split("~")

            if len(data) < 30:
                return {}

            return {
                "code": fund_code,
                "name": data[1],
                "price": float(data[3]) if data[3] else 0,
                "change_pct": float(data[32]) if data[32] else 0,
                "volume": float(data[6]) if data[6] else 0,
                "amount": float(data[37]) if data[37] else 0,
            }
        except Exception as e:
            console.print(f"[red]获取基金{fund_code}数据失败: {e}[/red]")
            return {}

    def get_market_index(self) -> dict:
        """获取大盘指数 (使用腾讯行情API)"""
        try:
            indices = {
                "上证指数": "sh000001",
                "深证成指": "sz399001",
                "创业板指": "sz399006",
            }
            result = {}
            symbols = ",".join(indices.values())
            url = f"https://qt.gtimg.cn/q={symbols}"
            resp = self._request_with_retry(url, timeout=10)

            for line in resp.text.strip().split(";"):
                if not line.strip():
                    continue
                parts = line.split("~")
                if len(parts) < 35:
                    continue

                for name, sym in indices.items():
                    if sym in line:
                        result[name] = {
                            "code": parts[2],
                            "price": float(parts[3]) if parts[3] else 0,
                            "change_pct": float(parts[32]) if parts[32] else 0,
                            "volume": float(parts[6]) if parts[6] else 0,
                        }
            return result
        except Exception as e:
            console.print(f"[red]获取大盘指数失败: {e}[/red]")
            return {}

    def get_intraday_kline(self, stock_code: str, period: str = "60min",
                           days: int = 60) -> pd.DataFrame:
        """获取分钟级K线"""
        try:
            import akshare as ak
            end = datetime.now()
            start = end - timedelta(days=days)
            df = ak.stock_zh_a_hist_min_em(
                symbol=stock_code,
                period={"15min": "15", "30min": "30", "60min": "60"}.get(period, "60"),
                start_date=start.strftime("%Y%m%d"),
                end_date=end.strftime("%Y%m%d"),
            )
            if df is not None and not df.empty:
                col_map = {"时间": "date", "开盘": "open", "收盘": "close",
                           "最高": "high", "最低": "low", "成交量": "volume"}
                rename = {k: v for k, v in col_map.items() if k in df.columns}
                df = df.rename(columns=rename)
                needed = [c for c in ["date", "open", "close", "high", "low", "volume"] if c in df.columns]
                df = df[needed]
                df["date"] = pd.to_datetime(df["date"])
                df = df.set_index("date").sort_index()
                for c in ["open", "close", "high", "low", "volume"]:
                    df[c] = pd.to_numeric(df[c], errors="coerce")
                return df
        except Exception:
            pass
        return pd.DataFrame()

    def get_sector_flow(self) -> pd.DataFrame:
        """获取板块资金流向"""
        try:
            import akshare as ak
            df = ak.stock_sector_fund_flow_rank(
                indicator="今日", sector_type="行业资金流"
            )
            if df is not None and not df.empty:
                return df.head(20)
        except Exception:
            pass
        return pd.DataFrame()
