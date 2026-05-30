"""
策略自进化引擎
根据回测数据自动调整策略参数，实现系统自我优化
"""

import json
import sqlite3
import time
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict
from rich.console import Console

console = Console()

from src.data.store import DB_PATH, get_conn


@dataclass
class StrategyParams:
    """策略参数"""
    technical_weight: float = 0.40
    capital_weight: float = 0.20
    news_weight: float = 0.25
    fundamental_weight: float = 0.15
    buy_threshold: float = 30.0
    sell_threshold: float = -30.0
    strong_buy_threshold: float = 60.0
    strong_sell_threshold: float = -60.0
    # 进化历史
    version: int = 1
    updated_at: str = ""
    reason: str = ""


@dataclass
class EvolutionRecord:
    """进化记录"""
    id: int = 0
    timestamp: str = ""
    version: int = 0
    # 旧参数
    old_params: Dict = None
    new_params: Dict = None
    # 评估指标
    accuracy_before: float = 0
    accuracy_after: float = 0
    sharpe_before: float = 0
    sharpe_after: float = 0
    # AI分析
    ai_reasoning: str = ""
    key_changes: List[str] = None

    def __post_init__(self):
        if self.old_params is None:
            self.old_params = {}
        if self.new_params is None:
            self.new_params = {}
        if self.key_changes is None:
            self.key_changes = []


