# A股量化交易系统重构设计

## 一、总体架构

```
┌──────────────────────────────────────────────────────────────────────┐
│                         A股量化交易系统                                │
├──────────────────────────────────────────────────────────────────────┤
│                                                                       │
│  ┌──────────────────────────────────────────────────────────┐        │
│  │                   引擎层 Engine                             │        │
│  │  ┌──────────────┐  ┌──────────────┐  ┌────────────────┐  │        │
│  │  │  回测引擎      │  │  实盘引擎      │  │  信号总线       │  │        │
│  │  │  Backtest     │  │  LiveEngine  │  │  SignalBus    │  │        │
│  │  └──────┬───────┘  └──────┬───────┘  └───────┬────────┘  │        │
│  └─────────┼─────────────────┼──────────────────┼────────────┘        │
│            │                 │                  │                      │
│  ┌─────────▼─────────────────▼──────────────────▼────────────┐        │
│  │                    策略层 Strategy                           │       │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────┐  │        │
│  │  │ 技术策略  │ │ 资金流策略 │ │ 新闻策略  │ │ 集成策略      │  │        │
│  │  │Technical │ │ Capital  │ │ News     │ │ Ensemble     │  │        │
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────────┘  │        │
│  └──────────────────────┬────────────────────────────────────┘        │
│                         │                                             │
│  ┌──────────────────────▼────────────────────────────────────┐        │
│  │                    风控层 Risk                               │       │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────┐  │        │
│  │  │ 仓位风控  │ │ 大盘风控  │ │ 止损风控  │ │ 规则引擎      │  │        │
│  │  │Position  │ │ Market   │ │ StopLoss │ │ Rule Engine  │  │        │
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────────┘  │        │
│  └──────────────────────┬────────────────────────────────────┘        │
│                         │                                             │
│  ┌──────────────────────▼────────────────────────────────────┐        │
│  │                    执行层 Execution                          │       │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────┐  │        │
│  │  │ 订单管理  │ │ Broker   │ │ 持仓管理  │ │ 交易记录存储  │  │        │
│  │  │ Order    │ │ Mock/Real│ │Position  │ │ Trade Log    │  │        │
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────────┘  │        │
│  └──────────────────────┬────────────────────────────────────┘        │
│                         │                                             │
│  ┌──────────────────────▼────────────────────────────────────┐        │
│  │                    数据层 Data                               │       │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────┐  │        │
│  │  │ 行情采集  │ │ K线存储   │ │ 新闻采集  │ │ 数据缓存     │  │        │
│  │  │Collector │ │ Kline DB │ │ News     │ │ Cache        │  │        │
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────────┘  │        │
│  └──────────────────────┬────────────────────────────────────┘        │
│                         │                                             │
│  ┌──────────────────────▼────────────────────────────────────┐        │
│  │                 存储层 (SQLite)                             │       │
│  │  kline_data | signals | trades | analytics | config         │        │
│  └─────────────────────────────────────────────────────────────┘        │
│                                                                       │
│  ┌──────────────────────┐  ┌──────────────────┐  ┌────────────────┐  │
│  │  Web面板 Streamlit   │  │  通知推送 Notifier │  │ 绩效分析        │  │
│  │  (保留+升级)          │  │  (全保留)          │  │ Analytics      │  │
│  └──────────────────────┘  └──────────────────┘  └────────────────┘  │
│                                                                       │
└──────────────────────────────────────────────────────────────────────┘
```

## 二、模块详细设计

### 2.1 数据层 `src/data/`

**保留内容：** 
- `StockDataCollector` 的腾讯行情/AKShare 数据采集逻辑（重构为更健壮）
- `NewsCollector` 的新闻采集逻辑

**新增/改造：**

`store.py` — 统一存储接口
```python
class KlineStore:
    """K线数据持久化"""
    def save_kline(code, period, df)       # 增量写入 SQLite
    def load_kline(code, period, start, end)  # 读取
    def has_data(code, period, date)        # 检查是否已有数据
    def get_latest_date(code, period)       # 获取最新日期
```

