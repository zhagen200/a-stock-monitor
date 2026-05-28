#!/usr/bin/env python3
"""
A股量化交易系统 - 统一入口
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))


def main():
    from src.core.config import settings
    settings.load()

    from src.engine.live import LiveEngine
    from src.engine.backtest import BacktestEngine
    from src.strategy.technical import TechnicalStrategy
    from src.strategy.capital_flow import CapitalFlowStrategy
    from src.strategy.news_sentiment import NewsSentimentStrategy
    from src.strategy.ensemble import EnsembleStrategy
    from src.risk.manager import RiskManager
    from src.risk.rules import PositionLimitRule, MarketRegimeFilter, ConsecutiveLossRule

    import argparse
    parser = argparse.ArgumentParser(description="A股量化交易系统")
    parser.add_argument("--mode", choices=["once", "loop", "web", "backtest"],
                       default="once", help="运行模式")
    parser.add_argument("--interval", type=int, default=5,
                       help="监控间隔(分钟)")
    parser.add_argument("--backtest-start", default="2025-01-01",
                       help="回测开始日期")
    parser.add_argument("--backtest-end", default="2025-12-31",
                       help="回测结束日期")
    parser.add_argument("--auto-execute", action="store_true",
                       help="自动执行交易（慎用）")
    parser.add_argument("--scan-code", default="",
                       help="扫描指定股票代码")
    parser.add_argument("--scan-name", default="",
                       help="扫描股票名称")
    args = parser.parse_args()

    if args.scan_code:
        engine = LiveEngine()
        stock = {"code": args.scan_code, "name": args.scan_name or args.scan_code}
        signal = engine.scan_stock(stock)
        if signal:
            print(f"\n{signal.name}({signal.code})")
            print(f"  操作: {signal.action}  评分: {signal.score:.1f}")
            print(f"  置信度: {signal.confidence:.0f}%")
            print(f"  当前价: ¥{signal.price:.2f}")
            print(f"  止损: ¥{signal.stop_loss:.2f}")
            print(f"  止盈: ¥{signal.take_profit_1:.2f} / ¥{signal.take_profit_2:.2f}")
            if signal.reasons:
                for r in signal.reasons:
                    print(f"  · {r}")
        return

    if args.mode == "backtest":
        strategies = [
            TechnicalStrategy(),
            CapitalFlowStrategy(),
            NewsSentimentStrategy(),
        ]
        ensemble = EnsembleStrategy(strategies)
        risk_manager = RiskManager([
            PositionLimitRule(),
            MarketRegimeFilter(),
            ConsecutiveLossRule(),
        ])
        engine = BacktestEngine(
            ensemble=ensemble,
            risk_manager=risk_manager,
        )
        watchlist = settings.get_watchlist()
        result = engine.run(
            codes=watchlist,
            start_date=args.backtest_start,
            end_date=args.backtest_end,
        )
        print("\n" + "=" * 50)
        print("  回测结果")
        print("=" * 50)
        print(f"  总收益率: {result.total_return:.2f}%")
        print(f"  年化收益: {result.annual_return:.2f}%")
        print(f"  最大回撤: {result.max_drawdown:.2f}%")
        print(f"  夏普比率: {result.sharpe_ratio}")
        print(f"  胜率: {result.win_rate:.2f}%")
        print(f"  盈亏比: {result.profit_loss_ratio}")
        print(f"  交易次数: {result.total_trades}")
        print("=" * 50)

        if result.equity_curve:
            import pandas as pd
            df = pd.DataFrame(result.equity_curve)
            print(f"\n收益率曲线 (前10行):")
            print(df.head(10).to_string(index=False))
        return

    if args.mode == "web":
        import subprocess
        subprocess.run([
            sys.executable, "-m", "streamlit", "run",
            str(Path(__file__).parent / "src" / "web" / "app.py"),
            "--server.port", "8501",
            "--theme.base", "dark",
        ])
        return

    engine = LiveEngine(auto_execute=args.auto_execute)

    if args.mode == "once":
        engine.run_once()
    else:
        engine.run_loop(args.interval)


if __name__ == "__main__":
    main()
