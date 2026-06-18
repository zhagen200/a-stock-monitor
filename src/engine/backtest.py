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
        self.default_buy_threshold = settings.get("backtest.buy_threshold", 15.0)
        self.default_sell_threshold = settings.get("backtest.sell_threshold", -15.0)
        self.position_pct = settings.get("backtest.position_pct", 0.30)
        self.data_manager = DataManager()
        self.signal_store = SignalStore()

    def run(
        self,
        codes: List[str],
        start_date: str,
        end_date: str,
        on_signal: Optional[Callable] = None,
        buy_threshold: float | None = None,
        sell_threshold: float | None = None,
    ) -> BacktestResult:
        buy_threshold = buy_threshold if buy_threshold is not None else self.default_buy_threshold
        sell_threshold = sell_threshold if sell_threshold is not None else self.default_sell_threshold

        cash = self.initial_cash
        positions: Dict[str, dict] = {}
        total_trades = 0
        wins = 0
        losses = 0
        total_profit = 0.0
        total_loss = 0.0
        peak = self.initial_cash
        max_drawdown = 0.0
        equity_curve = []

        # 预加载数据
        all_klines: Dict[str, pd.DataFrame] = {}
        for code_entry in codes:
            code = code_entry["code"] if isinstance(code_entry, dict) else code_entry
            df = self.data_manager.get_kline(code, days=500)
            if not df.empty:
                all_klines[code] = df

        if not all_klines:
            return BacktestResult()

        # 收集所有交易日并排序去重
        all_dates = set()
        for code, df in all_klines.items():
            mask = (df.index >= start_date) & (df.index <= end_date)
            all_dates.update(df[mask].index.tolist())

        trading_days = sorted(all_dates)
        if not trading_days:
            return BacktestResult()

        day_count = 0

        for trade_date in trading_days:
            date_str = trade_date.strftime("%Y-%m-%d") if hasattr(trade_date, 'strftime') else str(trade_date)[:10]
            day_count += 1
            total_value = cash

            for code_entry in codes:
                code = code_entry["code"] if isinstance(code_entry, dict) else code_entry
                name = code_entry.get("name", code) if isinstance(code_entry, dict) else code

                if code not in all_klines:
                    continue

                full_df = all_klines[code]
                # 截取到当前交易日
                df = full_df[full_df.index <= trade_date]
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

                # 回测使用自定义阈值（默认±10），而非实时监控的高阈值
                action = signal.action
                if signal.score >= abs(buy_threshold) * 2.5:
                    action = "strong_buy"
                elif signal.score >= abs(buy_threshold):
                    action = "buy"
                elif signal.score <= sell_threshold * 2.5:
                    action = "strong_sell"
                elif signal.score <= sell_threshold:
                    action = "sell"
                else:
                    action = "hold"

                if self.risk_manager:
                    ctx = {"change_pct": 0}
                    risk_result = self.risk_manager.check(signal, ctx)
                    if not risk_result.passed:
                        continue

                self.signal_store.save_signal(signal, is_backtest=1)

                if on_signal:
                    on_signal(signal)

                if action in ("strong_buy", "buy") and code not in positions:
                    pct = self.position_pct if action == "strong_buy" else self.position_pct * 0.5
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

                elif action in ("strong_sell", "sell") and code in positions:
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
            equity_curve.append({"date": date_str, "value": round(total_value, 2)})

        # 未平仓按最后价格结算
        for code, pos in positions.items():
            if code in all_klines:
                last_price = float(all_klines[code].iloc[-1]["close"])
                total_value += pos["volume"] * last_price - pos["volume"] * pos["cost"]

        total_return = (total_value - self.initial_cash) / self.initial_cash * 100
        years = day_count / 252 if day_count > 0 else 0.01
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
            equity_curve=equity_curve,
        )