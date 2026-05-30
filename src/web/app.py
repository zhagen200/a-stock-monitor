"""
Streamlit Web监控面板 v5 — A股量化交易系统
侧边栏导航 + 6页面：自选股/大盘行情/选股筛选/风险监控/信号中心/回测数据
"""

import sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import streamlit as st
import plotly.graph_objects as go
import pandas as pd
import numpy as np
import sqlite3
from datetime import datetime, timedelta

from src.core.config import settings
from src.data.manager import DataManager
from src.engine.live import LiveEngine
from src.data.store import SignalStore, TradeStore, PositionStore, DB_PATH
from src.analysis.technical import TechnicalAnalyzer
from src.web.styles import GLOBAL_CSS, ACTION_LABELS, ACTION_COLORS, ACTION_EMOJI
from src.web.charts import plot_kline, gauge_fig, fund_flow_chart, score_bar_chart
from src.web.helpers import fv, fa, get_extra

st.set_page_config(page_title="A股量化交易系统", page_icon="📊", layout="wide", initial_sidebar_state="expanded")

# ── 初始化 ──
if "engine" not in st.session_state:
    settings.load()
    st.session_state.engine = LiveEngine()
if "detail_code" not in st.session_state:
    st.session_state.detail_code = ""

engine = st.session_state.engine
data_manager = engine.data_manager
signal_store = SignalStore()
trade_store = TradeStore()
position_store = PositionStore()
technical = TechnicalAnalyzer()


def inject_css():
    st.markdown(GLOBAL_CSS, unsafe_allow_html=True)


def indices_bar():
    """顶部大盘指数条 - 使用st.metric保持高度一致"""
    indices = data_manager.get_market_index()
    if not indices:
        return
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


def render_signal_stats(cur):
    """渲染信号统计"""
    cur.execute("SELECT COUNT(*) FROM signals")
    total = cur.fetchone()[0]
    cur.execute("SELECT COUNT(DISTINCT code) FROM signals")
    stock_count = cur.fetchone()[0]

    m1, m2 = st.columns(2)
    m1.metric("总信号数", total)
    m2.metric("监控股票数", stock_count)

    cur.execute("SELECT action, COUNT(*) FROM signals GROUP BY action ORDER BY COUNT(*) DESC")
    action_data = cur.fetchall()
    if action_data:
        fig = go.Figure(data=[go.Pie(
            labels=[r[0] for r in action_data],
            values=[r[1] for r in action_data],
            hole=0.4,
            marker=dict(colors=["#ef4444", "#f97316", "#6b7280", "#22c55e", "#10b981"]),
        )])
        fig.update_layout(template="plotly_dark", height=300, title="信号类型分布")
        st.plotly_chart(fig, use_container_width=True)

    cur.execute("SELECT timestamp, code, name, action, score, confidence FROM signals ORDER BY id DESC LIMIT 10")
    recent = cur.fetchall()
    if recent:
        st.subheader("最近10条信号")
        df = pd.DataFrame(recent, columns=["时间", "代码", "名称", "操作", "评分", "置信度"])
        df["时间"] = df["时间"].str[:19]
        st.dataframe(df, use_container_width=True, hide_index=True)


