from typing import List, Dict
from datetime import datetime, timedelta


def calculate_win_rate(trades: List[dict]) -> float:
    if not trades:
        return 0
    wins = sum(1 for t in trades if t.get("profit_amount", 0) > 0)
    total = len(trades)
    return round(wins / total * 100, 2) if total > 0 else 0


def calculate_profit_loss_ratio(trades: List[dict]) -> float:
    total_profit = sum(
        t.get("profit_amount", 0) for t in trades if t.get("profit_amount", 0) > 0
    )
    total_loss = abs(sum(
        t.get("profit_amount", 0) for t in trades if t.get("profit_amount", 0) < 0
    ))
    return round(total_profit / total_loss, 2) if total_loss > 0 else 0


def calculate_max_drawdown(equity_curve: List[dict]) -> float:
    if not equity_curve:
        return 0
    peak = equity_curve[0]["total_value"]
    max_dd = 0
    for point in equity_curve:
        val = point["total_value"]
        if val > peak:
            peak = val
        dd = (peak - val) / peak * 100
        max_dd = max(max_dd, dd)
    return round(max_dd, 2)


def calculate_sharpe_ratio(equity_curve: List[dict], risk_free_rate: float = 0.02) -> float:
    if len(equity_curve) < 2:
        return 0
    returns = [
        (eq["total_value"] - prev["total_value"]) / prev["total_value"]
        for eq, prev in zip(equity_curve[1:], equity_curve[:-1])
        if prev["total_value"] > 0
    ]
    if not returns:
        return 0
    avg_return = sum(returns) / len(returns)
    std_return = (
        sum((r - avg_return) ** 2 for r in returns) / len(returns)
    ) ** 0.5
    if std_return == 0:
        return 0
    excess_return = avg_return - risk_free_rate / 252
    return round(excess_return / std_return * (252 ** 0.5), 2)


def calculate_total_return(equity_curve: List[dict]) -> float:
    if len(equity_curve) < 2:
        return 0
    start = equity_curve[0]["total_value"]
    end = equity_curve[-1]["total_value"]
    return round((end - start) / start * 100, 2) if start > 0 else 0


def calculate_annual_return(equity_curve: List[dict]) -> float:
    if len(equity_curve) < 2:
        return 0
    start_val = equity_curve[0]["total_value"]
    end_val = equity_curve[-1]["total_value"]
    days = len(equity_curve)
    total_ret = (end_val - start_val) / start_val if start_val > 0 else 0
    years = days / 365
    if years <= 0:
        return 0
    return round(((1 + total_ret) ** (1 / years) - 1) * 100, 2)


def signal_accuracy(signals: List[dict], trades: List[dict]) -> Dict:
    total_signals = len(signals)
    buy_signals = sum(1 for s in signals if s.get("action") in ("buy", "strong_buy"))
    sell_signals = sum(1 for s in signals if s.get("action") in ("sell", "strong_sell"))
    executed_trades = len(trades)
    return {
        "total_signals": total_signals,
        "buy_signals": buy_signals,
        "sell_signals": sell_signals,
        "executed_trades": executed_trades,
        "execution_rate": round(executed_trades / total_signals * 100, 2) if total_signals > 0 else 0,
    }
