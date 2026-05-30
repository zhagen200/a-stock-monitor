# 系统设计文档 v4

## 一、架构设计

### 1.1 系统架构

```
┌─────────────────────────────────────────────────────────────────────────┐
│                       统一入口 (main.py)                                 │
│          --mode once/loop/web/backtest/optimize                         │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐ │
│  │ 数据层    │  │ 策略层    │  │ 引擎层    │  │ AI引擎层  │  │ 推送层    │ │
│  │          │  │          │  │          │  │          │  │          │ │
│  │collector │  │technical │  │live      │  │ llm_depot│  │ notifier │ │
│  │news      │  │capital   │  │backtest  │  │ analyzer │  │ (钉钉等) │ │
│  │manager   │  │ensemble  │  │signal_bus│  │ evolver  │  │          │ │
│  │cache     │  │+ 5 more  │  │          │  │          │  │          │ │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘ │
│       │              │              │              │              │      │
│       └──────────────┴──────────────┴──────┬───────┴──────────────┘      │
│                                            │                             │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐ │                             │
│  │ 执行层    │  │ 风控层    │  │ 分析层    │ │                             │
│  │          │  │          │  │          │ │                             │
│  │broker    │  │manager   │  │metrics   │ │                             │
│  │order     │  │rules     │  │report    │ │                             │
│  │position  │  │          │  │          │ │                             │
│  └──────────┘  └──────────┘  └──────────┘ │                             │
│                                            │                             │
│                              ┌─────────────▼─────────────┐              │
│                              │  统一数据库 (SQLite)        │              │
│                              │  data/stock_monitor.db     │              │
│                              │  10张表: signals/trades/   │              │
│                              │  positions/holdings/       │              │
│                              │  watch_pool/kline_data/    │              │
│                              │  backtest_results/         │              │
│                              │  strategy_versions/        │              │
│                              │  evolution_log             │              │
│                              └─────────────┬─────────────┘              │
│                                            │                             │
│                              ┌─────────────▼─────────────┐              │
│                              │      Web 面板              │              │
│                              │     (Streamlit v4)         │              │
│                              │ 自选股/大盘行情/选股筛选/   │              │
│                              │ 风险监控/信号中心/回测数据  │              │
│                              └───────────────────────────┘              │
└─────────────────────────────────────────────────────────────────────────┘
```

### 1.2 数据流

```
启动:
  main.py → settings.load() → LiveEngine() → init_database()

交易时段:
  DataManager → 腾讯API(实时行情) + AKShare(历史K线) + 东方财富(资金流)
  LiveEngine → StrategyEnsemble → TradeSignal
  SignalStore → 保存信号
  TradeStore → 保存交易
  PositionStore → 更新持仓
  Notifier → 推送信号

Web面板:
  Streamlit → DataManager(行情) + Store(数据) + TechnicalAnalyzer(分析)
  6个页面: 自选股/大盘行情/选股筛选/风险监控/信号中心/回测数据
```

## 二、模块详解

### 2.1 核心层 (`src/core/`)

**config.py** — 单例配置管理
- `settings.load()` 从 config/settings.yaml 加载
- `settings.get_watchlist()` 获取自选股列表

**base.py** — 基础数据结构
- TradeSignal, Order, Position 等 dataclass

### 2.2 数据层 (`src/data/`)

**collector.py** — 数据采集
- `get_realtime_quote()` — 腾讯行情API
- `get_kline()` — 腾讯K线API + AKShare回退
- `get_fund_flow()` — 资金流向
- `get_market_index()` — 大盘指数

**manager.py** — 数据管理器
- 带缓存的数据访问层
- 支持多周期K线（日/周/月/60分/15分）

**store.py** — SQLite统一存储
- KlineStore — K线数据缓存
- SignalStore — 信号记录
- TradeStore — 交易记录
- PositionStore — 持仓管理
- HoldingsStore — 配置持仓（替代 holdings.json）
- WatchPoolStore — 关注池（替代 watch_pool.json）

**cache.py** — 内存缓存（TTL机制）

### 2.3 分析层 (`src/analysis/`)

**technical.py** — 技术分析器
- MA排列、MACD、RSI、KDJ、布林带、K线形态
- 综合评分 -45 ~ +45

**signal_engine.py** — 多因子信号融合
- 技术(40%) + 资金(20%) + 新闻(25%) + 基本面(15%)
- 输出: TradeSignal

### 2.4 策略层 (`src/strategy/`)

8个策略模块，用于回测和集成：
- TechnicalStrategy — 技术策略
- CapitalFlowStrategy — 资金流策略
- NewsSentimentStrategy — 新闻情绪策略
- MultiTimeframeStrategy — 多周期策略
- VolumePatternStrategy — 量价形态策略
- TrendStrengthStrategy — 趋势强度策略
- EnsembleStrategy — 集成策略（组合多个子策略）

