"""
通知推送模块
支持企业微信机器人、钉钉、Server酱（带每日限额保护）、Bark
"""

import requests
import json
import os
import sqlite3
from datetime import datetime, date
from typing import Optional
from rich.console import Console
from pathlib import Path

console = Console()

# Server酱每日免费额度
SERVERCHAN_DAILY_LIMIT = 5
# 本地计数器文件
_counter_db = Path(__file__).parent.parent.parent / "logs" / "push_counter.db"


class PushCounter:
    """推送次数计数器（SQLite持久化）"""

    def __init__(self):
        _counter_db.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(_counter_db))
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS push_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel TEXT NOT NULL,
                push_date TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now','localtime'))
            )
        """)
        self.conn.commit()

    def count_today(self, channel: str) -> int:
        """查询今日某渠道推送次数"""
        cur = self.conn.execute(
            "SELECT COUNT(*) FROM push_log WHERE channel=? AND push_date=?",
            (channel, date.today().isoformat())
        )
        return cur.fetchone()[0]

    def record(self, channel: str):
        """记录一次推送"""
        self.conn.execute(
            "INSERT INTO push_log (channel, push_date) VALUES (?, ?)",
            (channel, date.today().isoformat())
        )
        self.conn.commit()

    def can_push(self, channel: str, limit: int) -> bool:
        """是否还能推送"""
        return self.count_today(channel) < limit

    def remaining(self, channel: str, limit: int) -> int:
        """剩余次数"""
        return max(0, limit - self.count_today(channel))

    def close(self):
        self.conn.close()


class Notifier:
    """多渠道通知推送"""

    def __init__(self, config: dict = None):
        config = config or {}
        notify_config = config.get("notify", {})
        self.enabled = notify_config.get("enabled", True)
        self.wecom_webhook = notify_config.get("wecom_webhook", "")
        self.dingtalk_webhook = notify_config.get("dingtalk_webhook", "")
        self.serverchan_key = notify_config.get("serverchan_key", "")
        self.bark_url = notify_config.get("bark_url", "")
        self.counter = PushCounter()

    def send(self, title: str, content: str, level: str = "info") -> bool:
        """发送通知到所有配置的渠道"""
        if not self.enabled:
            return False

        success = False

        # 企业微信 - 无限制
        if self.wecom_webhook:
            success |= self._send_wecom(title, content)

        # 钉钉 - 无限制
        if self.dingtalk_webhook:
            success |= self._send_dingtalk(title, content)

        # Server酱 (每日额度保护)
        if self.serverchan_key:
            if self.counter.can_push("serverchan", SERVERCHAN_DAILY_LIMIT):
                ok = self._send_serverchan(title, content)
                if ok:
                    self.counter.record("serverchan")
                    console.print(f"[dim]Server酱推送成功 (今日剩余{self.counter.remaining('serverchan', SERVERCHAN_DAILY_LIMIT)}次)[/dim]")
                success |= ok
            else:
                console.print(f"[yellow]Server酱每日限额已用完 ({SERVERCHAN_DAILY_LIMIT}次)[/yellow]")

        # Bark - 无限制
        if self.bark_url:
            success |= self._send_bark(title, content)

        # 无推送渠道时打印到控制台
        if not any([self.wecom_webhook, self.dingtalk_webhook,
                    self.serverchan_key, self.bark_url]):
            console.print(f"\n[bold cyan]📢 {title}[/bold cyan]")
            console.print(content)
            success = True

        return success

    def send_signal(self, signal) -> bool:
        """发送交易信号通知"""
        action_map = {
            "strong_buy": "🔴 强烈买入",
            "buy": "🟠 买入",
            "hold": "⚪ 观望",
            "sell": "🟢 卖出",
            "strong_sell": "🔵 强烈卖出",
        }

        title = f"{action_map.get(signal.action, signal.action)} {signal.name}({signal.code})"

        content = f"""📊 交易信号
━━━━━━━━━━━━━━━━━━━━
股票：{signal.name} ({signal.code})
当前价：¥{signal.price:.2f}
操作：{action_map.get(signal.action, signal.action)}
综合评分：{signal.score:.1f} 分
置信度：{self._confidence_bar(signal.confidence)}

📈 评分明细
├─ 技术面：{signal.technical_score:.1f} (权重40%)
├─ 资金面：{signal.capital_score:.1f} (权重20%)
├─ 消息面：{signal.news_score:.1f} (权重25%)
└─ 基本面：{signal.fundamental_score:.1f} (权重15%)

🎯 关键价位
├─ 止损位：¥{signal.stop_loss:.2f}
├─ 止盈1：¥{signal.take_profit_1:.2f}
├─ 止盈2：¥{signal.take_profit_2:.2f}
├─ 支撑位：{', '.join([f'¥{s}' for s in signal.support_levels[:3]]) or '无'}
└─ 阻力位：{', '.join([f'¥{r}' for r in signal.resistance_levels[:3]]) or '无'}

💡 信号依据
{chr(10).join(['• ' + r for r in signal.reasons[:5]])}

⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"""

        return self.send(title, content)

    def _confidence_bar(self, pct: float) -> str:
        """生成置信度进度条"""
        filled = int(pct / 10)
        return f"[{'█' * filled}{'░' * (10-filled)}] {pct:.0f}%"

    def _send_wecom(self, title: str, content: str) -> bool:
        """企业微信机器人（无限制）"""
        try:
            data = {
                "msgtype": "markdown",
                "markdown": {"content": f"### {title}\n{content}"}
            }
            resp = requests.post(self.wecom_webhook, json=data, timeout=10)
            return resp.json().get("errcode") == 0
        except Exception as e:
            console.print(f"[red]企业微信推送失败: {e}[/red]")
            return False

    def _send_dingtalk(self, title: str, content: str) -> bool:
        """钉钉机器人（无限制，支持自定义关键词）"""
        try:
            # 关键词安全模式：消息内容必须包含设置的关键词
            # 确保 "交易信号" 出现在消息中（这是钉钉机器人的安全关键词）
            if "交易信号" not in title and "交易信号" not in content:
                content = f"📊 交易信号\n{content}"

            data = {
                "msgtype": "markdown",
                "markdown": {
                    "title": title,
                    "text": f"### {title}\n\n{content}"
                }
            }
            resp = requests.post(self.dingtalk_webhook, json=data, timeout=10)
            result = resp.json()
            if result.get("errcode") != 0:
                console.print(f"[yellow]钉钉返回: {result.get('errmsg', 'unknown')}[/yellow]")
            return result.get("errcode") == 0
        except Exception as e:
            console.print(f"[red]钉钉推送失败: {e}[/red]")
            return False

    def _send_serverchan(self, title: str, content: str) -> bool:
        """Server酱（每日限额5次）"""
        try:
            url = f"https://sctapi.ftqq.com/{self.serverchan_key}.send"
            data = {"title": title, "desp": content}
            resp = requests.post(url, data=data, timeout=10)
            return resp.json().get("code") == 0
        except Exception as e:
            console.print(f"[red]Server酱推送失败: {e}[/red]")
            return False

    def _send_bark(self, title: str, content: str) -> bool:
        """Bark (iOS, 无限制)"""
        try:
            url = f"{self.bark_url}/{title}/{content}"
            resp = requests.get(url, timeout=10)
            return resp.status_code == 200
        except Exception as e:
            console.print(f"[red]Bark推送失败: {e}[/red]")
            return False
