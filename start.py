#!/usr/bin/env python3
"""
快速启动脚本
"""

import sys
from pathlib import Path

project_dir = Path(__file__).parent
sys.path.insert(0, str(project_dir))


def main():
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
    args = parser.parse_args()

    from main import main as run_main
    sys.argv = [sys.argv[0]]
    for attr in ["mode", "interval", "backtest_start", "backtest_end", "auto_execute"]:
        val = getattr(args, attr, None)
        if val:
            flag = f"--{attr.replace('_', '-')}"
            if isinstance(val, bool):
                if val:
                    sys.argv.append(flag)
            else:
                sys.argv.extend([flag, str(val)])

    run_main()


if __name__ == "__main__":
    main()
