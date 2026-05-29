"""
智能选股引擎 v2 - 使用腾讯/新浪数据源，更稳定
全市场扫描 + 短线机会推荐 + 资金流向
"""

import requests
import json
import re
import time
from datetime import datetime
from typing import List, Dict
from rich.console import Console

console = Console()

# 禁用代理
session = requests.Session()
session.trust_env = False
session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
})


class SmartStockPicker:
    """智能选股器 - 使用东方财富Web接口"""

    def __init__(self, config: dict = None):
        self.config = config or {}
        self.recommended_stocks = []

    def get_sector_fund_flow(self, count: int = 10) -> List[Dict]:
        """获取板块资金流向TOP N (东方财富Web接口)"""
        try:
            url = "https://push2.eastmoney.com/api/qt/clist/get"
            params = {
                'pn': 1, 'pz': count, 'po': 1, 'np': 1,
                'ut': 'b2884a393a59ad64002292a3e90d46a5',
                'fltt': 2, 'invt': 2, 'fid': 'f62',
                'fs': 'm:90+t:2',
                'fields': 'f12,f14,f2,f3,f62,f184,f66,f69,f72,f75,f78,f81,f84,f87,f204,f205,f124',
            }
            resp = session.get(url, params=params, timeout=15)
            data = resp.json()

            result = []
            if data.get('data') and data['data'].get('diff'):
                for item in data['data']['diff']:
                    result.append({
                        'name': item.get('f14', ''),
                        'change_pct': item.get('f3', 0),
                        'net_inflow': item.get('f62', 0),  # 主力净流入
                        'main_ratio': item.get('f184', 0),  # 主力净占比
                    })
            return result
        except Exception as e:
            console.print(f"[yellow]获取板块资金流向失败: {e}[/yellow]")
            return []

    def get_stock_fund_flow_top(self, count: int = 20) -> List[Dict]:
        """获取个股资金流入TOP N"""
        try:
            url = "https://push2.eastmoney.com/api/qt/clist/get"
            params = {
                'pn': 1, 'pz': count, 'po': 1, 'np': 1,
                'fltt': 2, 'invt': 2,
                'fid': 'f62',  # 按主力净流入排序
                'fs': 'm:0+t:6+f:!2,m:0+t:13+f:!2,m:0+t:80+f:!2,m:1+t:2+f:!2,m:1+t:23+f:!2,m:0+t:7+f:!2,m:1+t:3+f:!2',
                'fields': 'f12,f14,f2,f3,f62,f184,f66,f69,f72,f75,f78,f81,f84,f87,f204,f205,f124',
                'ut': 'b2884a393a59ad64002292a3e90d46a5',
            }
            resp = session.get(url, params=params, timeout=15)
            data = resp.json()

            result = []
            if data.get('data') and data['data'].get('diff'):
                for item in data['data']['diff']:
                    result.append({
                        'code': str(item.get('f12', '')),
                        'name': str(item.get('f14', '')),
                        'price': float(item.get('f2', 0) or 0),
                        'change_pct': float(item.get('f3', 0) or 0),
                        'main_net_inflow': float(item.get('f62', 0) or 0),
                        'main_net_ratio': float(item.get('f184', 0) or 0),
                        'super_large_net': float(item.get('f66', 0) or 0),
                        'large_net': float(item.get('f72', 0) or 0),
                        'medium_net': float(item.get('f78', 0) or 0),
                        'small_net': float(item.get('f84', 0) or 0),
                    })
            return result
        except Exception as e:
            console.print(f"[red]获取个股资金流向失败: {e}[/red]")
            return []

    def scan_short_term_opportunities(self, max_count: int = 10) -> List[Dict]:
        """
        扫描短线机会
        策略：
        1. 主力资金净流入 > 1000万
        2. 涨幅 2%~8%（不追涨停）
        3. 排除ST股
        4. 量能配合（从资金流向数据间接判断）
        """
        try:
            # 取资金流入TOP100候选
            url = "https://push2.eastmoney.com/api/qt/clist/get"
            params = {
                'pn': 1, 'pz': 100, 'po': 1, 'np': 1,
                'fltt': 2, 'invt': 2,
                'fid': 'f62',
                'fs': 'm:0+t:6+f:!2,m:0+t:13+f:!2,m:0+t:80+f:!2,m:1+t:2+f:!2,m:1+t:23+f:!2,m:0+t:7+f:!2,m:1+t:3+f:!2',
                'fields': 'f12,f14,f2,f3,f62,f184',
                'ut': 'b2884a393a59ad64002292a3e90d46a5',
            }
            resp = session.get(url, params=params, timeout=15)
            data = resp.json()

            candidates = []
            if data.get('data') and data['data'].get('diff'):
                for item in data['data']['diff']:
                    code = str(item.get('f12', ''))
                    name = str(item.get('f14', ''))
                    price = float(item.get('f2', 0) or 0)
                    change_pct = float(item.get('f3', 0) or 0)
                    main_net = float(item.get('f62', 0) or 0)

                    # 过滤条件
                    if main_net < 10000000:  # 主力净流入 < 1000万
                        continue
                    if change_pct < 2 or change_pct >= 9.9:  # 涨幅区间
                        continue
                    if 'ST' in name:  # 排除ST
                        continue
                    if price <= 0:  # 排除停牌
                        continue

                    # 评分
                    score = 0
                    if 3 <= change_pct <= 6:
                        score += 20
                    if main_net > 100000000:
                        score += 30
                    elif main_net > 50000000:
                        score += 20
                    else:
                        score += 10

                    candidates.append({
                        'code': code,
                        'name': name,
                        'price': price,
                        'change_pct': change_pct,
                        'main_net_inflow': main_net,
                        'score': score,
                        'recommend_date': datetime.now().strftime('%Y-%m-%d'),
                        'source': 'auto_pick',
                    })

            candidates.sort(key=lambda x: x['score'], reverse=True)
            self.recommended_stocks = candidates[:max_count]
            return self.recommended_stocks

        except Exception as e:
            console.print(f"[red]扫描短线机会失败: {e}[/red]")
            return []

    def generate_daily_report(self) -> str:
        """生成每日资金流向报表"""
        flow_top = self.get_stock_fund_flow_top(count=20)
        sectors = self.get_sector_fund_flow(count=10)

        lines = []
        lines.append(f"📊 每日资金流向报表 - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        lines.append("=" * 60)

        # 热门板块
        lines.append("\n🔥 今日热门板块 TOP10")
        lines.append("-" * 40)
        for i, s in enumerate(sectors, 1):
            net = s['net_inflow']
            lines.append(f"{i:2d}. {s['name']:<12} {s['change_pct']:+.2f}%  主力净流入: {net/1e4:.0f}万")

        # 个股资金流入TOP20
        lines.append("\n💰 个股资金流入 TOP20")
        lines.append("-" * 60)
        for i, s in enumerate(flow_top, 1):
            net = s['main_net_inflow']
            if net > 100000000:
                direction = "🔴 强力流入"
            elif net > 50000000:
                direction = "🟠 大幅流入"
            elif net > 10000000:
                direction = "🟡 流入"
            else:
                direction = "⚪ 小幅流入"

            lines.append(
                f"{i:2d}. {s['code']:<8} {s['name']:<10} "
                f"¥{s['price']:>7.2f} {s['change_pct']:>+6.2f}% "
                f"主力: {net/1e4:>8.0f}万 {direction}"
            )

        lines.append("\n" + "=" * 60)
        return "\n".join(lines)


if __name__ == "__main__":
    picker = SmartStockPicker()

    print("扫描短线机会...")
    stocks = picker.scan_short_term_opportunities(max_count=10)
    print(f"推荐 {len(stocks)} 只短线机会股票:")
    for s in stocks:
        print(f"  {s['code']} {s['name']} ¥{s['price']:.2f} {s['change_pct']:+.2f}% 主力净流入: {s['main_net_inflow']/1e4:.0f}万")

    print("\n生成报表...")
    report = picker.generate_daily_report()
    print(report)
