"""
Streamlit Web监控面板
实时K线图、信号流、持仓管理
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
import yaml
from datetime import datetime

from src.data.collector import StockDataCollector
from src.analysis.technical import TechnicalAnalyzer


st.set_page_config(page_title="A股智能监控", page_icon="📊", layout="wide")

@st.cache_resource
def init():
    config_path = Path(__file__).parent.parent.parent / "config" / "settings.yaml"
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}
    return config, StockDataCollector(), TechnicalAnalyzer()

config, collector, technical = init()


def plot_kline_with_indicators(df: pd.DataFrame, title: str):
    """绘制带技术指标的K线图"""
    fig = make_subplots(
        rows=3, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.03,
        row_heights=[0.6, 0.2, 0.2],
        subplot_titles=(title, "成交量", "MACD"),
    )

    # K线
    fig.add_trace(go.Candlestick(
        x=df.index, open=df["open"], high=df["high"],
        low=df["low"], close=df["close"], name="K线",
        increasing_line_color="red", decreasing_line_color="green",
    ), row=1, col=1)

    # 均线
    for period, color in [(5, "yellow"), (10, "purple"), (20, "blue"), (60, "white")]:
        ma = df["close"].rolling(period).mean()
        fig.add_trace(go.Scatter(
            x=df.index, y=ma, name=f"MA{period}",
            line=dict(width=1, color=color),
        ), row=1, col=1)

    # 布林带
    ma20 = df["close"].rolling(20).mean()
    std20 = df["close"].rolling(20).std()
    fig.add_trace(go.Scatter(
        x=df.index, y=ma20 + 2*std20, name="上轨",
        line=dict(width=1, color="gray", dash="dash"),
    ), row=1, col=1)
    fig.add_trace(go.Scatter(
        x=df.index, y=ma20 - 2*std20, name="下轨",
        line=dict(width=1, color="gray", dash="dash"),
        fill="tonexty", fillcolor="rgba(128,128,128,0.1)",
    ), row=1, col=1)

    # 成交量
    colors = ["red" if c >= o else "green" for c, o in zip(df["close"], df["open"])]
    fig.add_trace(go.Bar(
        x=df.index, y=df["volume"], name="成交量",
        marker_color=colors,
    ), row=2, col=1)

    # MACD
    ema12 = df["close"].ewm(span=12).mean()
    ema26 = df["close"].ewm(span=26).mean()
    dif = ema12 - ema26
    dea = dif.ewm(span=9).mean()
    macd = (dif - dea) * 2

    fig.add_trace(go.Scatter(x=df.index, y=dif, name="DIF",
                             line=dict(width=1, color="white")), row=3, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=dea, name="DEA",
                             line=dict(width=1, color="yellow")), row=3, col=1)
    macd_colors = ["red" if v >= 0 else "green" for v in macd]
    fig.add_trace(go.Bar(x=df.index, y=macd, name="MACD",
                         marker_color=macd_colors), row=3, col=1)

    fig.update_layout(
        template="plotly_dark",
        height=800,
        xaxis_rangeslider_visible=False,
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
    )

    return fig


def main():
    st.title("📊 A股智能量化监控系统")
    
    # 侧边栏
    with st.sidebar:
        st.header("⚙️ 设置")
        watchlist = config.get("watchlist", {})
        stocks = watchlist.get("stocks", [])
        stock_names = [f"{s['name']}({s['code']})" for s in stocks]
        
        selected = st.selectbox("选择股票", stock_names)
        days = st.slider("K线天数", 30, 250, 120)
        
        if st.button("🔄 刷新数据"):
            st.cache_data.clear()
            st.rerun()

    if not selected:
        st.info("请在左侧选择要分析的股票")
        return

    stock_code = stocks[stock_names.index(selected)]["code"]
    stock_name = stocks[stock_names.index(selected)]["name"]

    # 获取数据
    with st.spinner(f"加载 {stock_name} 数据..."):
        quote = collector.get_realtime_quote(stock_code)
        kline = collector.get_kline(stock_code, days=days)
        fund_flow = collector.get_fund_flow(stock_code)

    if kline.empty:
        st.error("获取K线数据失败")
        return

    # 顶部指标卡片
    col1, col2, col3, col4, col5 = st.columns(5)
    
    if quote:
        change_pct = quote.get("change_pct", 0)
        color = "red" if change_pct > 0 else "green"
        
        col1.metric("当前价", f"¥{quote['price']:.2f}", f"{change_pct:+.2f}%")
        col2.metric("成交量", f"{quote['volume']/10000:.0f}万手")
        col3.metric("成交额", f"{quote['amount']/100000000:.2f}亿")
        col4.metric("换手率", f"{quote['turnover_rate']:.2f}%")
        col5.metric("PE(动)", f"{quote['pe_ratio']:.1f}")

    # K线图
    st.plotly_chart(
        plot_kline_with_indicators(kline, f"{stock_name}({stock_code})"),
        use_container_width=True,
    )

    # 技术分析结果
    tech_result = technical.analyze(kline, quote.get("price", 0) if quote else 0)
    
    col_left, col_right = st.columns(2)
    
    with col_left:
        st.subheader("📈 技术分析")
        
        # 评分仪表盘
        score = tech_result.total_score
        score_color = "red" if score > 10 else "green" if score < -10 else "gray"
        
        fig_gauge = go.Figure(go.Indicator(
            mode="gauge+number",
            value=score,
            domain={"x": [0, 1], "y": [0, 1]},
            title={"text": "技术评分"},
            gauge={
                "axis": {"range": [-45, 45]},
                "bar": {"color": score_color},
                "steps": [
                    {"range": [-45, -15], "color": "darkgreen"},
                    {"range": [-15, 15], "color": "darkgray"},
                    {"range": [15, 45], "color": "darkred"},
                ],
                "threshold": {
                    "line": {"color": "white", "width": 2},
                    "thickness": 0.75,
                    "value": score,
                },
            },
        ))
        fig_gauge.update_layout(template="plotly_dark", height=300)
        st.plotly_chart(fig_gauge, use_container_width=True)

        # 信号列表
        st.write("**信号明细:**")
        for sig in tech_result.signals:
            icon = "🔴" if sig.signal == "bullish" else "🟢" if sig.signal == "bearish" else "⚪"
            st.write(f"{icon} {sig.name}: {sig.description}")

    with col_right:
        st.subheader("💰 资金流向")
        
        if fund_flow:
            flow_data = {
                "类型": ["主力", "超大单", "大单", "中单", "小单"],
                "净流入(万)": [
                    fund_flow.get("main_net_inflow", 0) / 10000,
                    fund_flow.get("super_large_net", 0) / 10000,
                    fund_flow.get("large_net", 0) / 10000,
                    fund_flow.get("medium_net", 0) / 10000,
                    fund_flow.get("small_net", 0) / 10000,
                ],
            }
            df_flow = pd.DataFrame(flow_data)
            colors = ["red" if v > 0 else "green" for v in df_flow["净流入(万)"]]
            
            fig_flow = go.Figure(go.Bar(
                x=df_flow["类型"], y=df_flow["净流入(万)"],
                marker_color=colors,
            ))
            fig_flow.update_layout(
                template="plotly_dark", height=300,
                title="今日资金流向",
                yaxis_title="净流入(万元)",
            )
            st.plotly_chart(fig_flow, use_container_width=True)
        else:
            st.info("暂无资金流向数据")

        # 关键价位
        st.write("**关键价位:**")
        st.write(f"止损: ¥{tech_result.stop_loss:.2f}")
        st.write(f"止盈1: ¥{tech_result.take_profit_1:.2f}")
        st.write(f"止盈2: ¥{tech_result.take_profit_2:.2f}")
        st.write(f"支撑位: {', '.join([f'¥{s}' for s in tech_result.support_levels[:3]])}")
        st.write(f"阻力位: {', '.join([f'¥{r}' for r in tech_result.resistance_levels[:3]])}")


if __name__ == "__main__":
    main()
