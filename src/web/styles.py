"""全局CSS样式 - 暗色主题，参考东方财富/同花顺风格"""

GLOBAL_CSS = """
<style>
/* ── 基础 ── */
.stApp { background: #0f1117; }
.block-container { padding-top: 2rem !important; max-width: 100% !important; padding-left: 1rem !important; padding-right: 1rem !important; }
#MainMenu { visibility: hidden; }
header[data-testid="stHeader"] { background: transparent; }

/* ── 侧边栏美化 ── */
[data-testid="stSidebar"] {
    background: #0d1117 !important;
    border-right: 1px solid #1e293b !important;
}
[data-testid="stSidebar"] [data-testid="stMarkdown"] h2 {
    font-size: 1.1rem !important;
    color: #e2e8f0 !important;
    margin-bottom: 0.2rem !important;
}
[data-testid="stSidebar"] [data-testid="stCaption"] {
    color: #64748b !important;
    font-size: 0.72rem !important;
}
[data-testid="stSidebar"] [data-testid="stRadio"] label {
    font-size: 0.85rem !important;
    color: #cbd5e1 !important;
    padding: 0.3rem 0.5rem !important;
    border-radius: 6px !important;
    margin-bottom: 0.1rem !important;
}
[data-testid="stSidebar"] [data-testid="stRadio"] label:hover {
    background: #1e293b !important;
}
[data-testid="stSidebar"] [data-testid="stRadio"] [data-testid="stMarkdown"] p {
    font-size: 0.85rem !important;
}
[data-testid="stSidebar"] hr {
    border-color: #1e293b !important;
    margin: 0.5rem 0 !important;
}
[data-testid="stSidebar"] [data-testid="stButton"] button {
    background: #1e293b !important;
    border: 1px solid #334155 !important;
    color: #e2e8f0 !important;
    font-size: 0.82rem !important;
    border-radius: 6px !important;
}

/* ── 指标卡片统一高度 ── */
div[data-testid="stMetric"] {
    background: #1a1f2e;
    border: 1px solid #2d3748;
    border-radius: 8px;
    padding: 0.6rem 0.8rem;
    min-height: 85px;
    display: flex;
    flex-direction: column;
    justify-content: center;
}
div[data-testid="stMetricValue"] { font-size: 1.2rem !important; }
div[data-testid="stMetricDelta"] { font-size: 0.82rem !important; }
div[data-testid="stMetricLabel"] { font-size: 0.78rem !important; color: #94a3b8 !important; }

/* ── 按钮 ── */
div.stButton > button { background: #1e293b; border: 1px solid #334155; border-radius: 6px; color: #e2e8f0; font-size: 0.78rem; padding: 0.15rem 0.5rem; }
div.stButton > button:hover { background: #334155; border-color: #475569; }

/* ── Tabs ── */
.stTabs [data-baseweb="tab-list"] { gap: 0; background: #1a1f2e; border-radius: 8px; padding: 0.2rem; }
.stTabs [data-baseweb="tab"] { border-radius: 6px; padding: 0.3rem 0.8rem; font-size: 0.85rem; }
.stTabs [aria-selected="true"] { background: #3b82f6 !important; color: white !important; }
.stTabs [data-baseweb="tab-panel"] { padding-top: 0.5rem !important; }

/* ── 指数条 ── */
.idx-bar { display:flex; gap:0.5rem; padding:0.4rem 0; overflow-x:auto; flex-wrap:nowrap; margin-bottom:0.3rem; }
.idx-item { display:flex; align-items:center; gap:0.4rem; background:#1a1f2e; border:1px solid #2d3748; border-radius:8px; padding:0.3rem 0.7rem; min-width:145px; flex-shrink:0; }
.idx-name { font-size:0.7rem; color:#94a3b8; }
.idx-price { font-size:0.95rem; font-weight:700; color:#f1f5f9; }
.idx-chg { font-size:0.78rem; font-weight:600; }

/* ── 颜色 ── */
.price-up { color:#ef4444 !important; }
.price-down { color:#22c55e !important; }

/* ── 卡片 ── */
.mcard { background:#1a1f2e; border:1px solid #2d3748; border-radius:8px; padding:0.5rem 0.8rem; flex:1; min-width:110px; }
.section-title { font-size:1rem; font-weight:600; color:#e2e8f0; margin:0.8rem 0 0.4rem 0; padding-bottom:0.3rem; border-bottom:1px solid #1e293b; }

/* ── 盘口 ── */
.ob-row { display:flex; justify-content:space-between; padding:0.15rem 0.5rem; font-size:0.8rem; }
.ob-row:hover { background:rgba(59,130,246,0.05); border-radius:4px; }

/* ── 新闻 ── */
.news-item { padding:0.3rem 0; border-bottom:1px solid #1a1f2e; font-size:0.82rem; }

/* ── 信号标签 ── */
.sb { display:inline-block; padding:0.1rem 0.45rem; border-radius:999px; font-size:0.72rem; font-weight:600; }
.sb-strong_buy { background:#7f1d1d; color:#fca5a5; }
.sb-buy { background:#7c2d12; color:#fdba74; }
.sb-hold { background:#374151; color:#d1d5db; }
.sb-sell { background:#14532d; color:#86efac; }
.sb-strong_sell { background:#064e3b; color:#6ee7b7; }

/* ── 财务网格 ── */
.fin-grid { display:grid; grid-template-columns:1fr 1fr; gap:0.3rem; font-size:0.82rem; }
.fin-item { display:flex; justify-content:space-between; padding:0.15rem 0.5rem; background:#1a1f2e; border-radius:4px; }

/* ── 热力图 ── */
.heatmap-grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(120px,1fr)); gap:4px; }
.heatmap-cell { padding:6px 8px; border-radius:4px; text-align:center; font-size:0.75rem; line-height:1.3; cursor:pointer; transition:transform 0.1s; }
.heatmap-cell:hover { transform:scale(1.05); }
.heatmap-name { font-weight:600; color:#fff; text-shadow:0 1px 2px rgba(0,0,0,0.5); }
.heatmap-chg { font-size:0.7rem; color:rgba(255,255,255,0.85); }

/* ── 市场情绪条 ── */
.sentiment-bar { display:flex; height:24px; border-radius:4px; overflow:hidden; margin:4px 0; }
.sentiment-up { background:#ef4444; }
.sentiment-flat { background:#6b7280; }
.sentiment-down { background:#22c55e; }

/* ── 数据表格 ── */
.data-table { width:100%; border-collapse:collapse; font-size:0.8rem; }
.data-table th { background:#1e293b; color:#94a3b8; padding:6px 8px; text-align:left; font-weight:500; border-bottom:1px solid #2d3748; }
.data-table td { padding:5px 8px; border-bottom:1px solid #1a1f2e; color:#e2e8f0; }
.data-table tr:hover { background:rgba(59,130,246,0.05); }

/* ── 滚动条 ── */
::-webkit-scrollbar { width:6px; height:6px; }
::-webkit-scrollbar-track { background:#0f1117; }
::-webkit-scrollbar-thumb { background:#334155; border-radius:3px; }
::-webkit-scrollbar-thumb:hover { background:#475569; }
</style>
"""

ACTION_LABELS = {"strong_buy": "强买", "buy":"买入", "hold":"观望", "sell":"卖出", "strong_sell":"强卖"}
ACTION_COLORS = {"strong_buy":"#ef4444", "buy":"#f97316", "hold":"#6b7280", "sell":"#22c55e", "strong_sell":"#10b981"}
ACTION_EMOJI = {"strong_buy":"🔴", "buy":"🟠", "hold":"⚪", "sell":"🟢", "strong_sell":"🔵"}
