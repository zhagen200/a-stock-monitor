#!/usr/bin/env python3
"""
A股智能量化监控系统 v3
AI多模型协作 + 策略自进化 + 回测数据存储

日度节奏:
  08:50-09:15  每日推荐（智能选股，AI推理，推送到钉钉/微信）
  09:15-11:30  上午盘实时监控（60秒/次，AI信号分析，买卖推送）
  11:30-13:00  午间休市休眠
  13:00-15:00  下午盘实时监控（60秒/次，AI信号分析，买卖推送）
  15:00-15:15  收盘汇总（AI总结+资金流向+后续关注点推送）
  15:15-次日   休眠至下一个交易日（周日执行策略进化）
"""

import sys
import time
import yaml
import signal
import os
import logging
import json
from pathlib import Path
from datetime import datetime, date, time as dtime, timedelta

os.environ['NO_PROXY'] = '*'
os.environ['no_proxy'] = '*'
os.environ['HTTP_PROXY'] = ''
os.environ['HTTPS_PROXY'] = ''
os.environ['ALL_PROXY'] = ''

from rich.console import Console
from rich.table import Table

sys.path.insert(0, str(Path(__file__).parent))

from src.data.collector import StockDataCollector
from src.data.news import NewsCollector
from src.analysis.technical import TechnicalAnalyzer
from src.analysis.signal_engine import SignalEngine
from src.llm.client import LLMClient
from src.llm.depot import LLMDepot
from src.llm.analyzer import AIAnalysisEngine
from src.llm.evolver import BacktestDB, StrategyEvolver
from src.notify.notifier import Notifier
from src.scanner.smart_picker import SmartStockPicker

console = Console()

LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

