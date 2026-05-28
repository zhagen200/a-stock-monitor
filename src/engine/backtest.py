from typing import Dict, List, Optional, Callable
from datetime import datetime, timedelta
import pandas as pd

from src.core.base import TradeSignal, BacktestResult
from src.core.config import settings
from src.data.manager import DataManager
from src.strategy.ensemble import EnsembleStrategy
from src.risk.manager import RiskManager
from src.data.store import SignalStore


class BacktestEngine:
    def __init__(
        self,
        ensemble: EnsembleStrategy,
        risk_manager: Optional[RiskManager] = None,
        initial_cash: float | None = None,
        commission_rate: float | None = None,
    ):
        settings.load()
        self.ensemble = ensemble
        self.risk_manager = risk_manager
        self.initial_cash = initial_cash or settings.get("backtest.initial_cash", 100000)
        self.commission_rate = commission_rate or settings.get("backtest.commission_rate", 0.00025)
        self.data_manager = DataManager()
        self.signal_store = SignalStore()

    def run(
        self,
        codes: List[str],
        start_date: str,
        end_date: str,
        on_signal: Optional[Callable] = None,
    ) -> BacktestResult:
        cash = self.initial_cash
        positions: Dict[str, dict] = {}
        total_trades = 0
        wins = 0
        losses = 0
        total_profit = 0.0
        total_loss = 0.0
        peak = self.initial_cash
        max_drawdown = 0.0

        current = datetime.strptime(start_date, "%Y-%m-%d")
        end = datetime.strptime(end_date, "%Y-%m-%d")
        day_count = 0

        # 预加载数据：先获取一次所有K线数据存入DB
        for code_entry in codes:
            code = code_entry["code"] if isinstance(code_entry, dict) else code_entry
            self.data_manager.get_kline(code, days=500, force_refresh=True)

        while current <= end:
            date_str = current.strftime("%Y-%m-%d")
            day_count += 1
            total_value = cash

            for code_entry in codes:
                code = code_entry["code"] if isinstance(code_entry, dict) else code_entry
                name = code_entry.get("name", code) if isinstance(code_entry, dict) else code

                # 从DB取截止到当前日期的数据
                df = self.data_manager.kline_store.load_kline(
                    code, start="", end=date_str
                )
                if df.empty or len(df) < 60:
                    continue

                price = float(df.iloc[-1]["close"])
                if price <= 0:
                    continue

                fund_flow = self.data_manager.get_fund_flow(code)

                signal = self.ensemble.generate(code, name, price, {
                    "kline_daily": df,
                    "fund_flow": fund_flow,
                    "news_score": 0,
                })

                if self.risk_manager:
                    ctx = {"change_pct": 0}
                    risk_result = self.risk_manager.check(signal, ctx)
                    if not risk_result.passed:
                        continue

                signal_id = self.signal_store.save_signal(signal, is_backtest=1)

                if on_signal:
                    on_signal(signal)

                if signal.action in ("strong_buy", "buy") and code not in positions:
                    pct = max(signal.position_pct / 100, 0.05)
                    invest = cash * pct
                    min_cost = price * 100
                    if invest >= min_cost:
                        volume = int(invest / price / 100) * 100
                        cost = volume * price
                        fee = cost * self.commission_rate
                        if cost + fee <= cash:
                            cash -= (cost + fee)
                            positions[code] = {
                                "code": code, "name": name,
                                "volume": volume, "cost": price,
                                "buy_date": date_str,
                            }
                            total_trades += 1

                elif signal.action in ("strong_sell", "sell") and code in positions:
                    pos = positions[code]
                    revenue = pos["volume"] * price
                    fee = revenue * self.commission_rate
                    profit = revenue - pos["volume"] * pos["cost"] - fee
                    cash += (revenue - fee)
                    if profit > 0:
                        wins += 1
                        total_profit += profit
                    else:
                        losses += 1
                        total_loss += abs(profit)
                    del positions[code]
                    total_trades += 1

                if code in positions:
                    pos = positions[code]
                    market_value = pos["volume"] * price
                    total_value += market_value
                else:
                    total_value = cash

            if total_value > peak:
                peak = total_value
            dd = (peak - total_value) / peak * 100 if peak > 0 else 0
            max_drawdown = max(max_drawdown, dd)

            current += timedelta(days=1)

        total_return = (total_value - self.initial_cash) / self.initial_cash * 100
        years = day_count / 365 if day_count > 0 else 0.01
        annual_return = ((1 + total_return / 100) ** (1 / years) - 1) * 100 if years > 0 else 0
        win_rate = wins / (wins + losses) * 100 if (wins + losses) > 0 else 0
        profit_loss_ratio = total_profit / total_loss if total_loss > 0 else 0

        return BacktestResult(
            total_return=round(total_return, 2),
            annual_return=round(annual_return, 2),
            max_drawdown=round(max_drawdown, 2),
            sharpe_ratio=0,
            win_rate=round(win_rate, 2),
            profit_loss_ratio=round(profit_loss_ratio, 2),
            total_trades=total_trades,
            equity_curve=[],
        )
