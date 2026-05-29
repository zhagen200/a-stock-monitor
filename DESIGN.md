# 系统设计文档

## 一、架构设计

### 1.1 系统架构

```
┌─────────────────────────────────────────────────────────────┐
│                     主控制台 (monitor.py)                     │
│              日度节奏调度：推荐→扫描→汇总→休眠               │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐   │
│  │ 数据层    │  │ 分析层    │  │ 选股层    │  │ 推送层    │   │
│  │          │  │          │  │          │  │          │   │
│  │ collector│  │technical │  │smart_pick│  │ notifier │   │
│  │ news     │  │signal_eng│  │          │  │ (钉钉等) │   │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘   │
│       │              │              │              │        │
│       └──────────────┴──────────────┴──────────────┘        │
│                              │                               │
│                    ┌─────────▼─────────┐                    │
│                    │   Web 面板        │                    │
│                    │  (Streamlit)      │                    │
│                    │  行情/持仓/关注池  │                    │
│                    └───────────────────┘                    │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### 1.2 数据流

```
开盘前(09:00):
  东方财富API → scan_short_term_opportunities() → 推荐TOP10 → 推送

交易时段(09:15-15:00, 每60秒):
  腾讯API → get_realtime_quote() → 实时行情
  腾讯API → get_kline()          → K线数据
  AKShare  → get_fund_flow()     → 资金流向
  LLM      → analyze_news()      → 新闻情绪(仅持仓股)
  → signal_engine.generate()     → 信号(买入/卖出/观望)
  → 买卖信号 → 推送

收盘后(15:00):
  大盘指数 + 信号汇总 + 资金流向 → 收盘汇总 → 推送
```

## 二、模块详解

### 2.1 数据层 (`src/data/`)

**collector.py** — 数据采集
- `get_realtime_quote()` — 腾讯行情API，实时股价/涨跌幅/成交量/换手率/PE
- `get_kline()` — 腾讯K线API + AKShare回退，支持日/周/月
- `get_fund_flow()` — 资金流向（主力/超大单/大单/中单/小单）
- `get_market_index()` — 大盘指数（上证/深证/创业板）

**news.py** — 新闻采集
- 东方财富个股新闻，返回标题+摘要列表

### 2.2 分析层 (`src/analysis/`)

**technical.py** — 技术分析器
- MA排列（多头/空头/纠缠）
- MACD金叉死叉 + 柱状图方向
- RSI超买超卖（4档区间）
- KDJ金叉死叉 + J值超限
- 布林带支撑/压力
- K线形态（锤子线/吞没/十字星）
- 综合评分范围: -45 ~ +45

**signal_engine.py** — 多因子信号融合
- 技术分析(40%) + 资金流向(20%) + 新闻情绪(25%) + 基本面(15%)
- 输出: TradeSignal(code, name, price, action, score, confidence, stop_loss, take_profit, reasons)

### 2.3 选股层 (`src/scanner/`)

**smart_picker.py** — 智能选股
- 数据源: 东方财富Web API（直接HTTP调用，绕过akshare代理问题）
- `get_sector_fund_flow(count)` — 板块资金流向TOP N
- `get_stock_fund_flow_top(count)` — 个股资金流入TOP N
- `scan_short_term_opportunities(max_count)` — 短线机会扫描
- `generate_daily_report()` — 每日资金流向报表

选股策略:
```
1. 主力资金净流入 > 1000万
2. 涨幅 2%~8%（不追涨停）
3. 排除ST股、停牌股
4. 评分: 涨幅3%~6% +20, 净流入>1亿 +30, >5000万 +20, >1000万 +10
5. 取TOP10
```

### 2.4 推送层 (`src/notify/`)

**notifier.py** — 多渠道推送
- 钉钉群机器人（Markdown消息，免费无限制）
- Server酱（微信推送）
- 企业微信机器人
- Bark（iOS推送）
- 推送内容: 买卖信号、每日推荐、收盘汇总、资金流向报表

### 2.5 Web面板 (`src/web/`)

**dashboard.py** — Streamlit界面
- 📈 行情分析: 选择股票查看K线、技术指标、资金流向、持仓盈亏
- 💼 持仓管理: 添加/编辑成本数量/全部卖出/删除
- 👁️ 关注池: 手动添加/移除，查看来源（手动/智能推荐）

**portfolio.py** — 持仓数据管理
- JSON文件存储（data/holdings.json, data/watch_pool.json）
- CRUD操作: add_holding, update_holding, sell_holding, delete_holding
- 关注池: add_to_watch, remove_from_watch
- 与 monitor.py 动态池联动

### 2.6 主程序 (`monitor.py`)

**StockMonitor** — 日度节奏控制

| 时段 | 方法 | 行为 |
|------|------|------|
| 08:50-09:15 | `daily_recommend()` | 智能选股推荐TOP10，推送 |
| 09:15-11:30 | `scan_all()` | 每60秒扫描，买卖信号推送 |
| 11:30-13:00 | 休眠 | `_sleep_until(13, 0)` |
| 13:00-15:00 | `scan_all()` | 每60秒扫描，买卖信号推送 |
| 15:00-15:15 | `closing_summary()` | 当日汇总+资金流向+后续关注，推送 |
| 15:15-次日 | 休眠 | `_sleep_until(次日8:50)` |
| 周末/假日 | 休眠 | 跳过全天 |

动态监控池管理:
- `_cleanup_dynamic_pool()`: 推荐股票超过3天自动移除
- 持仓股永不自动移除
- 关注池通过Web面板手动管理

## 三、数据存储

```
data/
├── holdings.json       # 持仓 [{code, name, cost, shares, added_at, updated_at}]
└── watch_pool.json     # 关注池 [{code, name, source, reason, added_at}]

