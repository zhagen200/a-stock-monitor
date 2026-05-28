import signal
import time
import logging
import pandas as pd
from pathlib import Path
from datetime import datetime
from typing import Optional, List

from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from src.core.base import TradeSignal
from src.core.config import settings
from src.data.manager import DataManager
from src.strategy.technical import TechnicalStrategy
from src.strategy.capital_flow import CapitalFlowStrategy
from src.strategy.news_sentiment import NewsSentimentStrategy
from src.strategy.multi_timeframe import MultiTimeframeStrategy
from src.strategy.volume_pattern import VolumePatternStrategy
from src.strategy.trend_strength import TrendStrengthStrategy
from src.strategy.ensemble import EnsembleStrategy
from src.risk.manager import RiskManager
from src.risk.rules import (
    PositionLimitRule, MarketRegimeFilter,
    ConsecutiveLossRule, VolatilityRule,
)
from src.engine.signal_bus import SignalBus
from src.execution.broker import MockBroker
from src.execution.position import PositionManager
from src.notify.notifier import Notifier
from src.analytics.report import ReportGenerator
from src.llm.client import LLMClient
from src.data.news import NewsCollector

console = Console()

LOG_DIR = Path(__file__).parent.parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

log = logging.getLogger("live_engine")
log.setLevel(logging.INFO)
fh = logging.FileHandler(LOG_DIR / "monitor.log", encoding="utf-8")
fh.setFormatter(logging.Formatter("%(asctime)s %(message)s", datefmt="%H:%M:%S"))
log.addHandler(fh)


