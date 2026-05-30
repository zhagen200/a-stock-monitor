"""工具函数"""

import time
import requests

# 禁用代理的session
_session = requests.Session()
_session.trust_env = False
_session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
})


def fv(v) -> str:
    """格式化成交量"""
    if not v: return "—"
    v = float(v)
    return f"{v/1e8:.2f}亿" if v >= 1e8 else f"{v/1e4:.0f}万"


def fa(v) -> str:
    """格式化金额"""
    if not v: return "—"
    v = float(v)
    return f"{v/1e8:.2f}亿" if v >= 1e8 else f"{v/1e4:.0f}万"


def get_extra(data_manager, codes: list) -> dict:
    """批量获取股票额外数据"""
    r = {}
    for c in codes:
        q = data_manager.get_realtime_quote(c)
        f = data_manager.get_fund_flow(c)
        r[c] = {**(q or {}), **(f or {})}
        time.sleep(0.05)
    return r


def get_market_breadth() -> dict:
    """获取市场涨跌家数 (东方财富API)"""
    try:
        url = "https://push2.eastmoney.com/api/qt/clist/get"
        # 涨的
        params = {
            'pn': 1, 'pz': 1, 'po': 1, 'np': 1,
            'fltt': 2, 'invt': 2, 'fid': 'f3',
            'fs': 'm:0+t:6+f:!2,m:0+t:13+f:!2,m:0+t:80+f:!2,m:1+t:2+f:!2,m:1+t:23+f:!2',
            'fields': 'f3',
            'ut': 'b2884a393a59ad64002292a3e90d46a5',
        }
        resp = _session.get(url, params=params, timeout=10)
        total = resp.json().get('data', {}).get('total', 0)

        # 涨的 (change_pct > 0)
        params['fid'] = 'f3'
        params['po'] = 1  # 降序
        resp_up = _session.get(url, params=params, timeout=10)
        # 用不同方式获取涨跌家数
        # 获取涨停/跌停
        params_limit_up = {
            'pn': 1, 'pz': 1, 'po': 1, 'np': 1,
            'fltt': 2, 'invt': 2, 'fid': 'f3',
            'fs': 'm:0+t:6+f:!2,m:0+t:13+f:!2,m:0+t:80+f:!2,m:1+t:2+f:!2,m:1+t:23+f:!2',
            'fields': 'f3',
            'ut': 'b2884a393a59ad64002292a3e90d46a5',
        }
        # 简化：返回总数，让前端估算
        return {"total": total}
    except Exception:
        return {"total": 0}


def get_sector_data(count: int = 30) -> list:
    """获取板块行情数据 (东方财富API)"""
    try:
        url = "https://push2.eastmoney.com/api/qt/clist/get"
        params = {
            'pn': 1, 'pz': count, 'po': 1, 'np': 1,
            'ut': 'b2884a393a59ad64002292a3e90d46a5',
            'fltt': 2, 'invt': 2, 'fid': 'f3',  # 按涨跌幅排序
            'fs': 'm:90+t:2',  # 行业板块
            'fields': 'f12,f14,f2,f3,f62,f184,f104,f105,f124',
        }
        resp = _session.get(url, params=params, timeout=15)
        data = resp.json()
        result = []
        if data.get('data') and data['data'].get('diff'):
            for item in data['data']['diff']:
                result.append({
                    'code': item.get('f12', ''),
                    'name': item.get('f14', ''),
                    'price': float(item.get('f2', 0) or 0),
                    'change_pct': float(item.get('f3', 0) or 0),
                    'net_inflow': float(item.get('f62', 0) or 0),
                    'main_ratio': float(item.get('f184', 0) or 0),
                    'up_count': int(item.get('f104', 0) or 0),
                    'down_count': int(item.get('f105', 0) or 0),
                })
        return result
    except Exception:
        return []


def get_concept_data(count: int = 30) -> list:
    """获取概念板块数据 (东方财富API)"""
    try:
        url = "https://push2.eastmoney.com/api/qt/clist/get"
        params = {
            'pn': 1, 'pz': count, 'po': 1, 'np': 1,
            'ut': 'b2884a393a59ad64002292a3e90d46a5',
            'fltt': 2, 'invt': 2, 'fid': 'f3',
            'fs': 'm:90+t:3',  # 概念板块
            'fields': 'f12,f14,f2,f3,f62,f184,f104,f105,f124',
        }
        resp = _session.get(url, params=params, timeout=15)
        data = resp.json()
        result = []
        if data.get('data') and data['data'].get('diff'):
            for item in data['data']['diff']:
                result.append({
                    'code': item.get('f12', ''),
                    'name': item.get('f14', ''),
                    'price': float(item.get('f2', 0) or 0),
                    'change_pct': float(item.get('f3', 0) or 0),
                    'net_inflow': float(item.get('f62', 0) or 0),
                    'up_count': int(item.get('f104', 0) or 0),
                    'down_count': int(item.get('f105', 0) or 0),
                })
        return result
    except Exception:
        return []


