"""
Streamlit Web面板 - 多页面
主页: 持仓概览 + 今日信号
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import streamlit as st
import plotly.graph_objects as go
import pandas as pd
from datetime import datetime

from src.core.config import settings
from src.data.manager import DataManager
from src.engine.live import LiveEngine
from src.data.store import SignalStore, TradeStore, PositionStore


st.set_page_config(page_title="A股量化交易系统", page_icon="📊", layout="wide")

if "engine" not in st.session_state:
    settings.load()
    st.session_state.engine = LiveEngine()

engine = st.session_state.engine
data_manager = engine.data_manager
signal_store = SignalStore()
trade_store = TradeStore()
position_store = PositionStore()


def main():
    st.title("📊 A股量化交易系统")

    col1, col2 = st.columns([2, 1])

    with col2:
        st.subheader("📡 大盘指数")
        indices = data_manager.get_market_index()
        if indices:
            for name, data in indices.items():
                change = data.get("change_pct", 0)
                color = "green" if change < 0 else "red"
                st.metric(name, f"{data.get('price', 0):.0f}", f"{change:+.2f}%")
        else:
            st.info("暂无大盘数据")

        positions = position_store.get_all_positions()
        active_positions = [p for p in positions if p["volume"] > 0]
        if active_positions:
            st.subheader("💼 当前持仓")
            pos_df = pd.DataFrame(active_positions)
            for _, row in pos_df.iterrows():
                color = "green" if row["profit_pct"] < 0 else "red"
                st.metric(
                    f"{row['name']}({row['code']})",
                    f"{row['volume']}股",
                    f"{row['profit_pct']:+.2f}%",
                )

    with col1:
        st.subheader("🔍 信号流")
        watchlist = settings.get_watchlist()
        selected_codes = {}

        cols = st.columns(3)
        for i, stock in enumerate(watchlist):
            with cols[i % 3]:
                st.write(f"**{stock['name']}({stock['code']})**")
                if st.button(f"扫描", key=f"scan_{stock['code']}"):
                    signal = engine.scan_stock(stock)
                    if signal:
                        st.session_state[f"signal_{stock['code']}"] = signal
                if f"signal_{stock['code']}" in st.session_state:
                    sig = st.session_state[f"signal_{stock['code']}"]
                    action_color = {
                        "strong_buy": "red", "buy": "orange",
                        "hold": "gray", "sell": "lightgreen",
                        "strong_sell": "green",
                    }
                    st.markdown(
                        f"操作: **:{action_color.get(sig.action, 'gray')}[{sig.action}]**  "
                        f"评分: {sig.score:.0f}  置信: {sig.confidence:.0f}%"
                    )

        st.divider()

        signals = signal_store.get_signals(limit=20)
        if signals:
            st.subheader("📋 历史信号")
            sig_df = pd.DataFrame(signals)
            sig_df = sig_df[["timestamp", "name", "action", "score", "confidence", "price"]]
            sig_df["timestamp"] = sig_df["timestamp"].str[:19]
            st.dataframe(sig_df, use_container_width=True, hide_index=True)

        trades = trade_store.get_trades(limit=20)
        if trades:
            st.subheader("📝 交易记录")
            trade_df = pd.DataFrame(trades)
            cols_show = ["timestamp", "name", "direction", "price", "volume", "amount", "fee"]
            trade_df = trade_df[[c for c in cols_show if c in trade_df.columns]]
            st.dataframe(trade_df, use_container_width=True, hide_index=True)


if __name__ == "__main__":
    main()