`cache.py` — 内存缓存层
```python
class DataCache:
    """内存缓存，减少API调用"""
    def get(key, ttl=60)    # 过期自动失效
    def set(key, value, ttl=60)
    def invalidate(pattern)
```

`manager.py` — 数据调度
```python
class DataManager:
    """统一数据入口，协调各数据源"""
    def get_kline(code, period, force_refresh=False)
    def get_realtime_quote(code)
    def get_fund_flow(code)
    def batch_update(watchlist)  # 批量刷新
```

**SQLite 数据库 Schema:**
```sql
-- K线数据
CREATE TABLE kline_data (
    code TEXT NOT NULL,
    period TEXT NOT NULL,  -- daily/weekly/monthly
    date TEXT NOT NULL,
    open REAL, close REAL, high REAL, low REAL, volume REAL,
    PRIMARY KEY (code, period, date)
);

-- 信号记录
CREATE TABLE signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL, name TEXT,
    timestamp TEXT NOT NULL,
    action TEXT, score REAL, price REAL,
    technical_score REAL, capital_score REAL,
    news_score REAL, fundamental_score REAL,
    confidence REAL, position_pct REAL,
    stop_loss REAL, take_profit_1 REAL, take_profit_2 REAL,
    reasons TEXT,  -- JSON array
    strategy_name TEXT,  -- 哪个策略生成的
    is_backtest INTEGER DEFAULT 0
);

-- 交易记录
CREATE TABLE trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL, name TEXT,
    direction TEXT NOT NULL,  -- buy/sell
    price REAL, volume INTEGER,
    amount REAL,  -- 成交金额
    timestamp TEXT NOT NULL,
    signal_id INTEGER,  -- 关联信号
    fee REAL DEFAULT 0,
    note TEXT
);

-- 仓位
CREATE TABLE positions (
    code TEXT PRIMARY KEY,
    name TEXT,
    volume INTEGER NOT NULL DEFAULT 0,
    cost_price REAL NOT NULL DEFAULT 0,
    current_price REAL DEFAULT 0,
    profit_pct REAL DEFAULT 0,
    profit_amount REAL DEFAULT 0,
    updated_at TEXT
);

-- 绩效快照（每日）
CREATE TABLE daily_metrics (
    date TEXT PRIMARY KEY,
    total_assets REAL,
    cash REAL,
    position_value REAL,
    daily_return REAL,
    cumulative_return REAL
);
```

### 2.2 策略层 `src/strategy/`

新增模块，统一策略接口：

```python
class BaseStrategy(ABC):
    """策略基类"""
    name: str
    weight: float  # 集成策略中的权重
    
    @abstractmethod
    def generate(self, data: Dict) -> StrategySignal:
        """生成策略信号"""
    
    @abstractmethod
    def get_required_data(self) -> List[str]:
        """返回所需数据列表"""
```

**具体策略：**
1. `technical.py` — 技术面（基于现有 `TechnicalAnalyzer` 改造，增加多时间框架）
2. `capital_flow.py` — 资金流（主力净流入/流出趋势）
3. `news_sentiment.py` — 新闻情绪（基于 LLM 分析）
4. `ensemble.py` — 多策略集成（加权融合，类似现有 SignalEngine 但更灵活）

```python
class StrategySignal:
    code: str
    strategy_name: str
    action: str  # strong_buy/buy/hold/sell/strong_sell
    score: float  # 0~100 或 -100~100
    confidence: float
    detail: Dict  # 额外数据
    timestamp: datetime
```

**多时间框架分析**（重要升级）：
- 日线级别：趋势识别
- 60分钟线：波段操作信号
- 15分钟线：日内买卖点
- 三框架信号一致时，置信度大幅提升

**市场状态识别**（新增）：
```python
def detect_market_regime(index_kline: pd.DataFrame) -> str:
    """识别市场状态: 牛市/震荡/熊市"""
    # 基于 MA120 方向 + 指数相对 MA 位置 + 波动率
```