class BacktestDB:
    """回测数据库（使用统一数据库 stock_monitor.db）"""

    def __init__(self):
        # 表已在 store.py 的 init_database() 中统一创建
        pass

    def _get_conn(self):
        return get_conn()

    def save_signal(self, signal_data: dict, ai_analysis: str = "",
                    ai_confidence: float = 0) -> int:
        """保存信号记录"""
        conn = self._get_conn()
        cur = conn.execute("""
            INSERT INTO signals (timestamp, code, name, action, score, price,
                                ai_analysis, ai_confidence, technical_score,
                                capital_score, news_score)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            datetime.now().isoformat(),
            signal_data.get('code', ''),
            signal_data.get('name', ''),
            signal_data.get('action', 'hold'),
            signal_data.get('score', 0),
            signal_data.get('price', 0),
            ai_analysis,
            ai_confidence,
            signal_data.get('technical_score', 0),
            signal_data.get('capital_score', 0),
            signal_data.get('news_score', 0),
        ))
        conn.commit()
        row_id = cur.lastrowid
        conn.close()
        return row_id

    def update_actual_returns(self, signal_id: int, returns: dict):
        """回填实际收益"""
        conn = self._get_conn()
        conn.execute("""
            UPDATE signals SET
                actual_return_1d = ?, actual_return_3d = ?,
                actual_return_5d = ?, actual_return_10d = ?,
                max_drawdown = ?
            WHERE id = ?
        """, (
            returns.get('return_1d', 0), returns.get('return_3d', 0),
            returns.get('return_5d', 0), returns.get('return_10d', 0),
            returns.get('max_drawdown', 0), signal_id,
        ))
        conn.commit()
        conn.close()

    def get_pending_signals(self, days: int = 7) -> List[Dict]:
        """获取需要回填收益的信号"""
        conn = self._get_conn()
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        rows = conn.execute("""
            SELECT id, code, name, action, score, price, timestamp
            FROM signals
            WHERE timestamp > ? AND actual_return_1d = 0
            ORDER BY timestamp DESC
        """, (cutoff,)).fetchall()
        conn.close()

        return [
            {"id": r[0], "code": r[1], "name": r[2], "action": r[3],
             "score": r[4], "price": r[5], "timestamp": r[6]}
            for r in rows
        ]

    def get_signal_stats(self, days: int = 30) -> Dict:
        """获取信号统计"""
        conn = self._get_conn()
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        rows = conn.execute("""
            SELECT action,
                   COUNT(*) as total,
                   AVG(CASE WHEN actual_return_1d > 0 THEN 1 ELSE 0 END) as accuracy_1d,
                   AVG(actual_return_1d) as avg_return_1d,
                   AVG(actual_return_3d) as avg_return_3d,
                   AVG(actual_return_5d) as avg_return_5d
            FROM signals
            WHERE timestamp > ? AND actual_return_1d != 0
            GROUP BY action
        """, (cutoff,)).fetchall()
        conn.close()

        stats = {}
        for r in rows:
            stats[r[0]] = {
                "total": r[1], "accuracy_1d": r[2] * 100 if r[2] else 0,
                "avg_return_1d": r[3], "avg_return_3d": r[4], "avg_return_5d": r[5],
            }
        return stats

    def save_backtest_result(self, result: dict):
        """保存每日回测结果"""
        conn = self._get_conn()
        conn.execute("""
            INSERT INTO backtest_results (date, total_signals, buy_signals, sell_signals,
                                         accuracy_1d, accuracy_3d, accuracy_5d,
                                         avg_return_1d, avg_return_3d, avg_return_5d,
                                         sharpe_ratio, max_drawdown, win_rate,
                                         ai_evaluation, key_insights)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            date.today().isoformat(),
            result.get('total_signals', 0),
            result.get('buy_signals', 0),
            result.get('sell_signals', 0),
            result.get('accuracy_1d', 0), result.get('accuracy_3d', 0),
            result.get('accuracy_5d', 0),
            result.get('avg_return_1d', 0), result.get('avg_return_3d', 0),
            result.get('avg_return_5d', 0),
            result.get('sharpe_ratio', 0), result.get('max_drawdown', 0),
            result.get('win_rate', 0),
            result.get('ai_evaluation', ''),
            json.dumps(result.get('key_insights', []), ensure_ascii=False),
        ))
        conn.commit()
        conn.close()

    def save_strategy_version(self, params: dict, accuracy: float = 0,
                              sharpe: float = 0, reason: str = ""):
        """保存策略版本"""
        conn = self._get_conn()
        max_ver = conn.execute(
            "SELECT MAX(version) FROM strategy_versions"
        ).fetchone()[0] or 0

        conn.execute("""
            INSERT INTO strategy_versions (version, params, accuracy, sharpe_ratio, reason)
            VALUES (?, ?, ?, ?, ?)
        """, (max_ver + 1, json.dumps(params, ensure_ascii=False), accuracy, sharpe, reason))
        conn.commit()
        conn.close()
        return max_ver + 1

    def get_latest_strategy(self) -> Optional[Dict]:
        """获取最新策略参数"""
        conn = self._get_conn()
        row = conn.execute("""
            SELECT version, params, accuracy, sharpe_ratio, reason, created_at
            FROM strategy_versions ORDER BY version DESC LIMIT 1
        """).fetchone()
        conn.close()

        if row:
            return {
                "version": row[0], "params": json.loads(row[1]),
                "accuracy": row[2], "sharpe_ratio": row[3],
                "reason": row[4], "created_at": row[5],
            }
        return None

    def save_evolution_log(self, record: dict):
        """保存进化记录"""
        conn = self._get_conn()
        conn.execute("""
            INSERT INTO evolution_log (timestamp, version, old_params, new_params,
                                      accuracy_before, accuracy_after, ai_reasoning, key_changes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            datetime.now().isoformat(),
            record.get('version', 0),
            json.dumps(record.get('old_params', {}), ensure_ascii=False),
            json.dumps(record.get('new_params', {}), ensure_ascii=False),
            record.get('accuracy_before', 0),
            record.get('accuracy_after', 0),
            record.get('ai_reasoning', ''),
            json.dumps(record.get('key_changes', []), ensure_ascii=False),
        ))
        conn.commit()
        conn.close()

    def close(self):
        """兼容旧接口，无需操作"""
        pass


class StrategyEvolver:
    """策略进化引擎"""

    def __init__(self, llm_depot, backtest_db: BacktestDB):
        self.depot = llm_depot
        self.db = backtest_db

    def evaluate_and_evolve(self, current_params: dict) -> Optional[Dict]:
        """
        评估当前策略并决定是否进化
        返回新参数（如果需要进化）或 None
        """
        # 1. 获取近期信号统计
        stats = self.db.get_signal_stats(days=30)
        if not stats:
            console.print("[yellow]无足够数据评估策略[/yellow]")
            return None

        # 2. 获取回测历史
        latest = self.db.get_latest_strategy()
        history = []
        rows = self.db.conn.execute("""
            SELECT date, accuracy_1d, sharpe_ratio, win_rate, ai_evaluation
            FROM backtest_results ORDER BY date DESC LIMIT 30
        """).fetchall()
        for r in rows:
            history.append({
                "date": r[0], "accuracy": r[1], "sharpe": r[2],
                "win_rate": r[3], "evaluation": r[4],
            })

        # 3. AI评估
        prompt = f"""你是量化策略优化专家，评估以下策略表现并建议参数调整。

## 当前策略参数
{json.dumps(current_params, ensure_ascii=False, indent=2)}

## 近30天信号统计
{json.dumps(stats, ensure_ascii=False, indent=2)}

## 回测历史
{json.dumps(history[:10], ensure_ascii=False, indent=2)}

## 当前版本
{json.dumps(latest, ensure_ascii=False, indent=2) if latest else '首次评估'}

请评估并输出JSON：
{{
    "should_evolve": true/false,
    "reason": "评估原因",
    "current_accuracy": 当前准确率估计,
    "suggested_params": {{
        "technical_weight": 建议值,
        "capital_weight": 建议值,
        "news_weight": 建议值,
        "fundamental_weight": 建议值,
        "buy_threshold": 建议值,
        "sell_threshold": 建议值,
        "strong_buy_threshold": 建议值,
        "strong_sell_threshold": 建议值
    }},
    "key_changes": ["主要调整1", "主要调整2"],
    "expected_improvement": "预期改进说明"
}}"""

        response = self.depot.call(
            prompt,
            "你是量化策略优化专家，基于历史数据客观评估，保守调整参数。输出必须是合法JSON。",
            task_type="evolution",
            json_mode=True,
        )

        try:
            result = json.loads(response.content)
        except (json.JSONDecodeError, Exception):
            console.print(f"[yellow]AI进化评估解析失败: {response.content[:200]}[/yellow]")
            return None

        if not result.get("should_evolve"):
            console.print(f"[dim]策略无需进化: {result.get('reason', '')}[/dim]")
            return None

        # 4. 保存进化记录
        new_params = result.get("suggested_params", {})
        new_params["updated_at"] = datetime.now().isoformat()
        new_params["reason"] = result.get("reason", "")

        # 合并（只更新有建议的字段）
        merged = {**current_params}
        for k, v in new_params.items():
            if k in merged and v is not None:
                merged[k] = v

        # 验证权重和为1
        weight_sum = (merged.get("technical_weight", 0) + merged.get("capital_weight", 0) +
                      merged.get("news_weight", 0) + merged.get("fundamental_weight", 0))
        if abs(weight_sum - 1.0) > 0.05:
            console.print(f"[yellow]权重之和 {weight_sum:.2f} ≠ 1.0，跳过进化[/yellow]")
            return None

        # 保存
        version = self.db.save_strategy_version(
            merged,
            accuracy=result.get("current_accuracy", 0),
            reason=result.get("reason", ""),
        )

        self.db.save_evolution_log({
            "version": version,
            "old_params": current_params,
            "new_params": merged,
            "accuracy_before": result.get("current_accuracy", 0),
            "ai_reasoning": result.get("reason", ""),
            "key_changes": result.get("key_changes", []),
        })

        console.print(f"[green]✅ 策略进化到 v{version}: {result.get('reason', '')}[/green]")
        return merged
