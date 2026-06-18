import signal
import time
import logging
import pandas as pd
from pathlib import Path
from datetime import datetime, date, time as dtime, timedelta
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
from src.llm.depot import LLMDepot
from src.llm.analyzer import AIAnalysisEngine
from src.llm.evolver import BacktestDB
from src.data.news import NewsCollector
from src.scanner.smart_picker import SmartStockPicker

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
        self._closing_done = False
        self._recommend_done = False
        self._today = ""
        self._today_signals: list = []

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
        self.picker = SmartStockPicker(settings.data)
        broker_type = settings.get("broker.type", "mock")
        if broker_type == "xtquant":
            from src.execution.broker import XtQuantBroker
            self.broker = XtQuantBroker(
                account_id=settings.get("broker.account_id", ""),
                password=settings.get("broker.password", ""),
            )
            if self.broker.connect():
                console.print("[bold green]✅ QMT券商连接成功[/bold green]")
            else:
                console.print("[yellow]⚠️ QMT未连接,使用模拟券商[/yellow]")
                self.broker = MockBroker()
        else:
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

        # AI 多模型分析 + 回测数据库
        self.llm_depot = LLMDepot(settings.data)
        ai_cfg = settings.get("ai_analysis", {})
        self._ai_enabled = ai_cfg.get("enabled", False)
        self._ai_signal = ai_cfg.get("signal_analysis", False)
        self.ai_engine = AIAnalysisEngine(self.llm_depot, settings.data) if self._ai_enabled else None
        self.backtest_db = BacktestDB()

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

        # AI 深度分析
        ai_analysis = None
        if self._ai_enabled and self._ai_signal and self.ai_engine:
            try:
                sig_data = {
                    'code': code, 'name': name, 'price': price,
                    'score': signal.score, 'action': signal.action,
                    'confidence': signal.confidence,
                    'stop_loss': signal.stop_loss,
                    'take_profit_1': signal.take_profit_1,
                    'take_profit_2': signal.take_profit_2,
                }
                indices = self.data_manager.get_market_index() or {}
                tech_data = {
                    'total_score': getattr(signal, 'technical_score', 0),
                    'signals': [{'name': r, 'signal': '', 'description': r} for r in signal.reasons[:5]],
                }
                ai_analysis = self.ai_engine.analyze_signal(
                    sig_data, tech_data, fund_flow or {}, [], indices,
                )
            except Exception as e:
                log.error(f"AI信号分析失败 {code}: {e}")

        # 存入回测数据库
        try:
            self.backtest_db.save_signal(
                signal_data={
                    'code': code, 'name': name,
                    'action': signal.action, 'score': signal.score, 'price': price,
                },
                ai_analysis=ai_analysis.ai_reasoning if ai_analysis else "",
                ai_confidence=ai_analysis.confidence_adjustment if ai_analysis else 0,
            )
        except Exception as e:
            log.error(f"回测存储失败 {code}: {e}")

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

    # ── 时间段判断 + 收盘汇总 ──────────────────────────

    def _backfill_returns(self):
        """回填历史信号的实际收益"""
        from src.data.collector import StockDataCollector
        collector = StockDataCollector()
        pending = self.backtest_db.get_pending_signals(days=10)
        if not pending:
            return
        filled = 0
        for sig in pending:
            try:
                kline = collector.get_kline(sig['code'], days=20)
                if kline.empty:
                    continue
                sig_date = datetime.fromisoformat(sig['timestamp']).date()
                close_prices = kline['close']
                future = close_prices[close_prices.index.date > sig_date]
                if len(future) < 1:
                    continue
                entry_price = sig['price']
                returns = {}
                for days, key in [(1, 'return_1d'), (3, 'return_3d'), (5, 'return_5d'), (10, 'return_10d')]:
                    if len(future) >= days:
                        returns[key] = (future.iloc[days-1] / entry_price - 1) * 100
                if returns:
                    if len(future) >= 2:
                        peak = entry_price
                        max_dd = 0
                        for p in future.iloc[:10]:
                            peak = max(peak, p)
                            dd = (peak - p) / peak * 100
                            max_dd = max(max_dd, dd)
                        returns['max_drawdown'] = max_dd
                    self.backtest_db.update_actual_returns(sig['id'], returns)
                    filled += 1
            except Exception as e:
                log.error(f"回填收益失败 {sig['code']}: {e}")
        if filled > 0:
            log.info(f"回填了 {filled} 条信号的实际收益")

    def daily_recommend(self):
        """每日智能推荐 + AI推理"""
        if self._recommend_done:
            return
        self._recommend_done = True

        console.print("\n[bold cyan]🔍 每日智能选股扫描...[/bold cyan]")
        log.info("每日智能选股扫描...")

        candidates = self.picker.scan_short_term_opportunities(max_count=10)

        if candidates:
            msg_lines = [f"📊 今日推荐 {len(candidates)} 只短线机会\n"]
            for s in candidates:
                msg_lines.append(
                    f"• {s['code']} {s['name']} ¥{s['price']:.2f} "
                    f"{s['change_pct']:+.2f}% 主力净流入{s['main_net_inflow']/1e4:.0f}万"
                )

            # AI 推理推荐理由
            ai_reasons = []
            if self._ai_enabled and self.ai_engine:
                for s in candidates[:3]:
                    try:
                        analysis = self.ai_engine.analyze_signal(
                            signal_data={'code': s['code'], 'name': s['name'],
                                         'price': s['price'], 'score': s.get('score', 0),
                                         'action': 'buy', 'confidence': 50,
                                         'stop_loss': s['price']*0.95,
                                         'take_profit_1': s['price']*1.05,
                                         'take_profit_2': s['price']*1.10},
                            tech_data={}, fund_flow={'main_net_inflow': s['main_net_inflow']},
                            news_list=[], market_indices=self.data_manager.get_market_index() or {},
                        )
                        ai_reasons.append(f"• {s['name']}: {analysis.ai_reasoning[:100]}")
                    except Exception as e:
                        log.error(f"AI推荐分析失败 {s['code']}: {e}")

            if ai_reasons:
                msg_lines.append("\n🤖 AI分析:")
                msg_lines.extend(ai_reasons)

            self.notifier.send(f"📊 今日推荐 {len(candidates)} 只短线机会", "\n".join(msg_lines))
            log.info(f"推荐 {len(candidates)} 只股票")
        else:
            log.info("今日无合适推荐")

    def _reset_daily_flags(self):
        today = date.today().isoformat()
        if self._today != today:
            self._today = today
            self._closing_done = False
            self._recommend_done = False
            self._today_signals = []
            log.info(f"=== 新交易日 {today} ===")

    def _get_phase(self) -> str:
        now = datetime.now()
        if now.weekday() >= 5:
            return "holiday"
        t = now.time()
        if t < dtime(8, 50):
            return "closed"
        elif t < dtime(9, 15):
            return "pre_market"
        elif t < dtime(11, 30):
            return "morning"
        elif t < dtime(13, 0):
            return "noon_break"
        elif t < dtime(15, 0):
            return "afternoon"
        elif t < dtime(15, 15):
            return "closing"
        else:
            return "closed"

    def _sleep_until(self, hour: int, minute: int, label: str):
        target = datetime.now().replace(hour=hour, minute=minute, second=0, microsecond=0)
        wait = (target - datetime.now()).total_seconds()
        if wait > 0:
            console.print(f"[dim]💤 {label}，等待至 {hour:02d}:{minute:02d}[/dim]")
            log.info(f"{label}，等待至 {hour:02d}:{minute:02d}")
            for _ in range(int(wait)):
                if not self.running:
                    break
                time.sleep(1)

    def closing_summary(self):
        """收盘汇总：大盘指数 + 个股表现 + 后续关注点"""
        if self._closing_done:
            return
        self._closing_done = True

        console.print("\n[bold cyan]📊 生成收盘汇总...[/bold cyan]")
        log.info("生成收盘汇总...")

        # 回填历史信号收益
        self._backfill_returns()

        # 1. 大盘指数
        indices = self.data_manager.get_market_index()
        idx_lines = []
        if indices:
            for name, data in indices.items():
                idx_lines.append(
                    f"  {name}: {data['price']:.2f} {data['change_pct']:+.2f}%"
                )

        # 2. 当日信号汇总（去重取最新）
        action_map = {
            "strong_buy": "🔴强买", "buy": "🟠买入", "hold": "⚪观望",
            "sell": "🟢卖出", "strong_sell": "🔵强卖",
        }
        latest_signals = {}
        for sig in self._today_signals:
            latest_signals[sig.code] = sig

        sig_lines = []
        watch_points = []
        for code, sig in latest_signals.items():
            act = action_map.get(sig.action, sig.action)
            sig_lines.append(
                f"  {sig.name}({code}): ¥{sig.price:.2f} {act} 评分{sig.score:.0f}"
            )
            if sig.reasons:
                sig_lines.append(f"    → {'; '.join(sig.reasons[:3])}")
            if sig.action in ("buy", "strong_buy"):
                watch_points.append(
                    f"  🔴 {sig.name}({code}) 买入信号，止损¥{sig.stop_loss:.2f}"
                )
            elif sig.action in ("sell", "strong_sell"):
                watch_points.append(f"  🟢 {sig.name}({code}) 卖出信号")
            elif abs(sig.score) > 20:
                watch_points.append(
                    f"  👀 {sig.name}({code}) 评分{sig.score:.0f}，接近信号区间"
                )

        # 3. 持仓盈亏
        positions = self.position_manager.get_all()
        pos_lines = []
        if positions:
            for code, pos in positions.items():
                cost = pos.get("cost", 0)
                shares = pos.get("shares", 0)
                if cost > 0 and shares > 0:
                    quote = self.data_manager.get_realtime_quote(code)
                    cur = quote.get("price", 0)
                    if cur > 0:
                        pnl = (cur - cost) / cost * 100
                        pos_lines.append(
                            f"  {pos.get('name', code)}: 成本¥{cost:.2f} "
                            f"现价¥{cur:.2f} 盈亏{pnl:+.2f}%"
                        )

        # 4. 回测统计
        stats = self.backtest_db.get_signal_stats(days=7)
        stats_lines = []
        for action, s in stats.items():
            stats_lines.append(
                f"  {action}: {s['total']}次, 1日准确率{s['accuracy_1d']:.0f}%, "
                f"平均收益{s['avg_return_1d']:+.2f}%"
            )

        report = f"""📊 A股收盘汇总 - {date.today().isoformat()}
{'='*50}

📈 大盘指数
{chr(10).join(idx_lines) if idx_lines else '  无数据'}

📊 持仓/关注股信号
{'─'*40}
{chr(10).join(sig_lines) if sig_lines else '  无信号数据'}

💰 持仓盈亏
{'─'*40}
{chr(10).join(pos_lines) if pos_lines else '  无持仓'}

📉 本周信号回测
{'─'*40}
{chr(10).join(stats_lines) if stats_lines else '  数据不足'}

🔮 后续关注
{'─'*40}
{chr(10).join(watch_points) if watch_points else '  暂无明确关注点'}

🤖 LLM使用统计
{self.llm_depot.get_usage_report()}

{'='*50}"""

        self.notifier.send(f"📊 A股收盘汇总 {date.today().isoformat()}", report)
        console.print("[green]✅ 收盘汇总已推送[/green]")
        log.info("收盘汇总已推送")

    def scan_all(self) -> list:
        results = []
        self._reset_daily_flags()
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
                    self._today_signals.append(signal)
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
        ai_status = "✅ 多模型" if self._ai_enabled and len(self.llm_depot.models) > 1 else "✅ 单模型" if self._ai_enabled else "❌"
        console.print(f"   AI分析: {ai_status}")
        console.print(f"   LLM: {'✅ 已启用' if self.llm else '❌ 未启用'}")
        console.print(f"   自动执行: {'✅' if self.signal_bus.auto_execute else '❌ 仅信号'}")
        console.print(f"   按 Ctrl+C 停止\n")

        log.info(f"🚀 启动 | AI:{ai_status} | 持仓:{len(watchlist)}只")

        # 启动时回填历史信号收益
        try:
            self._backfill_returns()
        except Exception as e:
            log.warning(f"启动回填收益失败: {e}")

        while self.running:
            try:
                phase = self._get_phase()

                if phase == "closed":
                    # 判断是否已过收盘时间但还没做收盘汇总
                    now = datetime.now()
                    if (dtime(15, 0) <= now.time() < dtime(15, 15)
                            and not self._closing_done):
                        self.closing_summary()
                    elif now.time() >= dtime(15, 15) and not self._closing_done:
                        self.closing_summary()

                    console.print("[dim]💤 收盘，休眠至明日[/dim]")
                    log.info("收盘，休眠至明日")
                    # 休眠到次日 8:50
                    tomorrow = (now + timedelta(days=1)).replace(
                        hour=8, minute=50, second=0, microsecond=0
                    )
                    wait = (tomorrow - now).total_seconds()
                    for _ in range(int(wait)):
                        if not self.running:
                            break
                        time.sleep(1)
                    continue

                if phase == "holiday":
                    console.print("[dim]💤 周末休市，休眠...[/dim]")
                    for _ in range(3600):
                        if not self.running:
                            break
                        time.sleep(1)
                    continue

                if phase == "noon_break":
                    self._sleep_until(13, 0, "午间休市")
                    continue

                if phase == "closing":
                    self.closing_summary()
                    # 收盘汇总后进入 closed，下次循环会休眠
                    continue

                # pre_market: 盘前推荐
                if phase == "pre_market":
                    self._reset_daily_flags()
                    self.daily_recommend()
                    self._sleep_until(9, 15, "等待开盘")
                    continue

                # morning / afternoon: 扫描
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