# ══════════════════════════════════════════════
# 侧边栏
# ══════════════════════════════════════════════
with st.sidebar:
    st.markdown(
        '<div style="display:flex;align-items:center;gap:0.5rem;margin-bottom:0.2rem">'
        '<span style="font-size:1.5rem">📊</span>'
        '<span style="font-size:1.1rem;font-weight:700;color:#f1f5f9">A股量化系统</span>'
        '</div>',
        unsafe_allow_html=True
    )
    st.caption(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    st.divider()

    page = st.radio("导航", [
        "🏠 自选股",
        "📈 大盘行情",
        "🔍 选股筛选",
        "⚠️ 风险监控",
        "📡 信号中心",
        "📊 回测数据",
    ], label_visibility="collapsed")

    st.divider()
    if st.button("🔄 刷新数据", use_container_width=True):
        st.rerun()


# ══════════════════════════════════════════════
# 📈 大盘行情
# ══════════════════════════════════════════════
if page == "📈 大盘行情":
    inject_css()
    try:
        from src.web.views.market import render_market_page
        render_market_page(data_manager)
    except Exception as e:
        st.error(f"大盘行情页面错误: {e}")
        import traceback; st.code(traceback.format_exc())

# ══════════════════════════════════════════════
# 🔍 选股筛选
# ══════════════════════════════════════════════
elif page == "🔍 选股筛选":
    inject_css()
    try:
        from src.web.views.screener import render_screener_page
        render_screener_page()
    except Exception as e:
        st.error(f"选股筛选页面错误: {e}")
        import traceback; st.code(traceback.format_exc())

# ══════════════════════════════════════════════
# ⚠️ 风险监控
# ══════════════════════════════════════════════
elif page == "⚠️ 风险监控":
    inject_css()
    try:
        from src.web.views.risk import render_risk_page
        render_risk_page(data_manager, position_store, signal_store, trade_store, settings)
    except Exception as e:
        st.error(f"风险监控页面错误: {e}")
        import traceback; st.code(traceback.format_exc())

# ══════════════════════════════════════════════
# 📡 信号中心
# ══════════════════════════════════════════════
elif page == "📡 信号中心":
    inject_css()
    st.markdown("## 📡 信号中心")

    wl = settings.get_watchlist()
    if wl:
        st.markdown("### 快速扫描")
        cols = st.columns(min(len(wl), 4))
        for i, s in enumerate(wl[:8]):
            with cols[i % 4]:
                sd = st.session_state.get(f"signal_{s['code']}")
                with st.container(border=True):
                    st.markdown(f"**{s['name']}** `{s['code']}`")
                    if sd:
                        st.markdown(
                            f'<span class="sb sb-{sd.action}">{ACTION_EMOJI.get(sd.action,"")} {ACTION_LABELS.get(sd.action,sd.action)}</span>'
                            f' 评分 {sd.score:.0f} 置信 {sd.confidence:.0f}%',
                            unsafe_allow_html=True
                        )
                    if st.button("扫描", key=f"ss_{s['code']}", use_container_width=True):
                        sig = engine.scan_stock(s)
                        if sig:
                            st.session_state[f"signal_{s['code']}"] = sig
                            st.rerun()

    st.divider()
    st.markdown("### 历史信号")
    signals = signal_store.get_signals(limit=50)
    if signals:
        for sig in signals[:15]:
            action = sig.get("action", "hold")
            color = ACTION_COLORS.get(action, "#6b7280")
            emoji = ACTION_EMOJI.get(action, "")
            label = ACTION_LABELS.get(action, action)
            ts = sig.get("timestamp", "")[:16]
            st.markdown(
                f'<div style="display:flex;align-items:center;gap:0.5rem;padding:0.3rem 0;border-bottom:1px solid #1a1f2e;font-size:0.82rem">'
                f'<span style="color:#64748b;min-width:130px">{ts}</span>'
                f'<span style="color:#f1f5f9;min-width:80px;font-weight:500">{sig.get("name","")}</span>'
                f'<span style="background:{color}22;color:{color};padding:0.1rem 0.4rem;border-radius:999px;font-size:0.72rem;font-weight:600">{emoji} {label}</span>'
                f'<span style="color:#94a3b8">评分 {sig.get("score",0):.0f}</span>'
                f'<span style="color:#94a3b8">置信 {sig.get("confidence",0):.0f}%</span>'
                f'<span style="color:#f1f5f9">¥{sig.get("price",0):.2f}</span>'
                f'</div>', unsafe_allow_html=True
            )
    else:
        st.info("暂无信号记录")

# ══════════════════════════════════════════════
# 📊 回测数据
# ══════════════════════════════════════════════
elif page == "📊 回测数据":
    inject_css()
    st.markdown("## 📊 回测数据与策略进化")

    try:
        if DB_PATH.exists():
            conn = sqlite3.connect(str(DB_PATH))
        else:
            st.warning("数据库不存在，系统运行后将自动生成")
            conn = None

        if conn:
            cur = conn.cursor()
            cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [r[0] for r in cur.fetchall()]

            tab_names = []
            if "signals" in tables: tab_names.append("📈 信号统计")
            if "backtest_results" in tables: tab_names.append("📊 回测结果")
            if "strategy_versions" in tables: tab_names.append("🧬 策略版本")
            if "evolution_log" in tables: tab_names.append("📜 进化日志")

            if not tab_names:
                st.info("数据库为空，等待系统运行后生成数据")
            else:
                tabs = st.tabs(tab_names)
                tab_idx = 0
                if "signals" in tables:
                    with tabs[tab_idx]:
                        render_signal_stats(cur)
                    tab_idx += 1
                if "backtest_results" in tables:
                    with tabs[tab_idx]:
                        cur.execute("SELECT * FROM backtest_results ORDER BY id DESC LIMIT 10")
                        rows = cur.fetchall()
                        if rows:
                            df = pd.DataFrame(rows, columns=[d[0] for d in cur.description])
                            st.dataframe(df, use_container_width=True, hide_index=True)
                        else:
                            st.info("暂无回测结果")
                    tab_idx += 1
                if "strategy_versions" in tables:
                    with tabs[tab_idx]:
                        cur.execute("SELECT * FROM strategy_versions ORDER BY version DESC")
                        rows = cur.fetchall()
                        if rows:
                            for r in rows:
                                sv = dict(zip([d[0] for d in cur.description], r))
                                with st.expander(f"v{sv.get('version','-')} — {sv.get('reason','-')}", expanded=True):
                                    import json as _json
                                    try: st.json(_json.loads(sv.get("params", "{}")))
                                    except: st.write(sv.get("params", ""))
                                    m1, m2 = st.columns(2)
                                    m1.metric("准确率", f"{sv.get('accuracy',0):.1%}")
                                    m2.metric("夏普比", f"{sv.get('sharpe_ratio',0):.2f}")
                        else:
                            st.info("暂无策略版本记录")
                    tab_idx += 1
                if "evolution_log" in tables:
                    with tabs[tab_idx]:
                        cur.execute("SELECT * FROM evolution_log ORDER BY version DESC LIMIT 20")
                        rows = cur.fetchall()
                        if rows:
                            for r in rows:
                                ev = dict(zip([d[0] for d in cur.description], r))
                                with st.expander(f"v{ev.get('version','-')} — {ev.get('timestamp','')[:19]}", expanded=True):
                                    c1, c2 = st.columns(2)
                                    c1.metric("进化前", f"{ev.get('accuracy_before',0):.1%}")
                                    c2.metric("进化后", f"{ev.get('accuracy_after',0):.1%}")
                                    if ev.get("ai_reasoning"):
                                        st.markdown("**AI推理**")
                                        st.write(ev["ai_reasoning"])
                        else:
                            st.info("暂无进化日志")
            conn.close()
    except Exception as e:
        st.error(f"回测数据页面错误: {e}")
        import traceback; st.code(traceback.format_exc())

# ══════════════════════════════════════════════
# 🏠 自选股 (默认页面)
# ══════════════════════════════════════════════
elif page == "🏠 自选股":
    inject_css()

    # 大盘指数
    indices_bar()

    # 如果有选中的股票，显示详情
    if st.session_state.detail_code:
        code = st.session_state.detail_code
        wl = settings.get_watchlist()
        info = next((s for s in wl if s["code"] == code), None)
        name = info["name"] if info else code

        if st.button("← 返回自选股"):
            st.session_state.detail_code = ""
            st.rerun()

        with st.spinner(f"加载 {name} 数据..."):
            quote = data_manager.get_realtime_quote(code)
            kline = data_manager.get_kline(code, days=250)
            fund = data_manager.get_fund_flow(code)
            news = data_manager.get_stock_news(code, limit=10)

        # 顶部标题
        if quote:
            chg = quote.get("change_pct", 0)
            color = "#ef4444" if chg >= 0 else "#22c55e"
            ar = "▲" if chg >= 0 else "▼"
            st.markdown(
                f'### {name} `{code}` ¥{quote["price"]:.2f} '
                f'<span style="color:{color}">{ar} {abs(chg):.2f}%</span>',
                unsafe_allow_html=True
            )

            # 行情卡片
            c1, c2, c3, c4, c5, c6, c7, c8 = st.columns(8)
            c1.metric("今开", f"¥{quote.get('open',0):.2f}")
            c2.metric("最高", f"¥{quote.get('high',0):.2f}")
            c3.metric("最低", f"¥{quote.get('low',0):.2f}")
            c4.metric("昨收", f"¥{quote.get('pre_close',0):.2f}")
            c5.metric("成交量", fv(quote.get("volume",0)))
            c6.metric("成交额", fa(quote.get("amount",0)))
            c7.metric("换手率", f"{quote.get('turnover_rate',0):.2f}%")
            c8.metric("市盈率", f"{quote.get('pe_ratio',0):.1f}")

        # K线
        days = st.select_slider("K线周期", [30, 60, 90, 120, 250], value=120, key="kd")
        kv = kline.iloc[-days:] if not kline.empty and len(kline) > days else kline
        if not kv.empty:
            st.plotly_chart(plot_kline(kv, f"{name}({code})"), use_container_width=True)

        tech_result = technical.analyze(kline, quote.get("price", 0) if quote else 0)

        # 详情Tabs
        tk, tt, tf, tn = st.tabs(["📊 盘口", "📈 技术面", "💰 资金流", "📰 新闻"])

        with tk:
            c1, c2 = st.columns(2)
            with c1:
                st.markdown("**卖五档**")
                asks = quote.get("asks", []) if quote else []
                for a in sorted(asks, key=lambda x: x.get("price", 0), reverse=True):
                    if a.get("price", 0) == 0: continue
                    st.markdown(f'<div style="color:#22c55e;font-size:0.82rem">{a.get("volume",0):.0f}手 ¥{a["price"]:.2f}</div>', unsafe_allow_html=True)
                st.markdown(f'<div style="border-top:1px solid #3b82f6;padding:0.3rem 0;text-align:center;font-weight:700;color:#3b82f6">¥{quote.get("price",0):.2f}</div>', unsafe_allow_html=True)
                st.markdown("**买五档**")
                bids = quote.get("bids", []) if quote else []
                for b in sorted(bids, key=lambda x: x.get("price", 0), reverse=True):
                    if b.get("price", 0) == 0: continue
                    st.markdown(f'<div style="color:#ef4444;font-size:0.82rem">{b.get("volume",0):.0f}手 ¥{b["price"]:.2f}</div>', unsafe_allow_html=True)
            with c2:
                st.markdown("**阶段表现**")
                if not kv.empty and len(kv) >= 2:
                    now_p = kv["close"].iloc[-1]
                    for label, n in {"5日": 5, "10日": 10, "20日": 20, "60日": 60}.items():
                        if len(kv) >= n:
                            ret = (now_p / kv["close"].iloc[-n] - 1) * 100
                            color = "#ef4444" if ret >= 0 else "#22c55e"
                            st.markdown(f'<div style="display:flex;justify-content:space-between;font-size:0.82rem"><span style="color:#94a3b8">{label}</span><span style="color:{color};font-weight:600">{ret:+.2f}%</span></div>', unsafe_allow_html=True)

        with tt:
            c1, c2 = st.columns([1, 1.5])
            with c1:
                st.plotly_chart(gauge_fig(tech_result.total_score, f"综合 {tech_result.total_score:.0f}"), use_container_width=True)
                scores = {"趋势": tech_result.trend_score, "动量": tech_result.momentum_score, "量能": tech_result.volume_score, "形态": tech_result.pattern_score}
                st.plotly_chart(score_bar_chart(scores), use_container_width=True)
            with c2:
                st.markdown("### 🎯 关键价位")
                mc1, mc2, mc3 = st.columns(3)
                mc1.metric("止损", f"¥{tech_result.stop_loss:.2f}" if tech_result.stop_loss else "—")
                mc2.metric("止盈1", f"¥{tech_result.take_profit_1:.2f}" if tech_result.take_profit_1 else "—")
                mc3.metric("止盈2", f"¥{tech_result.take_profit_2:.2f}" if tech_result.take_profit_2 else "—")

                if tech_result.support_levels or tech_result.resistance_levels:
                    sc1, sc2 = st.columns(2)
                    with sc1:
                        st.markdown("⬆ **支撑**")
                        for lv in tech_result.support_levels[:3]: st.write(f"¥{lv:.2f}")
                    with sc2:
                        st.markdown("⬇ **阻力**")
                        for lv in tech_result.resistance_levels[:3]: st.write(f"¥{lv:.2f}")

                st.markdown("### 技术信号")
                for sig in tech_result.signals:
                    icon = "🟢" if sig.signal == "bullish" else "🔴" if sig.signal == "bearish" else "⚪"
                    st.markdown(f'{icon} **{sig.name}**: {sig.description}')

        with tf:
            if fund:
                st.plotly_chart(fund_flow_chart(fund), use_container_width=True)
                mni = fund.get("main_net_inflow", 0)
                if mni:
                    nc = "#ef4444" if mni >= 0 else "#22c55e"
                    st.markdown(f'<div style="text-align:center;color:#94a3b8"><span style="color:{nc};font-weight:600">{"主力净流入" if mni >= 0 else "主力净流出"}</span>: {abs(mni)/1e4:.0f}万元 | 净占比: {fund.get("main_net_pct",0):.2f}%</div>', unsafe_allow_html=True)
            else:
                st.info("暂无资金流向数据")

        with tn:
            if news:
                for item in news:
                    t = item.get("title", "")
                    dt = item.get("date", "") or item.get("time", "")
                    url = item.get("url", "")
                    st.markdown(f'- [{t}]({url}) <span style="color:#64748b;font-size:0.72rem">{dt}</span>', unsafe_allow_html=True)
            else:
                st.info("暂无相关新闻")

        if st.button("← 返回自选股", key="back_bot"):
            st.session_state.detail_code = ""
            st.rerun()

    else:
        # ── 自选股列表 ──
        wl = settings.get_watchlist()
        if not wl:
            st.info("暂无自选股，请在 config/settings.yaml 中添加")
        else:
            extra = get_extra(data_manager, [s["code"] for s in wl])

            # 持仓汇总
            total_cost = 0
            total_value = 0
            for s in wl:
                if s.get("cost") and s.get("shares"):
                    q = extra.get(s["code"], {})
                    cp = q.get("price", s["cost"])
                    total_cost += s["cost"] * s["shares"]
                    total_value += cp * s["shares"]

            if total_cost > 0:
                pnl = total_value - total_cost
                pnl_pct = (total_value / total_cost - 1) * 100
                pnl_color = "#ef4444" if pnl >= 0 else "#22c55e"
                c1, c2, c3 = st.columns(3)
                c1.metric("持仓成本", f"¥{total_cost:,.0f}")
                c2.metric("持仓市值", f"¥{total_value:,.0f}")
                c3.metric("持仓盈亏", f"¥{pnl:+,.0f}", f"{pnl_pct:+.2f}%")

            # 自选股HTML表格
            st.markdown("### 自选股实时行情")
            table_html = '<table class="data-table"><tr>'
            for h in ["#","名称","现价","涨跌幅","成交量","成交额","换手率","主力净流入"]:
                table_html += f'<th>{h}</th>'
            table_html += '</tr>'

            for i, s in enumerate(wl):
                q = extra.get(s["code"], {})
                chg = q.get("change_pct", 0)
                color = "#ef4444" if chg >= 0 else "#22c55e"
                ar = "▲" if chg >= 0 else "▼"
                price_str = f"¥{q.get('price',0):.2f}" if q.get("price") else "—"
                net = q.get("main_net_inflow", 0)
                nc = "#ef4444" if net >= 0 else "#22c55e"
                net_str = f"{net/1e4:.0f}万" if net else "—"
                tr = q.get("turnover_rate", 0)
                tr_str = f"{tr:.2f}%" if tr else "—"

                table_html += f'<tr>'
                table_html += f'<td style="color:#64748b">{i+1}</td>'
                table_html += f'<td><span style="color:#60a5fa;font-weight:500">{s["name"]}</span> <span style="color:#64748b;font-size:0.7rem">{s["code"]}</span></td>'
                table_html += f'<td style="color:#f1f5f9">{price_str}</td>'
                table_html += f'<td style="color:{color};font-weight:600">{ar} {abs(chg):.2f}%</td>'
                table_html += f'<td style="color:#e2e8f0">{fv(q.get("volume",0))}</td>'
                table_html += f'<td style="color:#e2e8f0">{fa(q.get("amount",0))}</td>'
                table_html += f'<td style="color:#e2e8f0">{tr_str}</td>'
                table_html += f'<td style="color:{nc}">{net_str}</td>'
                table_html += f'</tr>'

            table_html += '</table>'
            st.markdown(table_html, unsafe_allow_html=True)

            # 详情入口
            st.divider()
            detail_options = [f"{s['name']}({s['code']})" for s in wl]
            selected = st.selectbox("选择股票查看详情", detail_options, key="detail_select")
            if st.button("📊 查看详情", use_container_width=True):
                idx = detail_options.index(selected)
                st.session_state.detail_code = wl[idx]["code"]
                st.rerun()
