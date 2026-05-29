# 系统设计文档 v3

## 一、架构设计

### 1.1 系统架构

```
┌─────────────────────────────────────────────────────────────────────────┐
│                       主控制台 (monitor.py)                              │
│                日度节奏调度：推荐→扫描→AI分析→汇总→休眠                   │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐ │
│  │ 数据层    │  │ 分析层    │  │ 选股层    │  │ AI引擎层  │  │ 推送层    │ │
│  │          │  │          │  │          │  │          │  │          │ │
│  │ collector│  │technical │  │smart_pick│  │ llm_depot│  │ notifier │ │
│  │ news     │  │signal_eng│  │market_scn│  │ analyzer │  │ (钉钉等) │ │
│  │          │  │          │  │          │  │ evolver  │  │          │ │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘ │
│       │              │              │              │              │      │
│       └──────────────┴──────────────┴──────┬───────┴──────────────┘      │
│                                            │                             │
│                              ┌─────────────▼─────────────┐              │
│                              │    回测数据库 (SQLite)      │              │
│                              │  signals / backtest_results│              │
│                              │  strategy_versions         │              │
│                              │  evolution_log             │              │
│                              └─────────────┬─────────────┘              │
│                                            │                             │
│                              ┌─────────────▼─────────────┐              │
│                              │      Web 面板              │              │
│                              │     (Streamlit)            │              │
│                              │ 行情/持仓/关注/AI分析/回测  │              │
│                              └───────────────────────────┘              │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### 1.2 数据流

```
启动时:
  → _backfill_returns() → 回填历史信号收益

开盘前(08:50-09:15):
  东方财富API → scan_short_term_opportunities() → 推荐TOP10 → 推送

交易时段(09:15-15:00, 每60秒):
  腾讯API → get_realtime_quote() → 实时行情
  腾讯API → get_kline()          → K线数据
  AKShare  → get_fund_flow()     → 资金流向
  → signal_engine.generate()     → 技术信号
  
  AI分析流程:
  LLM Depot → 选择最佳模型
  Analyzer  → 信号深度分析 (技术面矛盾识别、置信度评估)
  Analyzer  → 新闻情感分析 (仅持仓股)
  → BacktestDB.save_signal()     → 存储信号+AI分析结果
  → 买卖信号 → 推送

收盘后(15:00-15:15):
  _backfill_returns()            → 回填历史信号实际收益
  大盘指数 + 信号汇总 + 资金流向 → 收盘汇总 → 推送

周日:
  StrategyEvolver.run_evolution() → 策略进化评估 → 生成新策略版本
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

**market_scanner.py** — 全市场扫描器
- 全市场股票扫描
- 多维度筛选条件

选股策略:
```
1. 主力资金净流入 > 1000万
2. 涨幅 2%~8%（不追涨停）
3. 排除ST股、停牌股
4. 评分: 涨幅3%~6% +20, 净流入>1亿 +30, >5000万 +20, >1000万 +10
5. 取TOP10
```

### 2.4 AI引擎层 (`src/llm/`) ⭐新增

**depot.py** — 多模型LLM调度中心
- 按任务类型自动选择最佳模型
- 故障自动转移（主模型失败切换备用模型）
- 使用统计（调用次数、成功率、响应时间）
- 模型分工:
  - MiMo → 选股推荐
  - GLM-5.1 → 技术分析
  - DeepSeek → 新闻分析
  - Gemini → 回测归因

**analyzer.py** — AI量化分析引擎
- `analyze_signal_deep()` — 信号深度分析
  - 技术面矛盾识别
  - 置信度评估
  - 风险点提示
- `analyze_news_batch()` — 新闻批量分析
  - 情感倾向判断
  - 利好利空识别
- `generate_stock_report()` — 个股报告生成
  - 综合技术/资金/新闻
- `evaluate_signal_accuracy()` — 信号准确性评估
  - 基于回填数据分析

**evolver.py** — 策略自进化引擎
- **BacktestDB** — 回测数据库管理
  - `save_signal()` — 保存信号记录
  - `update_actual_returns()` — 回填实际收益
  - `get_pending_signals()` — 获取待回填信号
  - `get_signal_stats()` — 获取信号统计
- **StrategyEvolver** — 策略进化器
  - `run_evolution()` — 执行策略进化评估
  - 分析近期回测数据
  - 识别有效因子
  - 动态调整权重参数
  - 生成新策略版本

### 2.5 推送层 (`src/notify/`)

**notifier.py** — 多渠道推送
- 钉钉群机器人（Markdown消息，免费无限制）
- Server酱（微信推送）
- 企业微信机器人
- Bark（iOS推送）
- 推送内容: 买卖信号、每日推荐、收盘汇总、资金流向报表

### 2.6 Web面板 (`src/web/`)

**dashboard.py** — Streamlit界面（5页面）
- 📈 行情分析: 选择股票查看K线、技术指标、资金流向、持仓盈亏
- 💼 持仓管理: 添加/编辑成本数量/全部卖出/删除
- 👁️ 关注池: 手动添加/移除，查看来源（手动/智能推荐）
- 🤖 **AI分析**: 各股票最新AI深度分析、评分趋势图、置信度概览
- 📊 **回测数据**: 信号统计分布、回测结果、策略版本管理、进化日志

**portfolio.py** — 持仓数据管理
- JSON文件存储（data/holdings.json, data/watch_pool.json）
- CRUD操作: add_holding, update_holding, sell_holding, delete_holding
- 关注池: add_to_watch, remove_from_watch
- 与 monitor.py 动态池联动

### 2.7 主程序 (`monitor.py`)

**StockMonitor** — 日度节奏控制