### 2.3 风控层 `src/risk/`

```python
class RiskManager:
    """风控管理器"""
    
    def check(self, signal: StrategySignal, context: TradingContext) -> RiskResult:
        """检查信号是否通过风控"""
        for rule in self.rules:
            result = rule.check(signal, context)
            if not result.passed:
                return result
        return RiskResult(passed=True)
```

**风控规则（可组合）：**
1. `PositionLimitRule` — 单票最大仓位 ≤20%，同行业 ≤30%
2. `MarketRegimeFilter` — 熊市只允许 strong_buy，牛市放宽
3. `StopLossRule` — 已有持仓是否触发止损
4. `ConsecutiveLossRule` — 连续亏损 N 次暂停交易
5. `VolatilityRule` — 波动过大时禁止开仓

### 2.4 执行层 `src/execution/`

```python
class Broker(ABC):
    @abstractmethod
    def buy(self, order: Order) -> OrderResult
    @abstractmethod
    def sell(self, order: Order) -> OrderResult
    @abstractmethod
    def get_position(self, code) -> Position

class MockBroker(Broker):
    """模拟券商（回测+仿真用）"""

class PositionManager:
    """持仓管理"""
    def load_from_db()
    def update_price(code, price)
    def get_total_value()
    def get_profit_pct(code)
```

**订单模型：**
```python
@dataclass
class Order:
    code: str
    direction: Literal["buy", "sell"]
    order_type: Literal["market", "limit"]
    price: float
    volume: int
    reason: str
    signal_id: Optional[int]
```

### 2.5 引擎层 `src/engine/`

**信号总线 `signal_bus.py`：**
```python
class SignalBus:
    """信号处理管道：策略 → 风控 → 执行"""
    
    def process(self, signal: TradeSignal) -> Optional[ExecutedOrder]:
        1. 风控过滤
        2. 通知推送（保留现有 Notifier）
        3. 如果是 strong_buy/strong_sell → 自动生成 Order
        4. 记录到 signals 表
```

**回测引擎 `backtest.py`：**
```python
class BacktestEngine:
    """基于历史数据的回测"""
    
    def run(self, strategy, codes, start_date, end_date, initial_cash) -> BacktestResult:
        # 按日期回放
        # 逐日：获取当日K线 → 策略生成信号 → 风控检查 → 执行
        # 记录所有交易 → 计算绩效
```

**绩效指标 `BacktestResult`：**
- 总收益率、年化收益率
- 最大回撤、夏普比率、卡尔玛比率
- 胜率、盈亏比
- 交易次数、平均持仓天数
- 月度收益率分布

**实盘引擎 `live.py`：**
```python
class LiveEngine:
    """实盘循环引擎"""
    def __init__(self):
        self.data_manager = DataManager()
        self.strategies = [TechnicalStrategy(), CapitalFlowStrategy(), ...]
        self.ensemble = EnsembleStrategy(self.strategies)
        self.risk_manager = RiskManager(...)
        self.signal_bus = SignalBus(...)
        self.notifier = Notifier(...)
        self.position_manager = PositionManager(...)
    
    def run(self, interval=5):
        while True:
            for stock in watchlist:
                signal = self.ensemble.generate(stock)
                self.signal_bus.process(signal)
            sleep(interval * 60)
```

### 2.6 绩效分析 `src/analytics/`

```python
class PerformanceAnalytics:
    def calculate_metrics(trades, equity_curve) -> Dict
    def generate_report(start_date, end_date) -> str
    def plot_equity_curve()  # Plotly 图表
```

**指标：**
- 收益率曲线
- 最大回撤曲线
- 月度收益热力图
- 品种盈亏分布
- 信号准确率统计

### 2.7 Web面板 `src/web/`（保留+升级）

**保留：** 现有 Streamlit 框架、K线图、技术指标可视化

