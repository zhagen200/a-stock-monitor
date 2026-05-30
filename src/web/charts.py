"""图表组件 - Plotly K线、仪表盘、热力图等"""

import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
import numpy as np


def plot_kline(df: pd.DataFrame, title: str, height=550, show_rsi=True):
    """带技术指标的K线图"""
    rows = 4 if show_rsi else 3
    row_h = [0.5, 0.15, 0.15, 0.15] if show_rsi else [0.6, 0.2, 0.2]
    titles = (title, "成交量", "MACD", "RSI/KDJ") if show_rsi else (title, "成交量", "MACD")
    fig = make_subplots(rows=rows, cols=1, shared_xaxes=True, vertical_spacing=0.02,
                        row_heights=row_h, subplot_titles=titles)

    # K线
    fig.add_trace(go.Candlestick(
        x=df.index, open=df["open"], high=df["high"],
        low=df["low"], close=df["close"], name="K线",
        increasing_line_color="#ef4444", decreasing_line_color="#22c55e"
    ), row=1, col=1)

    # 均线
    for p, c, w in [(5,"#f59e0b",1),(10,"#a855f7",1),(20,"#3b82f6",1.5),(60,"#6b7280",1)]:
        ma = df["close"].rolling(p).mean()
        fig.add_trace(go.Scatter(x=df.index, y=ma, name=f"MA{p}",
                                  line=dict(width=w, color=c)), row=1, col=1)

    # 布林带
    bm = df["close"].rolling(20).mean()
    bs = df["close"].rolling(20).std()
    fig.add_trace(go.Scatter(x=df.index, y=bm+2*bs, name="上轨",
                              line=dict(width=0.8,color="#6b7280",dash="dash")), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=bm-2*bs, name="下轨",
                              line=dict(width=0.8,color="#6b7280",dash="dash"),
                              fill="tonexty", fillcolor="rgba(107,114,128,0.06)"), row=1, col=1)

    # 成交量
    vc = ["#ef4444" if c>=o else "#22c55e" for c,o in zip(df["close"],df["open"])]
    fig.add_trace(go.Bar(x=df.index, y=df["volume"], marker_color=vc, showlegend=False), row=2, col=1)

    # MACD
    e12 = df["close"].ewm(span=12).mean()
    e26 = df["close"].ewm(span=26).mean()
    dif, dea = e12-e26, (e12-e26).ewm(span=9).mean()
    macd = (dif-dea)*2
    fig.add_trace(go.Scatter(x=df.index, y=dif, name="DIF", line=dict(width=1.2,color="#60a5fa")), row=3, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=dea, name="DEA", line=dict(width=1.2,color="#fbbf24")), row=3, col=1)
    mc = ["#ef4444" if v>=0 else "#22c55e" for v in macd]
    fig.add_trace(go.Bar(x=df.index, y=macd, marker_color=mc, showlegend=False), row=3, col=1)

    # RSI + KDJ
    if show_rsi:
        delta = df["close"].diff()
        gain = delta.clip(lower=0).rolling(14).mean()
        loss = (-delta.clip(upper=0)).rolling(14).mean()
        rs = gain / loss.replace(0, np.nan)
        rsi = 100 - 100 / (1 + rs)
        fig.add_trace(go.Scatter(x=df.index, y=rsi, name="RSI(14)",
                                  line=dict(width=1.2,color="#a78bfa")), row=4, col=1)
        fig.add_hline(y=70, line=dict(color="#ef4444", width=0.5, dash="dash"), row=4, col=1)
        fig.add_hline(y=30, line=dict(color="#22c55e", width=0.5, dash="dash"), row=4, col=1)
        # KDJ
        rsi_vals = rsi.dropna()
        if len(rsi_vals) >= 2:
            k = rsi_vals.rolling(3).mean()
            d = k.rolling(3).mean()
            fig.add_trace(go.Scatter(x=df.index[-len(k):], y=k, name="K",
                                      line=dict(width=0.8,color="#fbbf24")), row=4, col=1)
            fig.add_trace(go.Scatter(x=df.index[-len(d):], y=d, name="D",
                                      line=dict(width=0.8,color="#60a5fa")), row=4, col=1)

    fig.update_layout(
        template="plotly_dark", height=height, xaxis_rangeslider_visible=False,
        showlegend=True, legend=dict(orientation="h", yanchor="bottom", y=1.02, font=dict(size=9)),
        margin=dict(l=0,r=0,t=35,b=0), hovermode="x unified"
    )
    return fig