class LiveEngine:
    def __init__(self, auto_execute: bool = False):
        settings.load()

        self.data_manager = DataManager()
        self.news_collector = NewsCollector()
        self.position_manager = PositionManager()

        self.running = False
        self._weights = settings.get("signal.weights", {})
        self._llm_enabled = settings.get("llm.enabled", True)

        strategies = [
            TechnicalStrategy(),
            CapitalFlowStrategy(),
            MultiTimeframeStrategy(),
            VolumePatternStrategy(),
            TrendStrengthStrategy(),
        ]
        if self._llm_enabled:
            strategies.append(NewsSentimentStrategy())

        for s in strategies:
            w = self._weights.get(s.name, None)
            if w is not None:
                s.weight = w

        self.ensemble = EnsembleStrategy(strategies)

        self.risk_manager = RiskManager([
            PositionLimitRule(
                max_single_pct=settings.get("risk.max_position_pct", 20),
            ),
            MarketRegimeFilter(),
            ConsecutiveLossRule(
                max_losses=settings.get("risk.consecutive_loss_limit", 3),
            ),
            VolatilityRule(),
        ])

        self.notifier = Notifier(settings.data)
        self.broker = MockBroker()
        self.signal_bus = SignalBus(
            risk_manager=self.risk_manager,
            broker=self.broker,
            notifier=self.notifier,
            auto_execute=auto_execute,
        )

        llm_config = settings.get_llm_config()
        self.llm = None
        if llm_config.get("enabled", True):
            self.llm = LLMClient(
                api_base=llm_config.get("api_base", "http://localhost:11434/v1"),
                model=llm_config.get("model", "qwen2.5"),
                api_key=llm_config.get("api_key", "not-needed"),
            )

        self._llm_stocks = {
            s["code"] for s in settings.get_watchlist()
            if s.get("cost")
        }

    def scan_stock(self, stock: dict) -> Optional[TradeSignal]:
        code = stock["code"]
        name = stock.get("name", code)

        quote = None
        for _ in range(3):
            quote = self.data_manager.get_realtime_quote(code, force_refresh=True)
            if quote:
                break
            time.sleep(3)
        if not quote:
            return None
        price = quote.get("price", 0)
        change_pct = quote.get("change_pct", 0)

        kline = self.data_manager.get_kline(code, days=250)
        if kline.empty:
            return None

        fund_flow = self.data_manager.get_fund_flow(code)

        news_score = 0.0
        if self.llm and code in self._llm_stocks:
            news_list = self.data_manager.get_stock_news(code, limit=5)
            if news_list:
                all_titles = "\n".join([f"- {n.get('title', '')}" for n in news_list])
                analysis = self.llm.analyze_news(all_titles, code)
                news_score = analysis.get("score", 0)

        signal = self.ensemble.generate(code, name, price, {
            "kline_daily": kline,
            "fund_flow": fund_flow,
            "news_score": news_score,
        })

        signal.stop_loss = self._calc_stop_loss(kline, price)
        signal.take_profit_1 = self._calc_take_profit(kline, price, 1)
        signal.take_profit_2 = self._calc_take_profit(kline, price, 2)

        ctx = {"change_pct": change_pct}
        self.signal_bus.process(signal, ctx)

        self.position_manager.update_price(code, price)

        return signal

    def _calc_stop_loss(self, df, price: float) -> float:
        if df.empty or len(df) < 14:
            return round(price * 0.94, 2)
        atr = self._calc_atr(df)
        return round(max(price - 2 * atr, price * 0.94), 2)

    def _calc_take_profit(self, df, price: float, level: int) -> float:
        if df.empty or len(df) < 14:
            mult = 1.1 if level == 1 else 1.2
            return round(price * mult, 2)
        atr = self._calc_atr(df)
        if level == 1:
            return round(price + 3 * atr, 2)
        return round(price + 5 * atr, 2)

    def _calc_atr(self, df) -> float:
        high = df["high"]
        low = df["low"]
        close = df["close"].shift(1)
        tr = (high - low).abs()
        tr = pd.concat([high - low, (high - close).abs(), (low - close).abs()], axis=1).max(axis=1)
        return float(tr.rolling(14).mean().iloc[-1])

    def scan_all(self) -> list:
        results = []
        now = datetime.now().strftime("%H:%M:%S")
        console.print("\n" + "=" * 60)
        console.print(f"[bold]🔍 开始扫描 [{now}][/bold]")
        console.print("=" * 60)
        log.info(f"开始扫描 [{now}]")

        indices = self.data_manager.get_market_index()
        if indices:
            console.print("\n[bold]📊 大盘指数[/bold]")
            for name, data in indices.items():
                cc = "red" if data.get("change_pct", 0) > 0 else "green"
                console.print(
                    f"  {name}: {data.get('price', 0):.2f} "
                    f"[{cc}]{data.get('change_pct', 0):+.2f}%[/{cc}]"
                )

        watchlist = settings.get_watchlist()
        if indices:
            sh_index = indices.get("上证指数", {})
            sh_kline = self.data_manager.get_kline("000001", days=250)
            from src.strategy.technical import detect_market_regime
            regime = detect_market_regime(sh_kline) if not sh_kline.empty else "oscillate"
            for rule in self.risk_manager.rules:
                if hasattr(rule, "set_regime"):
                    rule.set_regime(regime)
            regime_colors = {"bull": "red", "oscillate": "yellow", "bear": "green"}
            rc = regime_colors.get(regime, "white")
            console.print(f"  市场状态: [{rc}]{regime}[/{rc}]")

        for stock in watchlist:
            try:
                signal = self.scan_stock(stock)
                if signal:
                    results.append(signal)
            except Exception as e:
                import traceback
                console.print(f"[red]扫描{stock.get('name')}失败: {e}[/red]")
                log.error(f"扫描{stock.get('name')}失败: {e}\n{traceback.format_exc()}")

        self._display_results(results)
        return results

    def _display_results(self, signals: list):
        table = Table(title="📊 信号汇总", show_lines=True)
        table.add_column("股票", style="cyan", width=12)
        table.add_column("现价", justify="right", width=8)
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

        for sig in signals:
            table.add_row(
                f"{sig.name}",
                f"¥{sig.price:.2f}",
                action_styles.get(sig.action, sig.action),
                f"{sig.score:.0f}",
                f"{'█' * int(sig.confidence/10)}{'░' * (10-int(sig.confidence/10))} {sig.confidence:.0f}%",
                f"¥{sig.stop_loss:.2f}",
                f"¥{sig.take_profit_1:.2f} / ¥{sig.take_profit_2:.2f}",
            )

        console.print(table)

        for sig in signals:
            if sig.action in ("strong_buy", "strong_sell"):
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

    def run_once(self):
        self.scan_all()

    def run_loop(self, interval_minutes: int = 5):
        self.running = True

        def stop_handler(sig, frame):
            console.print("\n[yellow]正在停止监控...[/yellow]")
            self.running = False

        signal.signal(signal.SIGINT, stop_handler)
        signal.signal(signal.SIGTERM, stop_handler)

        console.print("[bold green]🚀 A股量化交易系统启动[/bold green]")
        console.print(f"   监控间隔: {interval_minutes}分钟")
        watchlist = settings.get_watchlist()
        console.print(f"   自选股: {len(watchlist)}只")
        console.print(f"   LLM: {'✅ 已启用' if self.llm else '❌ 未启用'}")
        console.print(f"   自动执行: {'✅' if self.signal_bus.auto_execute else '❌ 仅信号'}")
        console.print(f"   按 Ctrl+C 停止\n")

        while self.running:
            try:
                self.scan_all()
                if self.running:
                    next_time = datetime.now().timestamp() + interval_minutes * 60
                    next_str = datetime.fromtimestamp(next_time).strftime("%H:%M:%S")
                    console.print(f"\n[dim]⏰ 下次扫描: {next_str}[/dim]")
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

