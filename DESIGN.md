# 系统设计文档

## 一、架构设计

### 1.1 四层架构

```
┌─────────────────────────────────────────────────────────────┐
│                        入口层                                │
│            main.py / start.py / deploy.sh                   │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐   │
│  │ 数据层    │  │ 策略层    │  │ 风控层    │  │ 执行层    │   │
│  │          │  │          │  │          │  │          │   │
│  │ collector│  │technical │  │ rules    │  │ broker   │   │
│  │ manager  │  │capital   │  │ manager  │  │ order    │   │
│  │ store    │  │multi_tf  │  │          │  │ position │   │
│  │ cache    │  │volume    │  │          │  │          │   │
│  │          │  │trend     │  │          │  │          │   │
│  │          │  │news      │  │          │  │          │   │
│  │          │  │ensemble  │  │          │  │          │   │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘   │
│       │              │              │              │        │
│       └──────────────┴──────────────┴──────────────┘        │
│                              │                               │
│                    ┌─────────▼─────────┐                    │
│                    │    信号总线        │                    │
│                    │   SignalBus       │                    │
│                    │  策略→风控→通知→执行 │                   │
│                    └─────────┬─────────┘                    │
│                              │                               │
│              ┌───────────────┼───────────────┐              │
│              ▼               ▼               ▼              │
│     ┌────────────┐  ┌────────────┐  ┌────────────┐        │
│     │ 通知推送    │  │ 回测引擎    │  │ Web面板    │        │
│     │ 4渠道      │  │ 历史验证    │  │ Streamlit  │        │
│     └────────────┘  └────────────┘  └────────────┘        │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### 1.2 数据流

```
定时扫描:
  腾讯API → get_realtime_quote() → 缓存(30s)
  AKShare  → get_kline()          → SQLite持久化
  AKShare  → get_fund_flow()      → 缓存(5min)
  LLM      → analyze_news()       → 情绪评分

策略处理:
  strategy.generate(data) → StrategySignal
  ensemble.generate()     → TradeSignal(加权融合)

执行链路:
  SignalBus.process(signal) → RiskManager.check()
                            → Notifier.send()
                            → Broker.execute() (可选)
```

## 二、模块详解

### 2.1 数据层 (`src/data/`)

**collector.py** — 数据采集
- `get_realtime_quote()` — 腾讯行情API，实时股价
- `get_kline()` — 腾讯K线API + AKShare回退，支持日/周/月
- `get_intraday_kline()` — AKShare分钟K线，支持15/30/60分钟
- `get_fund_flow()` — 3源回退: AKShare → 东方财富HTTP → 行情估算
- `get_market_index()` — 大盘指数(上证/深证/创业板)
- `get_sector_flow()` — 板块资金流向

**store.py** — SQLite存储
- 4表: `kline_data` / `signals` / `trades` / `positions`
- WAL模式，支持并发读
- K线按(code, period, date)唯一索引

**manager.py** — 统一数据入口
- 内存缓存(TTL)+DB持久化双层
- 支持force_refresh强制刷新

**cache.py** — TTL内存缓存
- `get_or_set(key, fn, ttl)` 模式

### 2.2 策略层 (`src/strategy/`)

**BaseStrategy** — 抽象基类
```python
class BaseStrategy(ABC):
    name: str
    weight: float
    generate(data: Dict) -> StrategySignal
    get_required_data() -> List[str]
