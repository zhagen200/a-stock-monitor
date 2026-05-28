from typing import List, Dict
from datetime import datetime

from src.analytics import metrics
from src.data.store import SignalStore, TradeStore


class ReportGenerator:
    def __init__(self):
        self.signal_store = SignalStore()
        self.trade_store = TradeStore()

    def generate_performance_report(self, equity_curve: List[dict] = None) -> str:
        trades = self.trade_store.get_trades(limit=200)
        signals = self.signal_store.get_signals(limit=200)

        if not equity_curve:
            equity_curve = []

        total_return = metrics.calculate_total_return(equity_curve)
        annual_return = metrics.calculate_annual_return(equity_curve)
        max_dd = metrics.calculate_max_drawdown(equity_curve)
        sharpe = metrics.calculate_sharpe_ratio(equity_curve) if equity_curve else 0
        win_rate = metrics.calculate_win_rate(trades)
        pl_ratio = metrics.calculate_profit_loss_ratio(trades)
        acc = metrics.signal_accuracy(signals, trades)

        lines = [
            "=" * 50,
            "  绩效分析报告",
            f"  生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            "=" * 50,
            "",
            "【收益指标】",
            f"  总收益率: {total_return:.2f}%",
            f"  年化收益率: {annual_return:.2f}%",
            f"  最大回撤: {max_dd:.2f}%",
            f"  夏普比率: {sharpe}",
            "",
            "【交易统计】",
            f"  总交易次数: {acc['executed_trades']}",
            f"  胜率: {win_rate:.2f}%",
            f"  盈亏比: {pl_ratio}",
            "",
            "【信号统计】",
            f"  总信号数: {acc['total_signals']}",
            f"  买入信号: {acc['buy_signals']}",
            f"  卖出信号: {acc['sell_signals']}",
            f"  信号执行率: {acc['execution_rate']:.2f}%",
            "",
            "=" * 50,
        ]
        return "\n".join(lines)