**新增页面：**
1. 首页 — 持仓概览 + 今日信号 + 市场状态
2. 回测页 — 策略选择 → 运行回测 → 展示结果
3. 绩效页 — 收益率曲线、月度收益、交易统计
4. 交易记录页 — 历史交易列表 + 筛选

### 2.8 通知推送（全保留）

保留 `src/notify/notifier.py` 全部内容：
- `Notifier` 类（4个渠道：企业微信/钉钉/Server酱/Bark）
- `PushCounter` 日限额控制
- `send_signal()` 信号格式化推送

### 2.9 配置文件（保留+增强）

保留 `config/settings.yaml` 结构，增加：
```yaml
# 新增配置项
database:
  path: data/stock_monitor.db

risk:
  max_position_pct: 20
  max_industry_pct: 30
  consecutive_loss_limit: 3

backtest:
  initial_cash: 100000
  commission_rate: 0.00025

strategies:
  technical:
    enabled: true
    weight: 0.4
  capital_flow:
    enabled: true
    weight: 0.2
  news:
    enabled: true
    weight: 0.25
  fundamental:
    enabled: false  # 基本面暂缓
    weight: 0.15
```

## 三、项目文件结构

```
a_stock_monitor/
├── main.py                       # 入口（精简）
├── start.py                      # 启动脚本（保留升级）
├── run_monitor.sh                # Shell启动（保留）
├── config/
│   └── settings.yaml             # 配置（保留+扩展）
├── logs/
│   ├── monitor.log
│   └── push_counter.db
├── data/
│   └── stock_monitor.db          # SQLite 数据库
├── src/
│   ├── __init__.py
│   ├── core/                     # 核心模块
│   │   ├── __init__.py
│   │   ├── base.py               # 基础类型定义
│   │   └── config.py             # 配置管理
│   ├── data/                     # 数据层
│   │   ├── __init__.py
│   │   ├── collector.py          # 行情采集（保留改造）
│   │   ├── news.py               # 新闻采集（保留改造）
│   │   ├── store.py              # 存储层（新增）
│   │   ├── cache.py              # 缓存（新增）
│   │   └── manager.py            # 数据调度（新增）
│   ├── strategy/                 # 策略层（新增）
│   │   ├── __init__.py
│   │   ├── base.py               # 策略基类
│   │   ├── technical.py          # 技术策略
│   │   ├── capital_flow.py       # 资金流策略
│   │   ├── news_sentiment.py     # 新闻情绪策略
│   │   └── ensemble.py           # 集成策略
│   ├── risk/                     # 风控层（新增）
│   │   ├── __init__.py
│   │   ├── manager.py            # 风控管理器
│   │   └── rules.py              # 风控规则集合
│   ├── execution/                # 执行层（新增）
│   │   ├── __init__.py
│   │   ├── order.py              # 订单模型
│   │   ├── broker.py             # 券商接口
│   │   └── position.py           # 持仓管理
│   ├── engine/                   # 引擎层（新增）
│   │   ├── __init__.py
│   │   ├── backtest.py           # 回测引擎
│   │   ├── live.py               # 实盘引擎
│   │   └── signal_bus.py         # 信号总线
│   ├── analytics/                # 绩效分析（新增）
│   │   ├── __init__.py
│   │   ├── metrics.py            # 绩效指标
│   │   └── report.py             # 报告生成
│   ├── analysis/                 # 旧模块（逐步迁移）
│   │   ├── technical.py          # 技术分析（保留，供回测参考）
│   │   └── signal_engine.py      # 信号引擎（保留兼容）
│   ├── llm/                      # LLM（保留）
│   │   ├── __init__.py
│   │   └── client.py
│   ├── notify/                   # 通知（全保留）
│   │   ├── __init__.py
│   │   └── notifier.py
│   └── web/                      # Web面板（保留升级）
│       ├── __init__.py
│       ├── app.py                # 主面板
│       ├── pages/                # 多页面
│       │   ├── backtest.py
│       │   ├── analytics.py
│       │   └── trades.py
│       └── components/           # 可复用组件
│           └── charts.py
└── docs/
    └── superpowers/
        └── specs/
            └── 2026-05-28-quant-system-redesign.md
```