def get_top_stocks(count: int = 20, sort_by: str = "f3", ascending: bool = False) -> list:
    """获取涨幅/跌幅/换手率TOP股票
    ascending=True: 升序（跌幅榜用）
    """
    try:
        url = "https://push2.eastmoney.com/api/qt/clist/get"
        params = {
            'pn': 1, 'pz': count,
            'po': 0 if ascending else 1,  # 0=升序, 1=降序
            'np': 1,
            'fltt': 2, 'invt': 2,
            'fid': sort_by,
            'fs': 'm:0+t:6+f:!2,m:0+t:13+f:!2,m:0+t:80+f:!2,m:1+t:2+f:!2,m:1+t:23+f:!2',
            'fields': 'f12,f14,f2,f3,f5,f6,f7,f8,f62,f184,f115',
            'ut': 'b2884a393a59ad64002292a3e90d46a5',
        }
        resp = _session.get(url, params=params, timeout=15)
        data = resp.json()
        result = []
        if data.get('data') and data['data'].get('diff'):
            for item in data['data']['diff']:
                result.append({
                    'code': str(item.get('f12', '')),
                    'name': str(item.get('f14', '')),
                    'price': float(item.get('f2', 0) or 0),
                    'change_pct': float(item.get('f3', 0) or 0),
                    'volume': float(item.get('f5', 0) or 0),
                    'amount': float(item.get('f6', 0) or 0),
                    'amplitude': float(item.get('f7', 0) or 0),
                    'turnover_rate': float(item.get('f8', 0) or 0),
                    'main_net_inflow': float(item.get('f62', 0) or 0),
                    'pe_ratio': float(item.get('f115', 0) or 0),
                })
        return result
    except Exception:
        return []


def get_board_stocks(board_code: str, board_type: str = "industry", count: int = 30) -> list:
    """获取板块成分股列表
    board_type: 'industry' (行业板块) 或 'concept' (概念板块)
    """
    try:
        # 板块代码格式: BK0475 (行业) 或 BK0655 (概念)
        fs = f"b:{board_code}"
        url = "https://push2.eastmoney.com/api/qt/clist/get"
        params = {
            'pn': 1, 'pz': count, 'po': 1, 'np': 1,
            'fltt': 2, 'invt': 2,
            'fid': 'f3',  # 按涨跌幅排序
            'fs': fs,
            'fields': 'f12,f14,f2,f3,f5,f6,f7,f8,f62,f184,f115',
            'ut': 'b2884a393a59ad64002292a3e90d46a5',
        }
        resp = _session.get(url, params=params, timeout=15)
        data = resp.json()
        result = []
        if data.get('data') and data['data'].get('diff'):
            for item in data['data']['diff']:
                result.append({
                    'code': str(item.get('f12', '')),
                    'name': str(item.get('f14', '')),
                    'price': float(item.get('f2', 0) or 0),
                    'change_pct': float(item.get('f3', 0) or 0),
                    'volume': float(item.get('f5', 0) or 0),
                    'amount': float(item.get('f6', 0) or 0),
                    'amplitude': float(item.get('f7', 0) or 0),
                    'turnover_rate': float(item.get('f8', 0) or 0),
                    'main_net_inflow': float(item.get('f62', 0) or 0),
                    'pe_ratio': float(item.get('f115', 0) or 0),
                })
        return result
    except Exception:
        return []


def render_stock_table(stocks: list, key_prefix: str = ""):
    """渲染股票列表表格 (通用组件)"""
    if not stocks:
        return
    import streamlit as st

    table_html = '<table class="data-table"><tr>'
    for h in ["#","代码","名称","现价","涨跌幅","成交量","成交额","换手率","主力净流入"]:
        table_html += f'<th>{h}</th>'
    table_html += '</tr>'

    for i, s in enumerate(stocks):
        chg = s.get("change_pct", 0)
        color = "#ef4444" if chg >= 0 else "#22c55e"
        ar = "▲" if chg >= 0 else "▼"
        net = s.get("main_net_inflow", 0)
        nc = "#ef4444" if net >= 0 else "#22c55e"

        table_html += '<tr>'
        table_html += f'<td style="color:#64748b">{i+1}</td>'
        table_html += f'<td style="color:#60a5fa">{s.get("code","")}</td>'
        table_html += f'<td style="color:#f1f5f9;font-weight:500">{s.get("name","")}</td>'
        table_html += f'<td style="color:#f1f5f9">¥{s.get("price",0):.2f}</td>'
        table_html += f'<td style="color:{color};font-weight:600">{ar} {abs(chg):.2f}%</td>'
        table_html += f'<td style="color:#e2e8f0">{fv(s.get("volume",0))}</td>'
        table_html += f'<td style="color:#e2e8f0">{fa(s.get("amount",0))}</td>'
        table_html += f'<td style="color:#e2e8f0">{s.get("turnover_rate",0):.2f}%</td>'
        table_html += f'<td style="color:{nc}">{fa(net)}</td>'
        table_html += '</tr>'

    table_html += '</table>'
    st.markdown(table_html, unsafe_allow_html=True)