def gauge_fig(value: float, title: str, vmin=-45, vmax=45):
    """仪表盘图"""
    c = "#ef4444" if value>10 else "#22c55e" if value<-10 else "#6b7280"
    fig = go.Figure(go.Indicator(
        mode="gauge+number", value=value,
        title={"text":title,"font":{"size":13}}, number={"font":{"size":22}},
        gauge={
            "axis":{"range":[vmin,vmax]}, "bar":{"color":c,"thickness":0.3},
            "bgcolor":"#1e293b", "borderwidth":0,
            "steps":[
                {"range":[vmin,vmin*0.5],"color":"#14532d"},
                {"range":[vmin*0.5,-5],"color":"#166534"},
                {"range":[-5,5],"color":"#334155"},
                {"range":[5,vmax*0.5],"color":"#7f1d1d"},
                {"range":[vmax*0.5,vmax],"color":"#991b1b"}
            ],
            "threshold":{"line":{"color":"white","width":2},"thickness":0.7,"value":value}
        }
    ))
    fig.update_layout(template="plotly_dark", height=160, margin=dict(l=15,r=15,t=25,b=5))
    return fig


def heatmap_color(change_pct: float) -> str:
    """根据涨跌幅返回背景色 (红涨绿跌)"""
    if change_pct >= 5: return "#b91c1c"
    elif change_pct >= 3: return "#dc2626"
    elif change_pct >= 1: return "#ef4444"
    elif change_pct >= 0: return "#7f1d1d"
    elif change_pct >= -1: return "#14532d"
    elif change_pct >= -3: return "#166534"
    elif change_pct >= -5: return "#15803d"
    else: return "#166534"


def sector_heatmap_html(sectors: list) -> str:
    """板块热力图 HTML"""
    if not sectors:
        return '<div style="color:#64748b;text-align:center;padding:2rem">暂无板块数据</div>'
    html = '<div class="heatmap-grid">'
    for s in sectors[:30]:
        chg = s.get("change_pct", 0)
        bg = heatmap_color(chg)
        html += (
            f'<div class="heatmap-cell" style="background:{bg}">'
            f'<div class="heatmap-name">{s["name"]}</div>'
            f'<div class="heatmap-chg">{chg:+.2f}%</div>'
            f'</div>'
        )
    html += '</div>'
    return html


def fund_flow_chart(flow_data: dict):
    """资金流向柱状图"""
    types = ["主力","超大单","大单","中单","小单"]
    keys = ["main_net_inflow","super_large_net","large_net","medium_net","small_net"]
    values = [flow_data.get(k,0)/10000 for k in keys]
    colors = ["#ef4444" if v>0 else "#22c55e" for v in values]
    fig = go.Figure(go.Bar(
        x=types, y=values, marker_color=colors,
        text=[f"{v:+.0f}万" for v in values], textposition="outside"
    ))
    fig.update_layout(
        template="plotly_dark", height=300,
        title={"text":"资金流向（万元）","font":{"size":14}},
        yaxis={"visible":False}, margin=dict(l=10,r=10,t=40,b=10)
    )
    return fig


def score_bar_chart(scores: dict):
    """技术评分明细柱状图"""
    colors = ["#ef4444" if v>0 else "#22c55e" if v<0 else "#6b7280" for v in scores.values()]
    fig = go.Figure(go.Bar(
        x=list(scores.keys()), y=list(scores.values()),
        marker_color=colors,
        text=[f"{v:+.0f}" for v in scores.values()], textposition="outside"
    ))
    fig.update_layout(
        template="plotly_dark", height=200,
        margin=dict(l=10,r=10,t=5,b=10), yaxis=dict(visible=False)
    )
    return fig