## 四、实施路线图

### Phase 1: 基础设施（3天）

| 任务 | 文件 | 说明 |
|------|------|------|
| 1.1 核心类型定义 | `src/core/base.py`, `config.py` | DataClass 定义：TradeSignal、Order、Position、StrategySignal |
| 1.2 数据存储层 | `src/data/store.py` | SQLite 建表、K线写入/读取、信号存储 |
| 1.3 数据缓存层 | `src/data/cache.py` | 内存缓存 + TTL |
| 1.4 数据管理器 | `src/data/manager.py` | 统一数据入口，替换旧直接调用方式 |

### Phase 2: 策略系统（2天）

| 任务 | 文件 | 说明 |
|------|------|------|
| 2.1 策略基类 | `src/strategy/base.py` | BaseStrategy 抽象类 |
| 2.2 技术策略 | `src/strategy/technical.py` | 多时间框架分析 + 市场状态 |
| 2.3 资金流策略 | `src/strategy/capital_flow.py` | 主力资金趋势 |
| 2.4 新闻情绪策略 | `src/strategy/news_sentiment.py` | LLM 情绪分析包装 |
| 2.5 集成策略 | `src/strategy/ensemble.py` | 加权融合 |

### Phase 3: 风控+执行系统（2天）

| 任务 | 文件 | 说明 |
|------|------|------|
| 3.1 风控管理 | `src/risk/manager.py`, `rules.py` | 规则引擎 |
| 3.2 信号总线 | `src/engine/signal_bus.py` | 策略→风控→执行 管道 |
| 3.3 Broker接口 | `src/execution/broker.py` | MockBroker 先实现 |
| 3.4 订单/持仓管理 | `src/execution/order.py`, `position.py` | 交易记录持久化 |

### Phase 4: 回测引擎（2天）

| 任务 | 文件 | 说明 |
|------|------|------|
| 4.1 回测核心 | `src/engine/backtest.py` | 逐日回放逻辑 |
| 4.2 绩效指标 | `src/analytics/metrics.py` | 夏普/回撤/胜率等 |
| 4.3 回测报告 | `src/analytics/report.py` | 报告生成 |

### Phase 5: 实盘引擎（1天）

| 任务 | 文件 | 说明 |
|------|------|------|
| 5.1 实盘引擎 | `src/engine/live.py` | 整合所有模块的循环引擎 |
| 5.2 入口改造 | `start.py`, `main.py` | 统一入口 |

### Phase 6: Web面板升级（2天）

| 任务 | 文件 | 说明 |
|------|------|------|
| 6.1 面板重构 | `src/web/app.py` | 多页面 Streamlit |
| 6.2 回测页面 | `src/web/pages/backtest.py` | 回测交互 |
| 6.3 绩效页面 | `src/web/pages/analytics.py` | 绩效图表 |

## 五、保留内容清单

1. ✅ `src/notify/notifier.py` — 完整保留
2. ✅ `src/llm/client.py` — 完整保留
3. ✅ `config/settings.yaml` — 扩展保留
4. ✅ `src/data/collector.py` — 采集方法保留，内部改造为更健壮
5. ✅ `src/data/news.py` — 完整保留
6. ✅ `src/web/dashboard.py` — 作为 app.py 的子页面保留（K线图/技术分析）
7. ✅ `start.py` — 升级为多模式入口
8. ✅ `run_monitor.sh` — 保留

## 六、技术债务处理

1. **硬编码腾讯API解析** — 提取到常量配置，增加字段名映射
2. **API Key 明文** — settings.yaml 禁止提交 git，gitignore 增加
3. **旧代码兼容** — 旧 `monitor.py` 和 `src/analysis/` 保留，过渡期并行运行
4. **类型注解** — 所有新代码强制类型注解
5. **异常处理** — 统一异常处理 + 重试机制