| 时段 | 方法 | 行为 |
|------|------|------|
| 启动时 | `_backfill_returns()` | 回填历史信号收益 |
| 08:50-09:15 | `daily_recommend()` | 智能选股推荐TOP10，推送 |
| 09:15-11:30 | `scan_all()` | 每60秒扫描+AI分析，买卖信号推送 |
| 11:30-13:00 | 休眠 | `_sleep_until(13, 0)` |
| 13:00-15:00 | `scan_all()` | 每60秒扫描+AI分析，买卖信号推送 |
| 15:00-15:15 | `closing_summary()` | 收益回填+当日汇总+资金流向+后续关注，推送 |
| 15:15-次日 | 休眠 | `_sleep_until(次日8:50)` |
| 周末/假日 | 休眠 | 跳过全天 |
| 周日 | `run_evolution()` | 策略进化评估 |

动态监控池管理:
- `_cleanup_dynamic_pool()`: 推荐股票超过3天自动移除
- 持仓股永不自动移除
- 关注池通过Web面板手动管理

## 三、数据存储

```
data/
├── holdings.json       # 持仓 [{code, name, cost, shares, added_at, updated_at}]
├── watch_pool.json     # 关注池 [{code, name, source, reason, added_at}]
└── backtest.db         # 回测数据库 (SQLite)

logs/
├── monitor.log         # 运行日志（Python logging, 纯文本）
└── watchlist_pool.json # 动态监控池（推荐股票, 3天过期）
```

### 回测数据库表结构

**signals** — 信号记录
```sql
CREATE TABLE signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    code TEXT NOT NULL,
    name TEXT NOT NULL,
    action TEXT NOT NULL,           -- buy/sell/hold/strong_buy/strong_sell
    score REAL,                     -- 综合评分
    price REAL,                     -- 信号时价格
    ai_analysis TEXT,               -- AI深度分析文本
    ai_confidence REAL,             -- AI置信度
    technical_score REAL,           -- 技术面评分
    capital_score REAL,             -- 资金面评分
    news_score REAL,                -- 消息面评分
    actual_return_1d REAL DEFAULT 0,-- 1日实际收益(%)
    actual_return_3d REAL DEFAULT 0,-- 3日实际收益(%)
    actual_return_5d REAL DEFAULT 0,-- 5日实际收益(%)
    actual_return_10d REAL DEFAULT 0,-- 10日实际收益(%)
    max_drawdown REAL,              -- 最大回撤(%)
    correct_factors TEXT,           -- 正确因子
    wrong_factors TEXT,             -- 错误因子
    lesson_learned TEXT             -- 经验教训
);
```

**backtest_results** — 每日回测结果
```sql
CREATE TABLE backtest_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT,
    total_signals INTEGER,
    buy_signals INTEGER,
    sell_signals INTEGER,
    accuracy_1d REAL,               -- 1日准确率
    accuracy_3d REAL,               -- 3日准确率
    accuracy_5d REAL,               -- 5日准确率
    avg_return_1d REAL,             -- 平均1日收益
    avg_return_3d REAL,             -- 平均3日收益
    avg_return_5d REAL,             -- 平均5日收益
    sharpe_ratio REAL,              -- 夏普比率
    max_drawdown REAL,              -- 最大回撤
    win_rate REAL,                  -- 胜率
    ai_evaluation TEXT,             -- AI评估
    key_insights TEXT,              -- 关键洞察
    created_at TEXT
);
```

**strategy_versions** — 策略版本
```sql
CREATE TABLE strategy_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    version INTEGER,
    params TEXT,                    -- JSON格式参数
    accuracy REAL,
    sharpe_ratio REAL,
    reason TEXT,                    -- 版本变更原因
    created_at TEXT
);
```

**evolution_log** — 进化日志
```sql
CREATE TABLE evolution_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT,
    version INTEGER,
    old_params TEXT,                -- 旧参数JSON
    new_params TEXT,                -- 新参数JSON
    accuracy_before REAL,
    accuracy_after REAL,
    ai_reasoning TEXT,              -- AI推理过程
    key_changes TEXT                -- 关键变更JSON
);
```

## 四、配置文件

`config/settings.yaml`（.gitignore保护）

```yaml
watchlist:           # 自选股(stocks + funds)
llm_models:          # 多模型配置
  mimo:              # 选股推荐
  glm:               # 技术分析
  deepseek:          # 新闻分析
  gemini:            # 回测归因
ai_analysis:         # AI分析开关
  enabled: true
  evolution_enabled: true
notify:              # 推送渠道(dingtalk_webhook, serverchan_key)
signal:              # 信号阈值 + 权重
schedule:            # 扫描间隔
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
| LLM分析 | MiMo/GLM/DeepSeek/Gemini API | HTTP POST (OpenAI兼容) |

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
sqlite3             # 回测数据库（内置）
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

## 七、策略自进化机制

### 进化触发条件

1. **常规触发**: 每周日自动检查
2. **数据门槛**: 回测记录数 ≥ 50
3. **紧急触发**: 连续3日信号准确率 < 40%

### 进化流程

```
1. 收集近期回测数据 (signals + actual_returns)
2. 按信号类型分组统计准确率和收益
3. AI分析信号归因（哪些因子有效/无效）
4. 计算新权重参数
5. 生成新策略版本 (strategy_versions)
6. 记录进化日志 (evolution_log)
7. 更新配置文件
```

### 收益回填机制

系统在两个时机自动回填信号的实际收益：
1. **收盘汇总时** (15:15): 回填当天及近期信号
2. **系统启动时**: 确保历史数据不丢失

回填逻辑:
- 获取信号日期后的K线数据
- 计算1日/3日/5日/10日收益率
- 计算最大回撤
- 更新数据库