### 2.5 引擎层 (`src/engine/`)

**live.py** — 实时交易引擎
- 扫描自选股 → 生成信号 → 执行交易 → 更新持仓

**backtest.py** — 回测引擎
- 历史数据回测 → 绩效评估

**signal_bus.py** — 信号总线
- 信号分发和处理

### 2.6 执行层 (`src/execution/`)

**broker.py** — 模拟券商（MockBroker）
**order.py** — 订单管理
**position.py** — 持仓管理

### 2.7 风控层 (`src/risk/`)

**manager.py** — 风险管理器
**rules.py** — 风险规则
- PositionLimitRule — 持仓集中度限制
- MarketRegimeFilter — 市场环境过滤
- ConsecutiveLossRule — 连续亏损限制

### 2.8 AI引擎层 (`src/llm/`)

**depot.py** — 多模型LLM调度中心
- 按任务类型选择模型（MiMo/GLM/DeepSeek/Gemini）
- 故障自动转移

**analyzer.py** — AI量化分析引擎
- 信号深度分析、新闻情感分析、个股报告

**evolver.py** — 策略自进化引擎
- BacktestDB — 回测数据库（使用统一 stock_monitor.db）
- StrategyEvolver — 策略参数自动优化

### 2.9 Web面板 (`src/web/`)

**app.py** — Streamlit 主面板（v4）
- 侧边栏导航 + 6个页面

**styles.py** — 全局CSS暗色主题
**charts.py** — Plotly图表组件
**helpers.py** — 工具函数（东方财富API封装）

**pages/market.py** — 大盘行情页
- 大盘指数、行业/概念板块热力图、涨跌榜

**pages/screener.py** — 选股筛选器
- 多条件筛选（涨跌幅/换手率/成交额/PE）

**pages/risk.py** — 风险监控页
- 持仓盈亏汇总、资产配置饼图、仓位明细

## 三、数据存储

统一数据库: `data/stock_monitor.db` (SQLite)

```
signals          — 信号记录（含AI分析、实际收益回填）
trades           — 交易记录
positions        — 当前持仓
holdings         — 配置持仓（成本/数量）
watch_pool       — 关注池
kline_data       — K线缓存
backtest_results — 每日回测结果
strategy_versions— 策略版本
evolution_log    — 进化日志
```

## 四、配置文件

`config/settings.yaml`（.gitignore保护）

```yaml
watchlist:           # 自选股(stocks + funds)
llm_models:          # 多模型配置
llm:                 # 单模型配置（兼容）
ai_analysis:         # AI分析开关
notify:              # 推送渠道
signal:              # 信号阈值 + 权重
schedule:            # 扫描间隔
risk:                # 风控参数
backtest:            # 回测参数
```

## 五、外部依赖

| 数据 | 来源 | 方式 |
|------|------|------|
| 实时行情 | 腾讯行情API | HTTP GET |
| K线数据 | 腾讯K线API + AKShare | HTTP GET |
| 资金流向 | 东方财富Web API | HTTP GET |
| 板块数据 | 东方财富Web API | HTTP GET |
| 新闻 | 东方财富 | 网页抓取 |
| LLM分析 | MiMo/GLM/DeepSeek/Gemini | HTTP POST |

## 六、信号评分体系

### 技术分析评分 (-45 ~ +45)

| 指标 | 多头加分 | 空头减分 |
|------|----------|----------|
| MA排列 | 多头+15, 偏多+10 | 空头-15, 偏空-10 |
| MACD | 金叉+5, 红柱+3 | 死叉-5, 绿柱-3 |
| RSI | 超卖(<30)+8, 偏低+4 | 超买(>70)-8, 偏高-4 |
| KDJ | 金叉+5, J<0 +3 | 死叉-5, J>100 -3 |
| 布林带 | 下轨支撑 | 上轨压力 |
| K线形态 | 锤子线/吞没+3~4 | 上吊线/吞没-3~4 |

### 多因子融合

```
综合评分 = 技术×40% + 资金×20% + 新闻×25% + 基本面×15%

≥ 60   → 🔴 强烈买入 (推送)
30~60  → 🟠 买入 (推送)
-30~30 → ⚪ 观望 (不推送)
-60~-30→ 🟢 卖出 (推送)
≤ -60  → 🔵 强烈卖出 (推送)
```

## 七、运行命令

```bash
# 实时监控
python main.py --mode once      # 执行一次
python main.py --mode loop      # 持续监控

# Web面板
python main.py --mode web       # 启动Streamlit面板

# 回测
python main.py --mode backtest --backtest-start 2025-01-01

# 参数优化
python main.py --mode optimize

# 旧版入口（已弃用）
python monitor.py --interval 60
```
