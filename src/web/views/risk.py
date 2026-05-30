"""风险监控页面 - 持仓分析、资产配置、风险指标"""

import streamlit as st
import plotly.graph_objects as go
import pandas as pd
from datetime import datetime
from src.web.styles import GLOBAL_CSS, ACTION_LABELS, ACTION_COLORS, ACTION_EMOJI
from src.web.helpers import fv, fa


def render_risk_page(data_manager, position_store, signal_store, trade_store, settings):
    """风险监控页面"""
    st.markdown(GLOBAL_CSS, unsafe_allow_html=True)
    st.markdown('<div style="font-size:1.1rem;font-weight:700;color:#f1f5f9;margin-bottom:0.5rem">'
                '⚠️ 风险监控</div>', unsafe_allow_html=True)

    # ── 获取持仓数据 ──
    positions = position_store.get_all_positions()
    active = [p for p in positions if p.get("volume", 0) > 0]
    watchlist = settings.get_watchlist()

    if not active and not watchlist:
        st.info("暂无持仓数据，请先在自选股中添加持仓信息")
        return

    # ── 持仓概览 ──
    st.markdown('<div style="font-size:0.95rem;font-weight:600;color:#f1f5f9;margin-bottom:0.3rem">'
                '💼 持仓概览</div>', unsafe_allow_html=True)

    total_cost = 0
    total_value = 0
    holdings_data = []

    for w in watchlist:
        if not w.get("cost") or not w.get("shares"):
            continue
        code = w["code"]
        name = w["name"]
        cost = w["cost"]
        shares = w["shares"]
        cost_total = cost * shares

        quote = data_manager.get_realtime_quote(code)
        current_price = quote.get("price", cost) if quote else cost
        market_value = current_price * shares
        pnl = market_value - cost_total
        pnl_pct = (current_price / cost - 1) * 100

        total_cost += cost_total
        total_value += market_value

        holdings_data.append({
            "code": code, "name": name, "cost": cost,
            "shares": shares, "current": current_price,
            "cost_total": cost_total, "market_value": market_value,
            "pnl": pnl, "pnl_pct": pnl_pct,
        })

    # 汇总指标
    if holdings_data:
        total_pnl = total_value - total_cost
        total_pnl_pct = (total_value / total_cost - 1) * 100 if total_cost > 0 else 0
        pnl_color = "#ef4444" if total_pnl >= 0 else "#22c55e"

        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.markdown(
                f'<div style="background:#1a1f2e;border:1px solid #2d3748;border-radius:8px;padding:0.6rem;text-align:center">'
                f'<div style="font-size:0.72rem;color:#94a3b8">总成本</div>'
                f'<div style="font-size:1.2rem;font-weight:700;color:#f1f5f9">¥{total_cost:,.0f}</div>'
                f'</div>', unsafe_allow_html=True
            )
        with c2:
            st.markdown(
                f'<div style="background:#1a1f2e;border:1px solid #2d3748;border-radius:8px;padding:0.6rem;text-align:center">'
                f'<div style="font-size:0.72rem;color:#94a3b8">总市值</div>'
                f'<div style="font-size:1.2rem;font-weight:700;color:#f1f5f9">¥{total_value:,.0f}</div>'
                f'</div>', unsafe_allow_html=True
            )
        with c3:
            st.markdown(
                f'<div style="background:#1a1f2e;border:1px solid #2d3748;border-radius:8px;padding:0.6rem;text-align:center">'
                f'<div style="font-size:0.72rem;color:#94a3b8">总盈亏</div>'
                f'<div style="font-size:1.2rem;font-weight:700;color:{pnl_color}">¥{total_pnl:+,.0f}</div>'
                f'</div>', unsafe_allow_html=True
            )
        with c4:
            st.markdown(
                f'<div style="background:#1a1f2e;border:1px solid #2d3748;border-radius:8px;padding:0.6rem;text-align:center">'
                f'<div style="font-size:0.72rem;color:#94a3b8">总收益率</div>'
                f'<div style="font-size:1.2rem;font-weight:700;color:{pnl_color}">{total_pnl_pct:+.2f}%</div>'
                f'</div>', unsafe_allow_html=True
            )

    st.markdown("---")

    # ── 持仓明细 + 资产配置 ──
    col_left, col_right = st.columns([2, 1])

    with col_left:
        st.markdown('<div style="font-size:0.9rem;font-weight:600;color:#f1f5f9;margin-bottom:0.3rem">'
                    '持仓明细</div>', unsafe_allow_html=True)

        for h in holdings_data:
            pnl_color = "#ef4444" if h["pnl"] >= 0 else "#22c55e"
            pnl_ar = "▲" if h["pnl"] >= 0 else "▼"
            weight = h["market_value"] / total_value * 100 if total_value > 0 else 0

            st.markdown(
                f'<div style="background:#1a1f2e;border:1px solid #2d3748;border-radius:8px;padding:0.5rem 0.8rem;margin-bottom:0.3rem">'
                f'<div style="display:flex;justify-content:space-between;align-items:center">'
                f'<span style="font-weight:600;color:#f1f5f9">{h["name"]}({h["code"]})</span>'
                f'<span style="color:{pnl_color};font-weight:600">{pnl_ar} {h["pnl_pct"]:+.2f}%</span>'
                f'</div>'
                f'<div style="display:flex;gap:1rem;margin-top:0.3rem;font-size:0.78rem;color:#94a3b8">'
                f'<span>成本 ¥{h["cost"]:.2f}</span>'
                f'<span>现价 ¥{h["current"]:.2f}</span>'
                f'<span>{h["shares"]}股</span>'
                f'<span>市值 ¥{h["market_value"]:,.0f}</span>'
                f'<span>盈亏 <span style="color:{pnl_color}">¥{h["pnl"]:+,.0f}</span></span>'
                f'<span>仓位 {weight:.1f}%</span>'
                f'</div>'
                # 仓位进度条
                f'<div style="margin-top:0.3rem;height:4px;background:#2d3748;border-radius:2px;overflow:hidden">'
                f'<div style="height:100%;width:{min(weight,100):.0f}%;background:#3b82f6;border-radius:2px"></div>'
                f'</div>'
                f'</div>', unsafe_allow_html=True
            )

    with col_right:
        st.markdown('<div style="font-size:0.9rem;font-weight:600;color:#f1f5f9;margin-bottom:0.3rem">'
                    '资产配置</div>', unsafe_allow_html=True)

        if holdings_data:
            labels = [h["name"] for h in holdings_data]
            values = [h["market_value"] for h in holdings_data]
            colors = ["#3b82f6", "#ef4444", "#f59e0b", "#22c55e", "#a855f7", "#ec4899", "#14b8a6", "#f97316"]

            fig = go.Figure(go.Pie(
                labels=labels, values=values, hole=0.4,
                marker=dict(colors=colors[:len(labels)]),
                textfont=dict(size=11),
            ))
            fig.update_layout(
                template="plotly_dark", height=300,
                margin=dict(l=10, r=10, t=10, b=10),
                showlegend=True, legend=dict(font=dict(size=10))
            )
            st.plotly_chart(fig, use_container_width=True)

    st.markdown("---")

    # ── 最近信号 ──
    st.markdown('<div style="font-size:0.95rem;font-weight:600;color:#f1f5f9;margin-bottom:0.3rem">'
                '📡 最近交易信号</div>', unsafe_allow_html=True)

    signals = signal_store.get_signals(limit=20)
    if signals:
        for sig in signals[:10]:
            action = sig.get("action", "hold")
            color = ACTION_COLORS.get(action, "#6b7280")
            emoji = ACTION_EMOJI.get(action, "")
            label = ACTION_LABELS.get(action, action)
            ts = sig.get("timestamp", "")[:16]

            st.markdown(
                f'<div style="display:flex;align-items:center;gap:0.5rem;padding:0.3rem 0.5rem;'
                f'border-bottom:1px solid #1a1f2e;font-size:0.8rem">'
                f'<span style="color:#64748b;min-width:130px">{ts}</span>'
                f'<span style="color:#f1f5f9;min-width:80px;font-weight:500">{sig.get("name","")}</span>'
                f'<span style="background:{color}22;color:{color};padding:0.1rem 0.4rem;border-radius:999px;'
                f'font-size:0.72rem;font-weight:600;min-width:50px;text-align:center">{emoji} {label}</span>'
                f'<span style="color:#94a3b8">评分 {sig.get("score",0):.0f}</span>'
                f'<span style="color:#94a3b8">置信 {sig.get("confidence",0):.0f}%</span>'
                f'<span style="color:#f1f5f9">¥{sig.get("price",0):.2f}</span>'
                f'</div>', unsafe_allow_html=True
            )
    else:
        st.info("暂无信号记录")