logs/
├── monitor.log         # 运行日志（Python logging, 纯文本）
├── watchlist_pool.json # 动态监控池（推荐股票, 3天过期）
└── push_counter.db     # 推送次数计数（SQLite）
```

## 四、配置文件

`config/settings.yaml`（.gitignore保护）

```yaml
watchlist:     # 自选股(stocks + funds)
llm:           # LLM配置(api_base, model, api_key, enabled)
notify:        # 推送渠道(dingtalk_webhook, serverchan_key)
signal:        # 信号阈值 + 权重
schedule:      # 扫描间隔
```

## 五、外部依赖

### 数据源

| 数据 | 来源 | 方式 |
|------|------|------|
| 实时行情 | 腾讯行情API | HTTP GET |
| K线数据 | 腾讯K线API + AKShare回退 | HTTP GET |
| 资金流向 | AKShare | Python库调用 |
| 新闻 | 东方财富 | 网页抓取 |
| 板块/个股资金流向TOP | 东方财富Web API | 直接HTTP（trust_env=False绕过代理） |
| LLM新闻分析 | MiMo API (OpenAI兼容) | HTTP POST |

### Python依赖

```
akshare >= 1.14     # A股数据
pandas >= 2.0       # 数据处理
requests            # HTTP
rich                # CLI输出
pyyaml              # 配置
openai              # LLM客户端
streamlit           # Web面板
plotly              # 图表
```

## 六、信号评分体系

### 技术分析评分 (-45 ~ +45)

| 指标 | 多头加分 | 空头减分 |
|------|----------|----------|
| MA排列 | 多头+10, 偏多+5 | 空头-10, 偏空-5 |
| MACD | 金叉+8, 红柱放大+5 | 死叉-8, 绿柱放大-5 |
| RSI | 超卖(<30)+8, 偏低+4 | 超买(>70)-8, 偏高-4 |
| KDJ | 金叉+6 | 死叉-6 |
| 布林带 | 下轨支撑+4 | 上轨压力-4 |
| K线形态 | 锤子线/吞没+5 | 十字星/吊颈线-5 |

### 多因子融合

```
综合评分 = 技术×40% + 资金×20% + 新闻×25% + 基本面×15%

≥ 60   → 🔴 强烈买入 (推送)
30~60  → 🟠 买入 (推送)
-30~30 → ⚪ 观望 (不推送)
-60~-30→ 🟢 卖出 (推送)
≤ -60  → 🔵 强烈卖出 (推送)
```
