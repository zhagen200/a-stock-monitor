"""
Streamlit Web监控面板 v3
持仓管理 + 关注池 + 实时监控 + K线分析 + AI分析 + 回测数据
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
import yaml
import sqlite3
import json
from datetime import datetime
from collections import defaultdict

from src.data.collector import StockDataCollector
from src.analysis.technical import TechnicalAnalyzer
from src.web.portfolio import (
    get_holdings, add_holding, update_holding, sell_holding, delete_holding,
    get_watch_pool, add_to_watch, remove_from_watch,
)


st.set_page_config(page_title="A股智能监控", page_icon="📊", layout="wide")


@st.cache_resource
def init():
    config_path = Path(__file__).parent.parent.parent / "config" / "settings.yaml"
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}
    return config, StockDataCollector(), TechnicalAnalyzer()


config, collector, technical = init()

DB_PATH = Path(__file__).parent.parent.parent / "data" / "backtest.db"


def get_backtest_conn():
    if DB_PATH.exists():
        return sqlite3.connect(str(DB_PATH))
    return None


def plot_kline(df: pd.DataFrame, title: str):
    """绘制带技术指标的K线图"""
    fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.03,
                        row_heights=[0.6, 0.2, 0.2], subplot_titles=(title, "成交量", "MACD"))
    fig.add_trace(go.Candlestick(x=df.index, open=df["open"], high=df["high"],
                                  low=df["low"], close=df["close"], name="K线",
                                  increasing_line_color="red", decreasing_line_color="green"), row=1, col=1)
    for period, color in [(5, "yellow"), (10, "purple"), (20, "blue"), (60, "white")]:
        ma = df["close"].rolling(period).mean()
        fig.add_trace(go.Scatter(x=df.index, y=ma, name=f"MA{period}",
                                  line=dict(width=1, color=color)), row=1, col=1)
    ma20 = df["close"].rolling(20).mean()
    std20 = df["close"].rolling(20).std()
    fig.add_trace(go.Scatter(x=df.index, y=ma20 + 2*std20, name="上轨",
                              line=dict(width=1, color="gray", dash="dash")), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=ma20 - 2*std20, name="下轨",
                              line=dict(width=1, color="gray", dash="dash"),
                              fill="tonexty", fillcolor="rgba(128,128,128,0.1)"), row=1, col=1)
    colors = ["red" if c >= o else "green" for c, o in zip(df["close"], df["open"])]
    fig.add_trace(go.Bar(x=df.index, y=df["volume"], name="成交量", marker_color=colors), row=2, col=1)
    ema12 = df["close"].ewm(span=12).mean()
    ema26 = df["close"].ewm(span=26).mean()
    dif = ema12 - ema26
    dea = dif.ewm(span=9).mean()
    macd = (dif - dea) * 2
    fig.add_trace(go.Scatter(x=df.index, y=dif, name="DIF", line=dict(width=1, color="white")), row=3, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=dea, name="DEA", line=dict(width=1, color="yellow")), row=3, col=1)
    macd_colors = ["red" if v >= 0 else "green" for v in macd]
    fig.add_trace(go.Bar(x=df.index, y=macd, name="MACD", marker_color=macd_colors), row=3, col=1)
    fig.update_layout(template="plotly_dark", height=800, xaxis_rangeslider_visible=False,
                      showlegend=True, legend=dict(orientation="h", yanchor="bottom", y=1.02))
    return fig


def gauge_fig(value, title, vmin=-45, vmax=45):
    """仪表盘图"""
    color = "red" if value > 10 else "green" if value < -10 else "gray"
    fig = go.Figure(go.Indicator(
        mode="gauge+number", value=value,
        title={"text": title},
        gauge={
            "axis": {"range": [vmin, vmax]},
            "bar": {"color": color},
            "steps": [
                {"range": [vmin, vmin * 0.5], "color": "darkgreen"},
                {"range": [vmin * 0.5, -5], "color": "lightgreen"},
                {"range": [-5, 5], "color": "darkgray"},
                {"range": [5, vmax * 0.5], "color": "lightcoral"},
                {"range": [vmax * 0.5, vmax], "color": "darkred"},
            ],
        },
    ))
    fig.update_layout(template="plotly_dark", height=250, margin=dict(l=20, r=20, t=30, b=10))
    return fig


# ── 侧边栏导航 ─────────────────────────────────────
st.sidebar.title("📊 A股智能监控")
page = st.sidebar.radio("导航", [
    "📈 行情分析",
    "💼 持仓管理",
    "👁️ 关注池",
    "🤖 AI分析",
    "📊 回测数据",
])

# ===================================================
# 页面1: 行情分析
# ===================================================
if page == "📈 行情分析":
    st.title("📈 行情分析")

    holdings = get_holdings()
    watch_pool = get_watch_pool()
    all_stocks = []
    all_codes = set()

    for h in holdings:
        if h["code"] not in all_codes:
            all_stocks.append({"code": h["code"], "name": h["name"], "source": "持仓"})
            all_codes.add(h["code"])
    for w in watch_pool:
        if w["code"] not in all_codes:
            all_stocks.append({"code": w["code"], "name": w["name"], "source": "关注"})
            all_codes.add(w["code"])
    for s in config.get("watchlist", {}).get("stocks", []):
        if s["code"] not in all_codes:
            all_stocks.append({"code": s["code"], "name": s["name"], "source": "配置"})
            all_codes.add(s["code"])

    if not all_stocks:
        st.info("暂无监控股票，请先到「持仓管理」或「关注池」添加")
    else:
        col_sel, col_days = st.columns([3, 1])
        with col_sel:
            options = [f"{s['name']}({s['code']}) [{s['source']}]" for s in all_stocks]
            selected = st.selectbox("选择股票", options)
        with col_days:
            days = st.slider("K线天数", 30, 250, 120)

        idx = options.index(selected)
        stock_code = all_stocks[idx]["code"]
        stock_name = all_stocks[idx]["name"]

        with st.spinner(f"加载 {stock_name} 数据..."):
            quote = collector.get_realtime_quote(stock_code)
            kline = collector.get_kline(stock_code, days=days)
            fund_flow = collector.get_fund_flow(stock_code)

        if kline.empty:
            st.error("获取K线数据失败")
        else:
            if quote:
                c1, c2, c3, c4, c5 = st.columns(5)
                chg = quote.get("change_pct", 0)
                c1.metric("当前价", f"¥{quote['price']:.2f}", f"{chg:+.2f}%")
                c2.metric("成交量", f"{quote['volume']/10000:.0f}万手")
                c3.metric("成交额", f"{quote['amount']/100000000:.2f}亿")
                c4.metric("换手率", f"{quote.get('turnover_rate', 0):.2f}%")
                c5.metric("PE(动)", f"{quote.get('pe_ratio', 0):.1f}")

                for h in holdings:
                    if h["code"] == stock_code:
                        pnl = (quote["price"] - h["cost"]) * h["shares"]
                        pnl_pct = (quote["price"] / h["cost"] - 1) * 100
                        st.metric("持仓盈亏", f"¥{pnl:+,.2f}", f"{pnl_pct:+.2f}%",
                                  delta_color="inverse")
                        break

            st.plotly_chart(plot_kline(kline, f"{stock_name}({stock_code})"), use_container_width=True)

            tech_result = technical.analyze(kline, quote.get("price", 0) if quote else 0)
            col_l, col_r = st.columns(2)

            with col_l:
                st.subheader("📈 技术分析")
                score = tech_result.total_score
                st.plotly_chart(gauge_fig(score, "技术评分"), use_container_width=True)
                for sig in tech_result.signals:
                    icon = "🔴" if sig.signal == "bullish" else "🟢" if sig.signal == "bearish" else "⚪"
                    st.write(f"{icon} {sig.name}: {sig.description}")

            with col_r:
                st.subheader("💰 资金流向")
                if fund_flow:
                    flow_data = {"类型": ["主力", "超大单", "大单", "中单", "小单"],
                                 "净流入(万)": [fund_flow.get(k, 0)/10000 for k in
                                               ["main_net_inflow", "super_large_net", "large_net", "medium_net", "small_net"]]}
                    df_flow = pd.DataFrame(flow_data)
                    colors = ["red" if v > 0 else "green" for v in df_flow["净流入(万)"]]
                    fig_flow = go.Figure(go.Bar(x=df_flow["类型"], y=df_flow["净流入(万)"], marker_color=colors))
                    fig_flow.update_layout(template="plotly_dark", height=300, title="今日资金流向")
                    st.plotly_chart(fig_flow, use_container_width=True)
                else:
                    st.info("暂无资金流向数据")

                st.write("**关键价位:**")
                st.write(f"止损: ¥{tech_result.stop_loss:.2f}")
                st.write(f"止盈1: ¥{tech_result.take_profit_1:.2f}")
                st.write(f"止盈2: ¥{tech_result.take_profit_2:.2f}")

# ===================================================
# 页面2: 持仓管理
# ===================================================
elif page == "💼 持仓管理":
    st.title("💼 持仓管理")

    holdings = get_holdings()

    with st.expander("➕ 添加/更新持仓", expanded=False):
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            new_code = st.text_input("股票代码", placeholder="002195")
        with col2:
            new_name = st.text_input("股票名称", placeholder="岩山科技")
        with col3:
            new_cost = st.number_input("持仓成本", min_value=0.0, step=0.01)
        with col4:
            new_shares = st.number_input("持仓数量", min_value=0, step=100)
        if st.button("✅ 添加/更新持仓"):
            if new_code and new_name and new_cost > 0 and new_shares > 0:
                add_holding(new_code, new_name, new_cost, new_shares)
                st.success(f"已添加 {new_name}({new_code})")
                st.rerun()
            else:
                st.warning("请填写完整信息")

    if not holdings:
        st.info("暂无持仓记录，请添加")
    else:
        for h in holdings:
            with st.container():
                col_info, col_edit, col_action = st.columns([4, 3, 2])

                with col_info:
                    st.write(f"**{h['name']}** ({h['code']})")
                    st.caption(f"成本: ¥{h['cost']:.2f}  |  数量: {h['shares']}股  |  市值: ¥{h['cost']*h['shares']:,.2f}")

                with col_edit:
                    e1, e2 = st.columns(2)
                    with e1:
                        new_c = st.number_input("新成本", value=h["cost"], step=0.01, key=f"cost_{h['code']}")
                    with e2:
                        new_s = st.number_input("新数量", value=h["shares"], step=100, key=f"shares_{h['code']}")
                    if st.button("📝 更新", key=f"update_{h['code']}"):
                        update_holding(h["code"], new_c, new_s)
                        st.success("已更新")
                        st.rerun()

                with col_action:
                    sell_price = st.number_input("卖出价", value=0.0, step=0.01, key=f"sell_{h['code']}")
                    c1, c2 = st.columns(2)
                    with c1:
                        if st.button("📤 全部卖出", key=f"sellall_{h['code']}"):
                            sell_holding(h["code"], sell_price, 0)
                            st.success(f"已卖出 {h['name']}")
                            st.rerun()
                    with c2:
                        if st.button("🗑️ 删除", key=f"del_{h['code']}"):
                            delete_holding(h["code"])
                            st.success(f"已删除 {h['name']}")
                            st.rerun()

                st.divider()

# ===================================================
# 页面3: 关注池
# ===================================================
elif page == "👁️ 关注池":
    st.title("👁️ 关注池管理")

    pool = get_watch_pool()

    with st.expander("➕ 添加关注股票", expanded=False):
        col1, col2, col3 = st.columns(3)
        with col1:
            w_code = st.text_input("股票代码", placeholder="600030", key="w_code")
        with col2:
            w_name = st.text_input("股票名称", placeholder="中信证券", key="w_name")
        with col3:
            w_reason = st.text_input("关注原因", placeholder="短线机会", key="w_reason")
        if st.button("✅ 添加关注"):
            if w_code and w_name:
                add_to_watch(w_code, w_name, "manual", w_reason)
                st.success(f"已关注 {w_name}({w_code})")
                st.rerun()

    if not pool:
        st.info("关注池为空，请添加或等待每日智能推荐")
    else:
        for w in pool:
            col_info, col_action = st.columns([5, 1])
            with col_info:
                source_emoji = "🤖" if w.get("source") == "auto_pick" else "👤"
                st.write(f"{source_emoji} **{w['name']}** ({w['code']})")
                st.caption(f"来源: {w.get('source', '手动')}  |  原因: {w.get('reason', '-')}  |  添加: {w.get('added_at', '-')[:10]}")
            with col_action:
                if st.button("🗑️ 移除", key=f"remove_{w['code']}"):
                    remove_from_watch(w["code"])
                    st.success(f"已移除 {w['name']}")
                    st.rerun()
            st.divider()

    st.subheader("📊 监控池汇总")
    holdings = get_holdings()
    hold_codes = {h["code"] for h in holdings}
    pool_codes = {w["code"] for w in pool}
    all_codes = hold_codes | pool_codes
    st.write(f"持仓: {len(hold_codes)}只  |  关注: {len(pool_codes)}只  |  总计监控: {len(all_codes)}只")


# ===================================================
# 页面4: AI 分析
# ===================================================
elif page == "🤖 AI分析":
    st.title("🤖 AI 量化分析")

    conn = get_backtest_conn()
    if conn is None:
        st.warning("回测数据库不存在，尚无AI分析数据")
    else:
        cur = conn.cursor()

        # ── 概览指标 ──
        cur.execute("SELECT COUNT(*) FROM signals")
        total_signals = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM signals WHERE ai_analysis IS NOT NULL AND ai_analysis != ''")
        ai_signals = cur.fetchone()[0]
        cur.execute("SELECT COUNT(DISTINCT code) FROM signals")
        stock_count = cur.fetchone()[0]
        cur.execute("SELECT ROUND(AVG(ai_confidence), 1) FROM signals WHERE ai_confidence != 0")
        avg_conf_raw = cur.fetchone()[0]
        avg_conf = avg_conf_raw if avg_conf_raw else 0

        st.subheader("📊 概览")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("总信号数", total_signals)
        m2.metric("AI分析数", ai_signals, f"{ai_signals/total_signals*100:.0f}%" if total_signals else "0%")
        m3.metric("监控股票数", stock_count)
        m4.metric("平均置信度", f"{avg_conf:.1f}")

        # ── 按股票展示 ──
        st.subheader("📋 各股票最新AI分析")

        cur.execute("""
            SELECT code, name, COUNT(*) as total,
                   SUM(CASE WHEN ai_analysis != '' THEN 1 ELSE 0 END) as ai_cnt
            FROM signals GROUP BY code ORDER BY total DESC
        """)
        stock_stats = cur.fetchall()

        for s in stock_stats:
            code, name, total, ai_cnt = s
            with st.expander(f"{name} ({code}) — 信号 {total}条 / AI分析 {ai_cnt}条", expanded=False):
                # 最新AI分析
                cur.execute("""
                    SELECT timestamp, action, score, ai_analysis, ai_confidence
                    FROM signals
                    WHERE code = ? AND ai_analysis IS NOT NULL AND ai_analysis != ''
                    ORDER BY id DESC LIMIT 1
                """, (code,))
                row = cur.fetchone()
                if row:
                    ts, action, score, analysis, confidence = row
                    st.caption(f"分析时间: {ts[:19]}  |  信号: {action}  |  评分: {score:.1f}  |  置信度: {confidence:.1f}")
                    st.markdown(analysis)
                else:
                    st.info("暂无AI分析数据")

                # 历史评分趋势 (最近20条)
                cur.execute("""
                    SELECT timestamp, score, ai_confidence
                    FROM signals WHERE code = ?
                    ORDER BY id DESC LIMIT 20
                """, (code,))
                hist = cur.fetchall()
                if len(hist) >= 3:
                    hist = list(reversed(hist))
                    fig = go.Figure()
                    times = [r[0][11:19] for r in hist]
                    scores = [r[1] for r in hist]
                    confs = [r[2] for r in hist]
                    fig.add_trace(go.Scatter(x=times, y=scores, name="评分", mode="lines+markers",
                                              line=dict(color="yellow", width=2)))
                    fig.add_trace(go.Scatter(x=times, y=confs, name="置信度", mode="lines+markers",
                                              line=dict(color="cyan", width=1, dash="dot")))
                    fig.update_layout(template="plotly_dark", height=250,
                                      title=f"{name} 最近{len(hist)}次信号趋势")
                    st.plotly_chart(fig, use_container_width=True)

        conn.close()

# ===================================================
# 页面5: 回测数据
# ===================================================
elif page == "📊 回测数据":
    st.title("📊 回测数据与策略进化")

    conn = get_backtest_conn()
    if conn is None:
        st.warning("回测数据库不存在")
    else:
        cur = conn.cursor()

        tab1, tab2, tab3, tab4 = st.tabs(["📈 信号统计", "📊 回测结果", "🧬 策略版本", "📜 进化日志"])

        # ── Tab1: 信号统计 ──
        with tab1:
            st.subheader("信号分布统计")

            col_left, col_right = st.columns([1, 2])

            with col_left:
                # 按操作类型分布
                cur.execute("SELECT action, COUNT(*) FROM signals GROUP BY action ORDER BY COUNT(*) DESC")
                action_data = cur.fetchall()
                if action_data:
                    fig = go.Figure(data=[go.Pie(
                        labels=[r[0] for r in action_data],
                        values=[r[1] for r in action_data],
                        hole=0.4,
                        marker=dict(colors=["gray", "red", "green", "orange"]),
                    )])
                    fig.update_layout(template="plotly_dark", height=350, title="信号类型分布")
                    st.plotly_chart(fig, use_container_width=True)

                # 信号评分分布
                cur.execute("SELECT score FROM signals")
                all_scores = [r[0] for r in cur.fetchall()]
                if all_scores:
                    bins = {"<-20": 0, "-20~-10": 0, "-10~0": 0, "0~10": 0, "10~20": 0, ">20": 0}
                    for s in all_scores:
                        if s < -20: bins["<-20"] += 1
                        elif s < -10: bins["-20~-10"] += 1
                        elif s < 0: bins["-10~0"] += 1
                        elif s < 10: bins["0~10"] += 1
                        elif s < 20: bins["10~20"] += 1
                        else: bins[">20"] += 1
                    fig = go.Figure([go.Bar(x=list(bins.keys()), y=list(bins.values()),
                                             marker_color="lightblue")])
                    fig.update_layout(template="plotly_dark", height=300, title="评分分布")
                    st.plotly_chart(fig, use_container_width=True)

            with col_right:
                # 按股票信号数量
                cur.execute("""
                    SELECT name, code, COUNT(*) as cnt
                    FROM signals GROUP BY code ORDER BY cnt DESC
                """)
                stock_counts = cur.fetchall()
                if stock_counts:
                    fig = go.Figure([go.Bar(
                        x=[f"{r[0]}({r[1]})" for r in stock_counts],
                        y=[r[2] for r in stock_counts],
                        marker_color="orange",
                    )])
                    fig.update_layout(template="plotly_dark", height=400,
                                      title="各股票信号数量", xaxis_tickangle=-30)
                    st.plotly_chart(fig, use_container_width=True)

                # 最新信号表
                cur.execute("""
                    SELECT timestamp, code, name, action, score, ai_confidence
                    FROM signals ORDER BY id DESC LIMIT 10
                """)
                recent = cur.fetchall()
                if recent:
                    st.subheader("最近10条信号")
                    df_recent = pd.DataFrame(recent, columns=["时间", "代码", "名称", "操作", "评分", "置信度"])
                    df_recent["时间"] = df_recent["时间"].str[11:19]
                    st.dataframe(df_recent, use_container_width=True, hide_index=True)

        # ── Tab2: 回测结果 ──
        with tab2:
            cur.execute("SELECT COUNT(*) FROM backtest_results")
            bt_count = cur.fetchone()[0]

            if bt_count == 0:
                st.info("暂无回测结果数据。系统持续运行后，每日收盘会自动生成回测记录。")

                # 即使没有回测结果，也展示信号准确性的估算
                st.subheader("📊 当前信号准确性估算")

                # 检查是否有实际收益回填
                cur.execute("""
                    SELECT COUNT(*) FROM signals
                    WHERE actual_return_1d != 0 OR actual_return_3d != 0
                """)
                filled = cur.fetchone()[0]
                if filled > 0:
                    cur.execute("""
                        SELECT ROUND(AVG(actual_return_1d), 2),
                               ROUND(AVG(actual_return_3d), 2),
                               ROUND(AVG(actual_return_5d), 2)
                        FROM signals WHERE actual_return_1d != 0
                    """)
                    avg_ret = cur.fetchone()
                    c1, c2, c3 = st.columns(3)
                    c1.metric("平均1日收益", f"{avg_ret[0]:+.2f}%")
                    c2.metric("平均3日收益", f"{avg_ret[1]:+.2f}%")
                    c3.metric("平均5日收益", f"{avg_ret[2]:+.2f}%")

                    cur.execute("""
                        SELECT action, ROUND(AVG(actual_return_1d), 2), COUNT(*)
                        FROM signals WHERE actual_return_1d != 0
                        GROUP BY action
                    """)
                    by_action = cur.fetchall()
                    st.write("按信号类型的平均收益:")
                    for a, r, c in by_action:
                        emoji = "✅" if r > 0 else "❌" if r < 0 else "➖"
                        st.write(f"{emoji} {a}: {r:+.2f}% ({c}次)")
                else:
                    st.info("尚无回填的实际收益数据，信号准确性将在系统运行一段时间后自动评估。")
            else:
                cur.execute("SELECT * FROM backtest_results ORDER BY id DESC LIMIT 10")
                bt_rows = cur.fetchall()
                bt_cols = [d[0] for d in cur.description]
                st.dataframe(pd.DataFrame(bt_rows, columns=bt_cols), use_container_width=True, hide_index=True)

        # ── Tab3: 策略版本 ──
        with tab3:
            cur.execute("SELECT COUNT(*) FROM strategy_versions")
            sv_count = cur.fetchone()[0]

            if sv_count == 0:
                st.info("暂无策略版本记录。策略自进化尚需积累更多回测数据后触发。")
                st.markdown("""
                **策略自进化流程说明：**
                1. 系统每交易日生成信号并记录
                2. 信号实际收益自动回填后，系统评估策略准确性
                3. 当积累足够数据（建议50+信号），自动触发策略参数优化
                4. 优化结果生成新的策略版本，记录参数变更和效果对比

                **当前策略默认参数：**
                | 参数 | 值 |
                |------|-----|
                | 技术面权重 | 0.40 |
                | 资金面权重 | 0.20 |
                | 消息面权重 | 0.25 |
                | 基本面权重 | 0.15 |
                | 买入阈值 | 30 |
                | 卖出阈值 | -30 |
                | 强烈买入阈值 | 60 |
                | 强烈卖出阈值 | -60 |
                """)
            else:
                cur.execute("SELECT * FROM strategy_versions ORDER BY version DESC")
                sv_rows = cur.fetchall()
                for r in sv_rows:
                    sv_dict = dict(zip([d[0] for d in cur.description], r))
                    with st.expander(f"v{sv_dict['version']} — {sv_dict.get('reason', '-')}", expanded=True):
                        st.json(json.loads(sv_dict.get("params", "{}")))
                        m1, m2 = st.columns(2)
                        m1.metric("准确率", f"{sv_dict.get('accuracy', 0):.1%}")
                        m2.metric("夏普比", f"{sv_dict.get('sharpe_ratio', 0):.2f}")

        # ── Tab4: 进化日志 ──
        with tab4:
            cur.execute("SELECT COUNT(*) FROM evolution_log")
            ev_count = cur.fetchone()[0]

            if ev_count == 0:
                st.info("暂无进化日志。策略自进化将在积累足够回测数据后自动触发。")
                st.markdown("""
                **进化触发条件：**
                - 回测记录数 ≥ 50（当前可手动触发）
                - 每周日自动检查进化条件
                - 连续3日信号准确率 < 40% 自动触发紧急进化

                **进化机制：**
                1. 分析近期回测数据中表现最好的信号参数组合
                2. 使用AI分析信号归因，识别有效因子
                3. 动态调整各维度权重
                4. 生成新策略版本并对比前后效果
                """)
            else:
                cur.execute("SELECT * FROM evolution_log ORDER BY version DESC LIMIT 20")
                ev_rows = cur.fetchall()
                for r in ev_rows:
                    ev_dict = dict(zip([d[0] for d in cur.description], r))
                    with st.expander(f"v{ev_dict['version']} — {ev_dict['timestamp'][:19]}", expanded=True):
                        c1, c2 = st.columns(2)
                        with c1:
                            st.metric("进化前准确率", f"{ev_dict.get('accuracy_before', 0):.1%}")
                        with c2:
                            st.metric("进化后准确率", f"{ev_dict.get('accuracy_after', 0):.1%}")
                        if ev_dict.get("ai_reasoning"):
                            st.subheader("AI推理")
                            st.write(ev_dict["ai_reasoning"])
                        if ev_dict.get("key_changes"):
                            st.subheader("关键变更")
                            st.json(json.loads(ev_dict["key_changes"]) if isinstance(ev_dict["key_changes"], str) else ev_dict["key_changes"])

        conn.close()