def setup_logger():
    logger = logging.getLogger("stock_monitor")
    logger.setLevel(logging.INFO)
    fh = logging.FileHandler(LOG_DIR / "monitor.log", encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s %(message)s", datefmt="%H:%M:%S"))
    if not logger.handlers:
        logger.addHandler(fh)
    return logger

log = setup_logger()
POOL_FILE = LOG_DIR / "watchlist_pool.json"


class StockMonitor:
    """A股监控系统 v3 — AI多模型协作"""

    def __init__(self, config_path: str = "config/settings.yaml"):
        self.config = self._load_config(config_path)

        # 数据层
        self.collector = StockDataCollector()
        self.news_collector = NewsCollector()
        self.technical = TechnicalAnalyzer()
        self.signal_engine = SignalEngine(self.config)
        self.notifier = Notifier(self.config)
        self.picker = SmartStockPicker(self.config)

        # AI层 — 多模型调度
        self.llm_depot = LLMDepot(self.config)
        self.ai_engine = AIAnalysisEngine(self.llm_depot, self.config)
        self.backtest_db = BacktestDB()
        self.evolver = StrategyEvolver(self.llm_depot, self.backtest_db)

        # 向后兼容：旧单模型LLM
        llm_config = self.config.get("llm", {})
        if llm_config.get("enabled", True):
            # 解析 ${ENV_VAR} 占位符
            import re as _re, os as _os
            def _resolve(v):
                return _re.sub(r'\$\{(\w+)\}', lambda m: _os.environ.get(m.group(1)) or m.group(0), v)
            self.llm = LLMClient(
                api_base=_resolve(llm_config.get("api_base", "http://localhost:11434/v1")),
                model=_resolve(llm_config.get("model", "qwen2.5")),
                api_key=_resolve(llm_config.get("api_key", "not-needed")),
            )
        else:
            self.llm = None

        # AI分析配置
        ai_cfg = self.config.get("ai_analysis", {})
        self.ai_enabled = ai_cfg.get("enabled", False)
        self.ai_signal = ai_cfg.get("signal_analysis", False)
        self.ai_news = ai_cfg.get("news_analysis", False)
        self.ai_report = ai_cfg.get("stock_report", False)
        self.ai_evolution = ai_cfg.get("strategy_evolution", False)
        self.evolution_interval = ai_cfg.get("evolution_interval_days", 7)

        # 持仓与监控池
        self.watchlist = self.config.get("watchlist", {})
        self.holding_codes = set()
        for s in self.watchlist.get("stocks", []):
            if s.get("cost") and s.get("shares"):
                self.holding_codes.add(s["code"])

        self.llm_stocks = {"002195", "002640", "600580"}
        self.dynamic_pool = self._load_dynamic_pool()
        self.running = False

        # 日度标记
        self._today = None
        self._recommend_done = False
        self._closing_done = False
        self._evolution_done = False
        self._today_signals = []

    def _load_config(self, path: str) -> dict:
        try:
            with open(path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except FileNotFoundError:
            return {}

    def _load_dynamic_pool(self) -> dict:
        try:
            if POOL_FILE.exists():
                with open(POOL_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            pass
        return {}

    def _save_dynamic_pool(self):
        with open(POOL_FILE, "w", encoding="utf-8") as f:
            json.dump(self.dynamic_pool, f, ensure_ascii=False, indent=2)

    def _reset_daily_flags(self):
        today = date.today().isoformat()
        if self._today != today:
            self._today = today
            self._recommend_done = False
            self._closing_done = False
            self._evolution_done = False
            self._today_signals = []
            log.info(f"=== 新交易日 {today} ===")

    def _get_phase(self) -> str:
        now = datetime.now()
        if now.weekday() >= 5:
            return 'holiday'
        t = now.time()
        if t < dtime(8, 50):
            return 'closed'
        elif t < dtime(9, 15):
            return 'pre_market'
        elif t < dtime(11, 30):
            return 'morning'
        elif t < dtime(13, 0):
            return 'noon_break'
        elif t < dtime(15, 0):
            return 'afternoon'
        elif t < dtime(15, 15):
            return 'closing'
        else:
            return 'closed'

    def _sleep_until(self, target_h: int, target_m: int, label: str = ""):
        now = datetime.now()
        target = now.replace(hour=target_h, minute=target_m, second=0, microsecond=0)
        delta = (target - now).total_seconds()
        if delta <= 0:
            return
        if label:
            console.print(f"[dim]💤 {label}，休眠 {int(delta)//60} 分钟...[/dim]")
            log.info(f"{label}，休眠 {int(delta)//60} 分钟")
        for _ in range(int(delta)):
            if not self.running:
                break
            time.sleep(1)

    # ── 每日任务 ──────────────────────────────────────

    def daily_recommend(self):
        """每日智能推荐 + AI推理"""
        if self._recommend_done:
            return
        self._recommend_done = True

        console.print("\n[bold cyan]🔍 每日智能选股扫描...[/bold cyan]")
        log.info("每日智能选股扫描...")

        candidates = self.picker.scan_short_term_opportunities(max_count=10)
        self._cleanup_dynamic_pool()

        new_added = []
        today = date.today().isoformat()
        for stock in candidates:
            code = stock['code']
            if code in self.holding_codes:
                continue
            if code not in self.dynamic_pool:
                self.dynamic_pool[code] = {
                    'name': stock['name'], 'added_date': today,
                    'source': 'auto_pick', 'price_at_add': stock['price'],
                    'change_pct_at_add': stock['change_pct'],
                    'main_net_inflow': stock['main_net_inflow'],
                }
                new_added.append(stock)
        self._save_dynamic_pool()

        if new_added:
            # AI 推理推荐理由
            ai_reasons = []
            if self.ai_enabled and self.ai_signal:
                for s in new_added[:3]:  # 前3只做AI分析
                    try:
                        quote = self.collector.get_realtime_quote(s['code'])
                        analysis = self.ai_engine.analyze_signal(
                            signal_data={'code': s['code'], 'name': s['name'],
                                         'price': s['price'], 'score': s.get('score', 0),
                                         'action': 'buy', 'confidence': 50,
                                         'stop_loss': s['price']*0.95,
                                         'take_profit_1': s['price']*1.05,
                                         'take_profit_2': s['price']*1.10},
                            tech_data={}, fund_flow={'main_net_inflow': s['main_net_inflow']},
                            news_list=[], market_indices=self.collector.get_market_index() or {},
                        )
                        ai_reasons.append(f"• {s['name']}: {analysis.ai_reasoning[:100]}")
                    except Exception as e:
                        log.error(f"AI推荐分析失败 {s['code']}: {e}")

            msg_lines = [f"📊 今日推荐 {len(new_added)} 只短线机会\n"]
            for s in new_added:
                msg_lines.append(f"• {s['code']} {s['name']} ¥{s['price']:.2f} {s['change_pct']:+.2f}% 主力净流入{s['main_net_inflow']/1e4:.0f}万")
            if ai_reasons:
                msg_lines.append("\n🤖 AI分析:")
                msg_lines.extend(ai_reasons)

            self.notifier.send(f"📊 今日推荐 {len(new_added)} 只短线机会", "\n".join(msg_lines))
            log.info(f"新增 {len(new_added)} 只推荐股票")
        else:
            log.info("今日无合适推荐")

    def _cleanup_dynamic_pool(self):
        today = date.today()
        to_remove = []
        for code, info in self.dynamic_pool.items():
            if code in self.holding_codes:
                continue
            added_date = datetime.strptime(info['added_date'], '%Y-%m-%d').date()
            if (today - added_date).days >= 3:
                to_remove.append(code)
        for code in to_remove:
            log.info(f"移除过期: {code} {self.dynamic_pool[code]['name']}")
            del self.dynamic_pool[code]
        if to_remove:
            self._save_dynamic_pool()

    # ── 扫描 + AI分析 + 回测存储 ─────────────────────

    def scan_stock(self, stock_code: str, stock_name: str) -> dict:
        console.print(f"[cyan]扫描 {stock_name}({stock_code})...[/cyan]")
        log.info(f"扫描 {stock_name}({stock_code})...")

        quote = self.collector.get_realtime_quote(stock_code)
        if not quote:
            return None
        price = quote["price"]

        kline = self.collector.get_kline(stock_code, days=250)
        if kline.empty:
            return None

        tech_result = self.technical.analyze(kline, price)
        fund_flow = self.collector.get_fund_flow(stock_code)

        # 旧LLM新闻分析（向后兼容）
        news_score = 0.0
        news_list = []
        if self.llm and self.llm.enabled and stock_code in self.llm_stocks:
            news_list = self.news_collector.get_stock_news(stock_code, limit=5)
            if news_list:
                all_titles = "\n".join([f"- {n.get('title', '')}" for n in news_list])
                analysis = self.llm.analyze_news(all_titles, stock_code)
                news_score = analysis.get("score", 0)

        signal = self.signal_engine.generate_signal(
            code=stock_code, name=stock_name, price=price,
            technical_result=tech_result, fund_flow=fund_flow,
            news_sentiment=news_score,
        )

        result = {"quote": quote, "signal": signal, "tech_result": tech_result,
                  "fund_flow": fund_flow, "news_list": news_list}

        # ── AI 深度分析（v3新增）──
        ai_analysis = None
        if self.ai_enabled and self.ai_signal:
            try:
                sig_data = {
                    'code': stock_code, 'name': stock_name, 'price': price,
                    'score': signal.score, 'action': signal.action,
                    'confidence': signal.confidence,
                    'stop_loss': signal.stop_loss,
                    'take_profit_1': signal.take_profit_1,
                    'take_profit_2': signal.take_profit_2,
                }
                indices = self.collector.get_market_index() or {}
                ai_analysis = self.ai_engine.analyze_signal(
                    sig_data, {'total_score': tech_result.total_score, 'trend_score': tech_result.trend_score, 'momentum_score': tech_result.momentum_score, 'volume_score': tech_result.volume_score, 'pattern_score': tech_result.pattern_score, 'signals': [{'name': s.name, 'signal': s.signal, 'description': s.description} for s in tech_result.signals]},
                    fund_flow or {}, news_list, indices,
                )
                result['ai_analysis'] = ai_analysis
            except Exception as e:
                log.error(f"AI信号分析失败 {stock_code}: {e}")

        # ── 存入回测库（v3新增）──
        try:
            self.backtest_db.save_signal(
                signal_data={
                    'code': stock_code, 'name': stock_name,
                    'action': signal.action, 'score': signal.score, 'price': price,
                },
                ai_analysis=ai_analysis.ai_reasoning if ai_analysis else "",
                ai_confidence=ai_analysis.confidence_adjustment if ai_analysis else 0,
            )
        except Exception as e:
            log.error(f"回测存储失败 {stock_code}: {e}")

        return result

    def scan_fund(self, fund_code: str, fund_name: str) -> dict:
        fund_data = self.collector.get_fund_nav(fund_code)
        if not fund_data:
            return None
        kline = self.collector.get_kline(fund_code, days=250)
        if not kline.empty:
            tech_result = self.technical.analyze(kline, fund_data.get("price", 0))
            signal = self.signal_engine.generate_signal(
                code=fund_code, name=fund_name, price=fund_data.get("price", 0),
                technical_result=tech_result,
            )
            return {"data": fund_data, "signal": signal}
        return {"data": fund_data, "signal": None}

    def scan_all(self) -> list:
        results = []
        now = datetime.now().strftime("%H:%M:%S")

        console.print(f"\n{'='*60}")
        console.print(f"[bold]🔍 开始扫描 [{now}][/bold]")
        console.print(f"{'='*60}")
        log.info(f"开始扫描 [{now}]")

        indices = self.collector.get_market_index()
        if indices:
            for name, data in indices.items():
                log.info(f"  {name}: {data['price']:.2f} {data['change_pct']:+.2f}%")

        all_stocks = self._get_all_watch_codes()
        for stock in all_stocks:
            result = self.scan_stock(stock["code"], stock["name"])
            if result:
                results.append(result)
                self._today_signals.append(result)
                action = result["signal"].action
                if action in ("strong_buy", "strong_sell", "buy", "sell"):
                    self.notifier.send_signal(result["signal"])

        for fund in self.watchlist.get("funds", []):
            result = self.scan_fund(fund["code"], fund["name"])
            if result:
                results.append(result)

        self._display_results(results)
        self._log_results(results)
        return results

    def _get_all_watch_codes(self) -> list:
        codes = []
        seen = set()
        for stock in self.watchlist.get("stocks", []):
            codes.append(stock)
            seen.add(stock["code"])
        for code, info in self.dynamic_pool.items():
            if code not in seen:
                codes.append({"code": code, "name": info.get("name", code), "source": "auto"})
        return codes

    # ── 收盘汇总 + 收益回填 ──────────────────────────

    def closing_summary(self):
        """收盘汇总：行情+资金流向+AI总结+后续关注"""
        if self._closing_done:
            return
        self._closing_done = True

        console.print("\n[bold cyan]📊 生成收盘汇总...[/bold cyan]")
        log.info("生成收盘汇总...")

        # 1. 回填历史信号收益
        self._backfill_returns()

        # 2. 大盘指数
        indices = self.collector.get_market_index()
        idx_lines = []
        if indices:
            for name, data in indices.items():
                idx_lines.append(f"{name}: {data['price']:.2f} {data['change_pct']:+.2f}%")

        # 3. 当日信号汇总
        sig_summary = {}
        action_map = {"strong_buy": "🔴强买", "buy": "🟠买入", "hold": "⚪观望",
                      "sell": "🟢卖出", "strong_sell": "🔵强卖"}
        for r in self._today_signals:
            sig = r.get("signal")
            if sig:
                sig_summary[sig.code] = r

        sig_lines = []
        for code, r in sig_summary.items():
            sig = r["signal"]
            act = action_map.get(sig.action, sig.action)
            sig_lines.append(f"{sig.name}({code}): ¥{sig.price:.2f} {act} 评分{sig.score:.0f}")
            if sig.reasons:
                sig_lines.append(f"  → {'; '.join(sig.reasons[:3])}")
            # AI分析摘要
            ai = r.get("ai_analysis")
            if ai:
                sig_lines.append(f"  🤖 AI: {ai.ai_reasoning[:80]}...")

        # 4. 资金流向
        flow_report = self.picker.generate_daily_report()

        # 5. 后续关注
        watch_points = []
        for code, r in sig_summary.items():
            sig = r["signal"]
            if sig.action in ("buy", "strong_buy"):
                watch_points.append(f"🔴 {sig.name}({code}) 买入信号，止损¥{sig.stop_loss:.2f}")
            elif sig.action in ("sell", "strong_sell"):
                watch_points.append(f"🟢 {sig.name}({code}) 卖出信号")
            elif abs(sig.score) > 20:
                watch_points.append(f"👀 {sig.name}({code}) 评分{sig.score:.0f}，接近信号区间")

        # 6. 回测统计
        stats = self.backtest_db.get_signal_stats(days=7)
        stats_lines = []
        for action, s in stats.items():
            stats_lines.append(f"  {action}: {s['total']}次, 1日准确率{s['accuracy_1d']:.0f}%, 平均收益{s['avg_return_1d']:+.2f}%")

        report = f"""📊 A股收盘汇总 - {date.today().isoformat()}
{'='*50}

📈 大盘指数
{chr(10).join(idx_lines) if idx_lines else '无数据'}

📊 持仓/关注股信号
{'─'*40}
{chr(10).join(sig_lines) if sig_lines else '无信号数据'}

{flow_report}

📉 本周信号回测
{'─'*40}
{chr(10).join(stats_lines) if stats_lines else '数据不足'}

🔮 后续关注
{'─'*40}
{chr(10).join(watch_points) if watch_points else '暂无明确关注点'}

🤖 LLM使用统计
{self.llm_depot.get_usage_report()}

{'='*50}"""

        self.notifier.send(f"📊 A股收盘汇总 {date.today().isoformat()}", report)
        console.print("[green]✅ 收盘汇总已推送[/green]")
        log.info("收盘汇总已推送")

    def _backfill_returns(self):
        """回填历史信号的实际收益"""
        pending = self.backtest_db.get_pending_signals(days=10)
        if not pending:
            return

        filled = 0
        for sig in pending:
            try:
                kline = self.collector.get_kline(sig['code'], days=20)
                if kline.empty:
                    continue

                # 找到信号日期的K线
                sig_date = datetime.fromisoformat(sig['timestamp']).date()
                close_prices = kline['close']

                # 找信号日之后的价格
                future = close_prices[close_prices.index.date > sig_date]
                if len(future) < 1:
                    continue

                entry_price = sig['price']
                returns = {}
                for days, key in [(1, 'return_1d'), (3, 'return_3d'), (5, 'return_5d'), (10, 'return_10d')]:
                    if len(future) >= days:
                        returns[key] = (future.iloc[days-1] / entry_price - 1) * 100

                if returns:
                    # 最大回撤
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

    # ── 策略进化 ──────────────────────────────────────

    def run_evolution(self):
        """执行策略进化评估"""
        if self._evolution_done:
            return
        self._evolution_done = True

        console.print("\n[bold cyan]🧬 策略进化评估...[/bold cyan]")
        log.info("策略进化评估...")

        current_params = self.config.get("signal", {}).get("weights", {})
        current_params.update(self.config.get("signal", {}).get("thresholds", {}))

        new_params = self.evolver.evaluate_and_evolve(current_params)
        if new_params:
            # 更新配置
            if 'weights' in self.config.get('signal', {}):
                for k in ['technical', 'capital_flow', 'news_sentiment', 'fundamental']:
                    if k in new_params:
                        self.config['signal']['weights'][k] = new_params[k]
            if 'thresholds' in self.config.get('signal', {}):
                for k in ['buy', 'sell', 'strong_buy', 'strong_sell']:
                    if k in new_params:
                        self.config['signal']['thresholds'][k] = new_params[k]

            # 通知
            self.notifier.send("🧬 策略进化", f"策略参数已自动优化\n原因: {new_params.get('reason', '')}")
            log.info(f"策略已进化: {new_params}")

    # ── 显示/日志 ─────────────────────────────────────

    def _display_results(self, results: list):
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
            color = "red" if change_pct > 0 else "green"
            table.add_row(
                f"{sig.name}", f"¥{sig.price:.2f}",
                f"[{color}]{change_pct:+.2f}%[/{color}]",
                action_styles.get(sig.action, sig.action),
                f"{sig.score:.0f}",
                f"{'█' * int(sig.confidence/10)}{'░' * (10-int(sig.confidence/10))} {sig.confidence:.0f}%",
                f"¥{sig.stop_loss:.2f}", f"¥{sig.take_profit_1:.2f} / ¥{sig.take_profit_2:.2f}",
            )
        console.print(table)

    def _log_results(self, results: list):
        action_map = {"strong_buy": "🔴强买", "buy": "🟠买入", "hold": "⚪观望",
                      "sell": "🟢卖出", "strong_sell": "🔵强卖"}
        log.info(f"{'─'*60}")
        for r in results:
            sig = r.get("signal")
            if not sig:
                continue
            quote = r.get("quote") or r.get("data", {})
            chg = quote.get("change_pct", 0)
            log.info(f"{sig.name:<10} ¥{sig.price:>7.2f} {chg:>+7.2f}% "
                     f"{action_map.get(sig.action, sig.action):<8} "
                     f"{sig.score:>5.0f}  {sig.confidence:>5.0f}%")
            ai = r.get("ai_analysis")
            if ai:
                log.info(f"  🤖 {ai.ai_reasoning[:100]}")
        log.info(f"{'─'*60}")

    # ── 主循环 ────────────────────────────────────────

    def run_loop(self, interval_seconds: int = 60):
        self.running = True

        def stop_handler(sig, frame):
            console.print("\n[yellow]正在停止监控...[/yellow]")
            self.running = False

        signal.signal(signal.SIGINT, stop_handler)
        signal.signal(signal.SIGTERM, stop_handler)

        ai_status = "✅ 多模型" if self.ai_enabled and len(self.llm_depot.models) > 1 else "✅ 单模型" if self.ai_enabled else "❌"
        console.print("[bold green]🚀 A股监控系统 v3 启动[/bold green]")
        console.print(f"   扫描间隔: {interval_seconds}秒")
        console.print(f"   持仓: {len(self.holding_codes)}只")
        console.print(f"   AI分析: {ai_status}")
        console.print(f"   策略进化: {'✅' if self.ai_evolution else '❌'}")
        console.print(f"   推送: 钉钉 ✅ | Server酱 ✅\n")

        log.info(f"🚀 v3启动 | 间隔:{interval_seconds}秒 | AI:{ai_status} | 持仓:{len(self.holding_codes)}只")

        # 启动时立即回填历史信号收益（昨天及更早的数据）
        try:
            self._backfill_returns()
        except Exception as e:
            log.warning(f"启动回填收益失败: {e}")

        while self.running:
            try:
                self._reset_daily_flags()
                phase = self._get_phase()

                if phase in ('holiday', 'closed'):
                    if not self._closing_done and phase == 'closed':
                        self.closing_summary()

                    # 周日执行策略进化
                    if self.ai_evolution and datetime.now().weekday() == 6 and not self._evolution_done:
                        self.run_evolution()

                    label = "非交易日" if phase == 'holiday' else "收盘"
                    console.print(f"[dim]🌙 {label}，休眠...[/dim]")
                    log.info(f"{label}，休眠至明日")

                    tomorrow = datetime.now() + timedelta(days=1)
                    target = tomorrow.replace(hour=8, minute=50, second=0, microsecond=0)
                    sleep_seconds = max(60, int((target - datetime.now()).total_seconds()))
                    for _ in range(sleep_seconds):
                        if not self.running:
                            break
                        time.sleep(1)
                    continue

                if phase == 'pre_market':
                    self.daily_recommend()
                    self._sleep_until(9, 15, "等待开盘")
                    continue

                if phase in ('morning', 'afternoon'):
                    self.scan_all()
                    if self.running:
                        next_t = datetime.now() + timedelta(seconds=interval_seconds)
                        console.print(f"\n[dim]⏰ 下次扫描: {next_t.strftime('%H:%M:%S')}[/dim]")
                        for _ in range(interval_seconds):
                            if not self.running:
                                break
                            time.sleep(1)

                elif phase == 'noon_break':
                    self._sleep_until(13, 0, "午间休市")

                elif phase == 'closing':
                    self.closing_summary()

            except KeyboardInterrupt:
                break
            except Exception as e:
                console.print(f"[red]扫描出错: {e}[/red]")
                log.error(f"扫描出错: {e}")
                time.sleep(30)

        console.print("[yellow]监控已停止[/yellow]")
        log.info("监控已停止")
        self.backtest_db.close()


def main():
    import argparse
    parser = argparse.ArgumentParser(description="A股智能量化监控系统 v3")
    parser.add_argument("--config", default="config/settings.yaml")
    parser.add_argument("--once", action="store_true", help="只执行一次扫描")
    parser.add_argument("--interval", type=int, default=60, help="扫描间隔(秒)")
    parser.add_argument("--recommend", action="store_true", help="执行每日推荐")
    parser.add_argument("--report", action="store_true", help="生成资金流向报表")
    parser.add_argument("--summary", action="store_true", help="生成收盘汇总")
    parser.add_argument("--evolve", action="store_true", help="执行策略进化")
    parser.add_argument("--stats", action="store_true", help="查看回测统计")
    args = parser.parse_args()

    monitor = StockMonitor(args.config)

    if args.recommend:
        monitor.daily_recommend()
    elif args.report:
        report = monitor.picker.generate_daily_report()
        print(report)
        monitor.notifier.send("📊 每日资金流向报表", report)
    elif args.summary:
        monitor.closing_summary()
    elif args.evolve:
        monitor.run_evolution()
    elif args.stats:
        stats = monitor.backtest_db.get_signal_stats(days=30)
        print(json.dumps(stats, ensure_ascii=False, indent=2))
        print(f"\n{monitor.llm_depot.get_usage_report()}")
    elif args.once:
        monitor.scan_all()
    else:
        monitor.run_loop(args.interval)


if __name__ == "__main__":
    main()
