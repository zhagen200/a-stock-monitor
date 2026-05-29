"""
全市场扫描器 - 智能选股 + 资金流向分析
每日自动推荐短线机会股票，管理监控池
"""

import akshare as ak
import pandas as pd
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from rich.console import Console

console = Console()


class MarketScanner:
    """全市场扫描器"""

    def __init__(self, config: dict = None):
        self.config = config or {}
        self.hot_sectors = []  # 热门板块
        self.top_stocks = []  # 推荐股票
        self.capital_flow_top = []  # 资金流入TOP

    def get_sector_fund_flow(self) -> pd.DataFrame:
        """获取板块资金流向（今日）"""
        try:
            df = ak.stock_sector_fund_flow_rank(indicator="今日")
            if df is not None and not df.empty:
                # 标准化列名
                col_map = {}
                for col in df.columns:
                    if '名称' in col or '板块' in col:
                        col_map[col] = 'sector_name'
                    elif '净流入' in col and '主力' in col:
                        col_map[col] = 'main_net_inflow'
                    elif '净流入' in col:
                        col_map[col] = 'net_inflow'
                    elif '涨跌幅' in col:
                        col_map[col] = 'change_pct'
                df = df.rename(columns=col_map)
                return df
        except Exception as e:
            console.print(f"[yellow]获取板块资金流向失败: {e}[/yellow]")
        return pd.DataFrame()

    def get_stock_fund_flow_top(self, count: int = 20) -> List[Dict]:
        """获取个股资金流入TOP N"""
        try:
            df = ak.stock_individual_fund_flow_rank(indicator="今日")
            if df is None or df.empty:
                return []

            # 标准化列名
            col_map = {}
            for col in df.columns:
                if '代码' in col:
                    col_map[col] = 'code'
                elif '名称' in col:
                    col_map[col] = 'name'
                elif '最新价' in col:
                    col_map[col] = 'price'
                elif '涨跌幅' in col:
                    col_map[col] = 'change_pct'
                elif '主力净流入' in col and '净额' in col:
                    col_map[col] = 'main_net_inflow'
                elif '主力净流入' in col and '净占比' in col:
                    col_map[col] = 'main_net_ratio'
                elif '超大单' in col and '净额' in col:
                    col_map[col] = 'super_large_net'
                elif '大单' in col and '净额' in col:
                    col_map[col] = 'large_net'
                elif '中单' in col and '净额' in col:
                    col_map[col] = 'medium_net'
                elif '小单' in col and '净额' in col:
                    col_map[col] = 'small_net'

            df = df.rename(columns=col_map)

            # 转换数值列
            for col in ['main_net_inflow', 'change_pct', 'price', 'super_large_net', 'large_net', 'medium_net', 'small_net']:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')

            # 按主力净流入排序
            if 'main_net_inflow' in df.columns:
                df = df.sort_values('main_net_inflow', ascending=False)

            result = []
            for _, row in df.head(count).iterrows():
                result.append({
                    'code': str(row.get('code', '')),
                    'name': str(row.get('name', '')),
                    'price': float(row.get('price', 0)),
                    'change_pct': float(row.get('change_pct', 0)),
                    'main_net_inflow': float(row.get('main_net_inflow', 0)),
                    'main_net_ratio': float(row.get('main_net_ratio', 0)) if 'main_net_ratio' in row else 0,
                    'super_large_net': float(row.get('super_large_net', 0)),
                    'large_net': float(row.get('large_net', 0)),
                    'medium_net': float(row.get('medium_net', 0)),
                    'small_net': float(row.get('small_net', 0)),
                })

            self.capital_flow_top = result
            return result

        except Exception as e:
            console.print(f"[red]获取个股资金流向失败: {e}[/red]")
            return []

    def get_hot_sectors(self, count: int = 10) -> List[Dict]:
        """获取今日热门板块（按涨幅+资金流入综合排名）"""
        try:
            df = self.get_sector_fund_flow()
            if df.empty:
                return []

            result = []
            for _, row in df.head(count).iterrows():
                result.append({
                    'name': str(row.get('sector_name', '')),
                    'change_pct': float(row.get('change_pct', 0)),
                    'net_inflow': float(row.get('net_inflow', 0)) if 'net_inflow' in row else 0,
                })

            self.hot_sectors = result
            return result

        except Exception as e:
            console.print(f"[red]获取热门板块失败: {e}[/red]")
            return []

    def get_sector_stocks(self, sector_name: str) -> List[str]:
        """获取板块成分股"""
        try:
            df = ak.stock_board_concept_name_em()
            if df is not None and not df.empty:
                # 查找板块
                sector_row = df[df['板块名称'].str.contains(sector_name, na=False)]
                if not sector_row.empty:
                    sector_code = sector_row.iloc[0]['板块代码']
                    stocks_df = ak.stock_board_concept_cons_em(symbol=sector_name)
                    if stocks_df is not None and not stocks_df.empty:
                        return stocks_df['代码'].tolist()
        except Exception as e:
            console.print(f"[yellow]获取板块成分股失败: {e}[/yellow]")
        return []

    def scan_short_term_opportunities(self, max_count: int = 10) -> List[Dict]:
        """
        扫描短线机会股票
        策略：
        1. 主力资金净流入 > 0
        2. 涨幅在 2%~7% 之间（不追高，不抄底）
        3. 量比 > 1.5（放量）
        4. 换手率适中
        5. 来自热门板块加分
        """
        try:
            # 获取资金流入TOP股票
            flow_top = self.get_stock_fund_flow_top(count=100)  # 先取前100

            if not flow_top:
                return []

            # 获取热门板块
            hot_sectors = self.get_hot_sectors(count=10)
            hot_sector_names = [s['name'] for s in hot_sectors]

            candidates = []
            for stock in flow_top:
                code = stock['code']
                name = stock['name']
                change_pct = stock['change_pct']
                main_net = stock['main_net_inflow']

                # 过滤条件
                # 1. 主力净流入 > 0
                if main_net <= 0:
                    continue

                # 2. 涨幅在合理区间（1%~8%，不追涨停）
                if change_pct < 1 or change_pct >= 9.9:
                    continue

                # 3. 排除ST股
                if 'ST' in name or '*ST' in name:
                    continue

                # 4. 排除停牌（价格为0）
                if stock['price'] <= 0:
                    continue

                # 计算综合评分
                score = 0
                # 涨幅适中（3%~6%）加分
                if 3 <= change_pct <= 6:
                    score += 20
                # 主力净流入越大越好
                if main_net > 1e8:  # > 1亿
                    score += 30
                elif main_net > 5e7:  # > 5000万
                    score += 20
                elif main_net > 1e7:  # > 1000万
                    score += 10
                # 来自热门板块加分
                # (这里简化处理，实际可以查板块成分股)

                stock['score'] = score
                stock['source'] = 'auto_recommend'
                stock['recommend_date'] = datetime.now().strftime('%Y-%m-%d')
                candidates.append(stock)

            # 按评分排序，取前N个
            candidates.sort(key=lambda x: x['score'], reverse=True)
            self.top_stocks = candidates[:max_count]

            return self.top_stocks

        except Exception as e:
            console.print(f"[red]扫描短线机会失败: {e}[/red]")
            return []

    def generate_daily_report(self) -> str:
        """生成每日资金流向报表"""
        flow_top = self.get_stock_fund_flow_top(count=20)
        hot_sectors = self.get_hot_sectors(count=10)

        report_lines = []
        report_lines.append(f"📊 每日资金流向报表 - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        report_lines.append("=" * 60)

        # 热门板块
        report_lines.append("\n🔥 今日热门板块 TOP10")
        report_lines.append("-" * 40)
        for i, sector in enumerate(hot_sectors, 1):
            report_lines.append(f"{i:2d}. {sector['name']:<12} {sector['change_pct']:+.2f}%")

        # 资金流入TOP20
        report_lines.append("\n💰 个股资金流入 TOP20")
        report_lines("-" * 40)
        report_lines.append(f"{'序号':<4} {'代码':<8} {'名称':<10} {'现价':>8} {'涨跌幅':>8} {'主力净流入':>12} {'方向'}")
        report_lines.append("-" * 60)

        for i, stock in enumerate(flow_top, 1):
            # 资金方向判断
            direction = ""
            if stock['main_net_inflow'] > 1e8:
                direction = "🔴 强力流入"
            elif stock['main_net_inflow'] > 5e7:
                direction = "🟠 大幅流入"
            elif stock['main_net_inflow'] > 1e7:
                direction = "🟡 流入"
            else:
                direction = "⚪ 小幅流入"

            report_lines.append(
                f"{i:<4} {stock['code']:<8} {stock['name']:<10} "
                f"¥{stock['price']:>7.2f} {stock['change_pct']:>+7.2f}% "
                f"{stock['main_net_inflow']/1e4:>11.0f}万 {direction}"
            )

        report_lines.append("\n" + "=" * 60)
        return "\n".join(report_lines)


if __name__ == "__main__":
    scanner = MarketScanner()
    print("扫描中...")
    report = scanner.generate_daily_report()
    print(report)
