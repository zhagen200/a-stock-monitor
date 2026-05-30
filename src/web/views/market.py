"""大盘行情页面 - 市场全景、板块热力图、涨跌排行、板块成分股"""

import streamlit as st
from datetime import datetime
from src.web.styles import GLOBAL_CSS
from src.web.helpers import fv, fa, get_sector_data, get_concept_data, get_top_stocks, get_board_stocks, render_stock_table


def _render_board_detail(board_code, board_name, board_type):
    """渲染板块成分股详情"""
    st.markdown(f"#### 📋 {board_name} 成分股")
    with st.spinner(f"加载 {board_name} 成分股..."):
        stocks = get_board_stocks(board_code, board_type, count=30)
    if stocks:
        render_stock_table(stocks)
        st.caption(f"共 {len(stocks)} 只股票，按涨跌幅排序")
    else:
        st.info("获取成分股数据失败")


def _render_sector_tab(sectors, board_type="industry"):
    """渲染板块Tab (行业/概念通用)"""
    if not sectors:
        st.info("获取板块数据失败")
        return

    # 用selectbox选择板块，点击后显示成分股
    board_names = [f"{s['name']} ({s['change_pct']:+.2f}%)" for s in sectors]
    selected = st.selectbox(
        "选择板块查看成分股",
        board_names,
        key=f"board_select_{board_type}"
    )
    idx = board_names.index(selected)
    board = sectors[idx]

    # 板块信息卡片
    chg = board.get("change_pct", 0)
    net = board.get("net_inflow", 0)
    color = "#ef4444" if chg >= 0 else "#22c55e"
    nc = "#ef4444" if net >= 0 else "#22c55e"

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("涨跌幅", f"{chg:+.2f}%")
    c2.metric("主力净流入", fa(net))
    c3.metric("上涨家数", board.get("up_count", 0))
    c4.metric("下跌家数", board.get("down_count", 0))

    # 显示成分股
    _render_board_detail(board["code"], board["name"], board_type)

    st.divider()

    # 板块排行表格
    st.markdown("#### 板块排行")
    table_html = '<table class="data-table"><tr>'
    for h in ["#","板块名称","涨跌幅","主力净流入","上涨","下跌"]:
        table_html += f'<th>{h}</th>'
    table_html += '</tr>'

    for i, s in enumerate(sectors[:20]):
        chg = s.get("change_pct", 0)
        color = "#ef4444" if chg >= 0 else "#22c55e"
        ar = "▲" if chg >= 0 else "▼"
        net = s.get("net_inflow", 0)
        nc = "#ef4444" if net >= 0 else "#22c55e"

        table_html += '<tr>'
        table_html += f'<td style="color:#64748b">{i+1}</td>'
        table_html += f'<td style="color:#f1f5f9;font-weight:500">{s["name"]}</td>'
        table_html += f'<td style="color:{color};font-weight:600">{ar} {abs(chg):.2f}%</td>'
        table_html += f'<td style="color:{nc}">{fa(net)}</td>'
        table_html += f'<td style="color:#ef4444">{s.get("up_count",0)}</td>'
        table_html += f'<td style="color:#22c55e">{s.get("down_count",0)}</td>'
        table_html += '</tr>'

    table_html += '</table>'
    st.markdown(table_html, unsafe_allow_html=True)


def _render_top_stocks_tab(title, sort_by, ascending=False):
    """渲染涨跌/换手率排行Tab"""
    stocks = get_top_stocks(count=30, sort_by=sort_by, ascending=ascending)
    if not stocks:
        st.info(f"获取{title}数据失败")
        return

    # 选择股票查看详情
    stock_names = [f"{s['name']}({s['code']}) {s['change_pct']:+.2f}%" for s in stocks]
    selected = st.selectbox("选择股票查看详情", stock_names, key=f"top_select_{sort_by}_{ascending}")
    idx = stock_names.index(selected)
    stock = stocks[idx]

    # 股票详情卡片
    chg = stock.get("change_pct", 0)
    color = "#ef4444" if chg >= 0 else "#22c55e"

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("现价", f"¥{stock.get('price',0):.2f}")
    c2.metric("涨跌幅", f"{chg:+.2f}%")
    c3.metric("成交额", fa(stock.get("amount",0)))
    c4.metric("换手率", f"{stock.get('turnover_rate',0):.2f}%")
    c5.metric("振幅", f"{stock.get('amplitude',0):.2f}%")
    net = stock.get("main_net_inflow", 0)
    c6.metric("主力净流入", fa(net))

    st.divider()

    # 排行表格
    st.markdown(f"#### {title} TOP30")
    render_stock_table(stocks)


def render_market_page(data_manager):
    """大盘行情页面"""
    st.markdown("## 📈 大盘行情")

    # ── 大盘指数 ──
    indices = data_manager.get_market_index()
    if indices:
        cols = st.columns(len(indices))
        for i, (name, data) in enumerate(indices.items()):
            with cols[i]:
                chg = data.get("change_pct", 0)
                st.metric(
                    label=name,
                    value=f"{data.get('price',0):.2f}",
                    delta=f"{chg:+.2f}%",
                    delta_color="normal"
                )

    st.divider()

    # ── Tab: 行业板块 | 概念板块 | 涨幅榜 | 跌幅榜 | 换手率 ──
    t1, t2, t3, t4, t5 = st.tabs(["🏭 行业板块", "💡 概念板块", "🔴 涨幅榜", "🟢 跌幅榜", "🔄 换手率"])

    with t1:
        sectors = get_sector_data(count=50)
        _render_sector_tab(sectors, "industry")

    with t2:
        concepts = get_concept_data(count=50)
        _render_sector_tab(concepts, "concept")

    with t3:
        _render_top_stocks_tab("涨幅榜", "f3", ascending=False)

    with t4:
        _render_top_stocks_tab("跌幅榜", "f3", ascending=True)

    with t5:
        _render_top_stocks_tab("换手率榜", "f8", ascending=False)
