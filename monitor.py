#!/usr/bin/env python3
"""
A股智能量化监控系统 - 主程序
实时监控股票和基金，生成买卖信号
"""

import sys
import time
import yaml
import signal
import os
import logging
from pathlib import Path

# 设置不使用代理访问股票数据API
os.environ['NO_PROXY'] = '*'
os.environ['no_proxy'] = '*'
from datetime import datetime
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

from src.data.collector import StockDataCollector
from src.data.news import NewsCollector
from src.analysis.technical import TechnicalAnalyzer
from src.analysis.signal_engine import SignalEngine
from src.llm.client import LLMClient
from src.notify.notifier import Notifier

# Rich console 用于终端显示
console = Console()

# 纯文本日志 - 始终写入文件，不受 Rich 影响
LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

def setup_logger():
    """配置纯文本日志"""
    logger = logging.getLogger("stock_monitor")
    logger.setLevel(logging.INFO)
    # 文件 handler
    fh = logging.FileHandler(LOG_DIR / "monitor.log", encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s %(message)s", datefmt="%H:%M:%S"))
    logger.addHandler(fh)
    return logger

log = setup_logger()


class StockMonitor:
    """A股监控系统"""

    def __init__(self, config_path: str = "config/settings.yaml"):
        self.config = self._load_config(config_path)
        
        # 初始化各模块
        self.collector = StockDataCollector()
        self.news_collector = NewsCollector()
        self.technical = TechnicalAnalyzer()
        self.signal_engine = SignalEngine(self.config)
        self.notifier = Notifier(self.config)
        
        # LLM客户端 (可选)
        llm_config = self.config.get("llm", {})
        if llm_config.get("enabled", True):
            self.llm = LLMClient(
                api_base=llm_config.get("api_base", "http://localhost:11434/v1"),
                model=llm_config.get("model", "qwen2.5"),
                api_key=llm_config.get("api_key", "not-needed"),
            )
        else:
            self.llm = None

        self.watchlist = self.config.get("watchlist", {})
        # 仅对这些股票启用 LLM 新闻分析（持仓 + 重点关注）
        self.llm_stocks = {"002195", "002640", "600580"}
        self.signals_history = []
        self.running = False

    def _load_config(self, path: str) -> dict:
        """加载配置文件"""
        try:
            with open(path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except FileNotFoundError:
            console.print(f"[yellow]配置文件不存在: {path}，使用默认配置[/yellow]")
            return {}

    def scan_stock(self, stock_code: str, stock_name: str) -> dict:
        """扫描单只股票"""
        console.print(f"[cyan]扫描 {stock_name}({stock_code})...[/cyan]")
        log.info(f"扫描 {stock_name}({stock_code})...")
        
        # 1. 获取实时行情
        quote = self.collector.get_realtime_quote(stock_code)
        if not quote:
            return None
        price = quote["price"]

        # 2. 获取K线数据
        kline = self.collector.get_kline(stock_code, days=250)
        if kline.empty:
            return None

        # 3. 技术分析
        tech_result = self.technical.analyze(kline, price)

        # 4. 资金流向
        fund_flow = self.collector.get_fund_flow(stock_code)

        # 5. 新闻分析 (仅持仓/重点关注股启用LLM)
        news_score = 0.0
        news_list = []
        if self.llm and self.llm.enabled and stock_code in self.llm_stocks:
            news_list = self.news_collector.get_stock_news(stock_code, limit=5)
            if news_list:
                # 合并所有新闻标题为一次 LLM 调用，大幅减少 API 次数
                all_titles = "\n".join([f"- {n.get('title', '')}" for n in news_list])
                analysis = self.llm.analyze_news(all_titles, stock_code)
                news_score = analysis.get("score", 0)

        # 6. 生成信号
        signal = self.signal_engine.generate_signal(
            code=stock_code,
            name=stock_name,
            price=price,
            technical_result=tech_result,
            fund_flow=fund_flow,
            news_sentiment=news_score,
        )

        return {
            "quote": quote,
            "signal": signal,
            "tech_result": tech_result,
            "fund_flow": fund_flow,
            "news_list": news_list,
        }

    def scan_fund(self, fund_code: str, fund_name: str) -> dict:
        """扫描基金"""
        console.print(f"[cyan]扫描 {fund_name}({fund_code})...[/cyan]")
        log.info(f"扫描 {fund_name}({fund_code})...")
        
        fund_data = self.collector.get_fund_nav(fund_code)
        if not fund_data:
            return None

        # ETF基金也可以做技术分析
        kline = self.collector.get_kline(fund_code, days=250)
        if not kline.empty:
            tech_result = self.technical.analyze(kline, fund_data.get("price", 0))
            signal = self.signal_engine.generate_signal(
                code=fund_code,
                name=fund_name,
                price=fund_data.get("price", 0),
                technical_result=tech_result,
            )
            return {"data": fund_data, "signal": signal}
        
        return {"data": fund_data, "signal": None}

    def scan_all(self) -> list:
        """扫描全部自选股"""
        results = []
        now = datetime.now().strftime("%H:%M:%S")
        
        console.print("\n" + "=" * 60)
        console.print(f"[bold]🔍 开始扫描 [{now}][/bold]")
        console.print("=" * 60)
        log.info(f"{'='*60}")
        log.info(f"开始扫描 [{now}]")

        # 扫描大盘指数
        indices = self.collector.get_market_index()
        if indices:
            console.print("\n[bold]📊 大盘指数[/bold]")
            for name, data in indices.items():
                change_color = "red" if data["change_pct"] > 0 else "green"
                console.print(f"  {name}: {data['price']:.2f} [{change_color}]{data['change_pct']:+.2f}%[/{change_color}]")
                log.info(f"  {name}: {data['price']:.2f} {data['change_pct']:+.2f}%")

        # 扫描个股
        for stock in self.watchlist.get("stocks", []):
            result = self.scan_stock(stock["code"], stock["name"])
            if result:
                results.append(result)
                # 发送重要信号
                if result["signal"].action in ("strong_buy", "strong_sell"):
                    self.notifier.send_signal(result["signal"])

        # 扫描基金
        for fund in self.watchlist.get("funds", []):
            result = self.scan_fund(fund["code"], fund["name"])
            if result:
                results.append(result)

        # 显示结果汇总
        self._display_results(results)
        self._log_results(results)
        
        return results

    def _display_results(self, results: list):
        """终端显示扫描结果（Rich）"""
        table = Table(title="📊 信号汇总", show_lines=True)
        table.add_column("股票", style="cyan", width=12)
        table.add_column("现价", justify="right", width=8)
        table.add_column("涨跌", justify="right", width=8)
        table.add_column("操作", justify="center", width=10)
        table.add_column("评分", justify="right", width=6)
        table.add_column("置信度", justify="center", width=12)
        table.add_column("止损", justify="right", width=8)
        table.add_column("止盈", justify="right", width=12)

        action_styles = {
            "strong_buy": "[bold red]🔴强买[/bold red]",
            "buy": "[red]🟠买入[/red]",
            "hold": "[white]⚪观望[/white]",
            "sell": "[green]🟢卖出[/green]",
            "strong_sell": "[bold green]🔵强卖[/bold green]",
        }

        for r in results:
            sig = r.get("signal")
            if not sig:
                continue
            
            quote = r.get("quote") or r.get("data", {})
            change_pct = quote.get("change_pct", 0)
            change_color = "red" if change_pct > 0 else "green"
            
            table.add_row(
                f"{sig.name}",
                f"¥{sig.price:.2f}",
                f"[{change_color}]{change_pct:+.2f}%[/{change_color}]",
                action_styles.get(sig.action, sig.action),
                f"{sig.score:.0f}",
                f"{'█' * int(sig.confidence/10)}{'░' * (10-int(sig.confidence/10))} {sig.confidence:.0f}%",
                f"¥{sig.stop_loss:.2f}",
                f"¥{sig.take_profit_1:.2f} / ¥{sig.take_profit_2:.2f}",
            )

        console.print(table)

        # 显示强烈信号详情
        for r in results:
            sig = r.get("signal")
            if sig and sig.action in ("strong_buy", "strong_sell"):
                panel_content = (
                    f"[bold]{sig.name}({sig.code}) - {action_styles.get(sig.action)}[/bold]\n"
                    f"当前价: ¥{sig.price:.2f}  评分: {sig.score:.1f}  置信度: {sig.confidence:.0f}%\n"
                    f"止损: ¥{sig.stop_loss:.2f}  止盈: ¥{sig.take_profit_1:.2f}/¥{sig.take_profit_2:.2f}\n"
                    f"建议仓位: {sig.position_pct:.0f}%\n\n"
                    f"信号依据:\n" + "\n".join([f"  • {r}" for r in sig.reasons[:5]])
                )
                console.print(Panel(
                    panel_content,
                    title=f"⚡ {'强烈买入' if 'buy' in sig.action else '强烈卖出'}信号",
                    border_style="red" if "buy" in sig.action else "green",
                ))

    def _log_results(self, results: list):
        """将扫描结果写入纯文本日志"""
        action_map = {
            "strong_buy": "🔴强买",
            "buy": "🟠买入",
            "hold": "⚪观望",
            "sell": "🟢卖出",
            "strong_sell": "🔵强卖",
        }
        log.info(f"{'─'*60}")
        log.info(f"{'股票':<10} {'现价':>8} {'涨跌':>8} {'操作':<8} {'评分':>6} {'置信度':>6} {'止损':>8} {'止盈':>20}")
        log.info(f"{'─'*60}")
        for r in results:
            sig = r.get("signal")
            if not sig:
                continue
            quote = r.get("quote") or r.get("data", {})
            chg = quote.get("change_pct", 0)
            log.info(
                f"{sig.name:<10} ¥{sig.price:>7.2f} {chg:>+7.2f}% "
                f"{action_map.get(sig.action, sig.action):<8} "
                f"{sig.score:>5.0f}  {sig.confidence:>5.0f}% "
                f"¥{sig.stop_loss:>7.2f}  ¥{sig.take_profit_1:.2f}/¥{sig.take_profit_2:.2f}"
            )
            # 记录信号依据
            if sig.reasons:
                for reason in sig.reasons[:3]:
                    log.info(f"  · {reason}")
        log.info(f"{'─'*60}")

    def run_once(self):
        """执行一次扫描"""
        self.scan_all()

    def run_loop(self, interval_minutes: int = 5):
        """持续监控模式"""
        self.running = True
        
        def stop_handler(sig, frame):
            console.print("\n[yellow]正在停止监控...[/yellow]")
            log.info("正在停止监控...")
            self.running = False
        
        signal.signal(signal.SIGINT, stop_handler)
        signal.signal(signal.SIGTERM, stop_handler)

        console.print("[bold green]🚀 A股监控系统启动[/bold green]")
        console.print(f"   监控间隔: {interval_minutes}分钟")
        console.print(f"   自选股: {len(self.watchlist.get('stocks', []))}只")
        console.print(f"   基金: {len(self.watchlist.get('funds', []))}只")
        console.print(f"   LLM: {'✅ 已启用' if self.llm and self.llm.enabled else '❌ 未启用'}")
        console.print(f"   按 Ctrl+C 停止\n")
        
        log.info(f"🚀 A股监控系统启动 | 间隔:{interval_minutes}分钟 | 自选股:{len(self.watchlist.get('stocks', []))}只 | 基金:{len(self.watchlist.get('funds', []))}只 | LLM:{'✅' if self.llm and self.llm.enabled else '❌'}")

        while self.running:
            try:
                self.scan_all()
                if self.running:
                    next_time = (datetime.now().timestamp() + interval_minutes * 60)
                    next_str = datetime.fromtimestamp(next_time).strftime("%H:%M:%S")
                    console.print(f"\n[dim]⏰ 下次扫描: {next_str}[/dim]")
                    log.info(f"下次扫描: {next_str}")
                    for _ in range(interval_minutes * 60):
                        if not self.running:
                            break
                        time.sleep(1)
            except KeyboardInterrupt:
                break
            except Exception as e:
                console.print(f"[red]扫描出错: {e}[/red]")
                log.error(f"扫描出错: {e}")
                time.sleep(30)

        console.print("[yellow]监控已停止[/yellow]")
        log.info("监控已停止")


def main():
    """主入口"""
    import argparse
    
    parser = argparse.ArgumentParser(description="A股智能量化监控系统")
    parser.add_argument("--config", default="config/settings.yaml", help="配置文件路径")
    parser.add_argument("--once", action="store_true", help="只执行一次扫描")
    parser.add_argument("--interval", type=int, default=5, help="监控间隔(分钟)")
    args = parser.parse_args()

    monitor = StockMonitor(args.config)

    if args.once:
        monitor.run_once()
    else:
        monitor.run_loop(args.interval)


if __name__ == "__main__":
    main()
