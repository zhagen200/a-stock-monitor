"""选股筛选器页面 - 多条件筛选 + 股票详情"""

import streamlit as st
from src.web.helpers import get_top_stocks, fv, fa, render_stock_table


def render_screener_page():
    """选股筛选器页面"""
    st.markdown("## 🔍 选股筛选器")

    # ── 筛选条件 ──
    with st.expander("📋 筛选条件", expanded=True):
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            chg_min, chg_max = st.slider("涨跌幅(%)", -10.0, 10.0, (-3.0, 8.0), 0.1)
        with c2:
            turnover_min = st.number_input("最低换手率(%)", 0.0, 50.0, 1.0, 0.5)
        with c3:
            amount_min = st.number_input("最低成交额(亿)", 0.0, 100.0, 0.5, 0.1)
        with c4:
            pe_max = st.number_input("最大市盈率", 0.0, 500.0, 100.0, 10.0)

        c5, c6 = st.columns(2)
        with c5:
            sort_options = {
                "涨跌幅高→低": "f3",
                "换手率高→低": "f8",
                "成交额高→低": "f6",
                "主力净流入高→低": "f62",
            }
            sort_by = st.selectbox("排序方式", list(sort_options.keys()))
        with c6:
            count = st.slider("显示数量", 10, 100, 30, 10)

    if st.button("🔍 开始筛选", use_container_width=True):
        with st.spinner("正在筛选..."):
            stocks = get_top_stocks(count=200, sort_by=sort_options[sort_by])

            if not stocks:
                st.error("获取数据失败，请稍后重试")
                return

            filtered = []
            for s in stocks:
                chg = s.get("change_pct", 0)
                turnover = s.get("turnover_rate", 0)
                amount = s.get("amount", 0) / 1e8
                pe = s.get("pe_ratio", 0)

                if chg < chg_min or chg > chg_max: continue
                if turnover < turnover_min: continue
                if amount < amount_min: continue
                if pe_max > 0 and pe > pe_max: continue
                if pe < 0: continue

                filtered.append(s)

            st.session_state["screener_results"] = filtered[:count]
            st.session_state["screener_count"] = len(filtered)

    results = st.session_state.get("screener_results", [])
    total = st.session_state.get("screener_count", 0)

    if results:
        st.markdown(f"### 筛选结果: {total} 只 (显示前{len(results)}只)")

        # 选择股票查看详情
        stock_names = [f"{s['name']}({s['code']}) {s['change_pct']:+.2f}%" for s in results]
        selected = st.selectbox("选择股票查看详情", stock_names, key="screener_detail")
        idx = stock_names.index(selected)
        stock = results[idx]

        # 股票详情
        chg = stock.get("change_pct", 0)
        c1, c2, c3, c4, c5, c6 = st.columns(6)
        c1.metric("现价", f"¥{stock.get('price',0):.2f}")
        c2.metric("涨跌幅", f"{chg:+.2f}%")
        c3.metric("成交额", fa(stock.get("amount",0)))
        c4.metric("换手率", f"{stock.get('turnover_rate',0):.2f}%")
        c5.metric("市盈率", f"{stock.get('pe_ratio',0):.1f}")
        net = stock.get("main_net_inflow", 0)
        c6.metric("主力净流入", fa(net))

        st.divider()

        # 结果表格
        render_stock_table(results)
    elif "screener_results" in st.session_state:
        st.info("未找到符合条件的股票，请调整筛选条件")