```

**TechnicalStrategy** — 技术分析 (权重0.30)
- 趋势评分(±50): MA排列4档 + MACD金叉死叉 + MACD柱方向 + MA20偏离
- 动量评分(±30): RSI 4档区间 + KDJ金叉死叉 + J值超限
- 量能评分(±20): 放量上涨/下跌 + 量能趋势
- 市场状态调节: bull×1.0 / oscillate×0.9 / bear×0.7
- soft归一化: score×1.5 → clip(-100,100)

**CapitalFlowStrategy** — 资金流向 (权重0.15)
- 主力净流入额/占比评分

**MultiTimeframeStrategy** — 多时间框架 (权重0.15)
- 日线/60分/15分趋势方向一致性检查
- 三周期同向: +30分; 两周期同向: +15分
- 短线斜率修正

**VolumePatternStrategy** — 成交量形态 (权重0.15)
- 缩量见底 + 量价齐升 + 放量滞涨 + 量价背离 + 底部放量

**TrendStrengthStrategy** — 趋势强度 (权重0.10)
- ADX > 25判断强趋势
- DMI方向判断
- 布林带上下轨支撑/压力
- 连续阴阳线计数

**NewsSentimentStrategy** — 新闻情绪 (权重0.15, 需LLM)
- LLM分析新闻标题情感
- 返回±100评分

**EnsembleStrategy** — 集成引擎
- 遍历所有策略，加权累加
- 权重归一化: 最终评分 / 总权重
- 置信度: 策略方向一致时提升20%
- 仓位: strong_buy ≤20%, buy ≤10%

### 2.3 风控层 (`src/risk/`)

**规则链 (可组合)**

| 规则 | 作用 | 参数 |
|------|------|------|
| PositionLimitRule | 单股/行业仓位上限 | max_single_pct, max_industry_pct |
| MarketRegimeFilter | 熊市过滤买入信号 | — |
| ConsecutiveLossRule | 连续亏损暂停交易 | max_losses |
| VolatilityRule | 高波动率过滤 | — |

### 2.4 执行层 (`src/execution/`)

**OrderFactory** — 订单工厂
- `create_market_order()` — 市价单
- `create_limit_order()` — 限价单

**Broker接口** — 可替换券商实现
- `MockBroker` — 模拟交易(0.025%佣金)
- `RealBroker` — 实盘抽象基类
- `XtQuantBroker` — 迅投QMT对接桩

**PositionManager** — 持仓管理
- 增删改查 + 市值实时更新

### 2.5 核心层 (`src/core/`)

**base.py** — 数据类定义
- `TradeSignal` — 综合交易信号
- `StrategySignal` — 单个策略信号
- `Order` — 订单
- `Position` — 持仓
- `BacktestResult` — 回测结果

**config.py** — 配置管理
- YAML文件读取，`.`号路径访问
- `settings.get("signal.weights.technical")`

### 2.6 引擎层 (`src/engine/`)

**SignalBus** — 信号总线
1. 接收信号 → 2. 风控检查 → 3. 入库 → 4. 通知推送 → 5. 回调

**BacktestEngine** — 回测引擎
- 预加载数据 → 逐日回放
- 信号生成 → 风控检查 → 模拟交易
- 绩效计算: 收益率/夏普/最大回撤/胜率/盈亏比

**LiveEngine** — 实盘引擎
- 盘中扫描 + ATR止盈止损 + 大盘状态
- LLM新闻分析(持仓股)

### 2.7 优化层 (`src/optimization/`)

**GridSearchOptimizer** — 网格搜索
- `ParamGrid`定义参数空间
- `product()`笛卡尔积搜索
- 支持4种目标函数: sharpe / total_return / win_rate / composite

## 三、通知推送

| 渠道 | 方式 | 限制 |
|------|------|------|
| 企业微信 | Webhook机器人(Markdown) | 无 |
| 钉钉 | Webhook机器人(Markdown) | 无 |
| Server酱 | API推送 | 5次/日 |
| Bark | HTTP GET | 无 |

推送策略: 仅非`hold`信号触发通知，避免骚扰。

## 四、部署

### 4.1 后台运行
```bash
./deploy.sh bg          # screen后台
./deploy.sh stop        # 停止
./deploy.sh autostart   # launchd开机自启
```

### 4.2 launchd自启
Plist: `~/Library/LaunchAgents/com.astock.monitor.plist`
- `RunAtLoad`: 登录时启动
- `KeepAlive`: 崩溃后重启
- `ThrottleInterval`: 30秒重试间隔

## 五、配置文件

`config/settings.yaml` (被.gitignore保护，不提交密钥)

```yaml
llm:          # LLM配置
notify:       # 4个通知渠道
schedule:     # 扫描间隔
signal:       # 信号阈值 + 6策略权重
risk:         # 风控参数
backtest:     # 回测资金/佣金
watchlist:    # 自选股(stocks + funds)
```

## 六、SQLite Schema

```sql
kline_data(code, period, date, open, close, high, low, volume)
signals(id, code, name, timestamp, action, score, price,
        technical_score, capital_score, news_score, ...)
trades(id, code, name, direction, price, volume, amount, timestamp, fee)
positions(code, name, volume, cost_price, current_price, profit_pct, ...)
```

## 七、依赖

```
akshare >= 1.14    # A股数据
pandas >= 2.0       # 数据处理
requests            # HTTP
rich                # CLI输出
pyyaml              # 配置
openai              # LLM客户端
streamlit           # Web面板(可选)
```
