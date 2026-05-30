# A股量化监控系统 v4

实时监控A股市场，AI多模型深度分析，智能选股推荐，策略自进化，多渠道信号推送，Web面板管理。

## 核心功能

| 功能 | 说明 |
|------|------|
| 实时监控 | 分层扫描：持仓股15s/核心股30s/普通股60s/ETF 120s/动态池120s，价格波动(≥0.5%)即时触发 |
| **AI深度分析** | 多模型协作：MiMo选股/GLM技术分析/DeepSeek新闻/Gemini回测归因 |
| 智能选股 | 每日自动推荐TOP10短线机会（基于资金流入+涨幅+板块热度） |
| 动态监控池 | 推荐股票自动加入，3天过期自动移除 |
| 资金流向 | 每日TOP20个股资金流入 + 板块热度分析 |
| **策略自进化** | 基于回测数据自动调整策略参数，实现系统自我优化 |
| **回测数据库** | SQLite存储信号/回测结果/策略版本/进化日志 |
| 收盘汇总 | 每日15:00自动推送当日行情+信号+后续关注点 |
| 持仓管理 | Web面板添加/编辑/卖出/删除持仓 |
| 多渠道推送 | 钉钉（免费无限）+ Server酱（微信） |
| **板块热力图** | 行业板块/概念板块涨跌热力图，一目了然 |
| **选股筛选器** | 多条件筛选：涨跌幅/换手率/成交额/市盈率 |
| **风险监控** | 持仓盈亏汇总、资产配置饼图、仓位分析 |

## Web 面板

启动命令：
```bash
# 方式一：通过 main.py 启动
.venv/bin/python main.py --mode web

# 方式二：直接启动 Streamlit
.venv/bin/streamlit run src/web/app.py --server.port 8501 --theme.base dark
```

访问 `http://localhost:8501`，侧边栏导航六个页面：

| 页面 | 功能 |
|------|------|
| 🏠 **自选股** | 自选股实时行情表、持仓盈亏汇总、点击进入个股详情（K线/盘口/技术面/资金流/新闻） |
| 📈 **大盘行情** | 大盘指数、行业板块热力图、概念板块热力图、涨跌幅榜、换手率榜、板块资金流向 |
| 🔍 **选股筛选** | 多条件筛选器（涨跌幅/换手率/成交额/市盈率）、排序、结果导出 |
| ⚠️ **风险监控** | 持仓盈亏汇总、资产配置饼图、仓位明细、最近交易信号 |
| 📡 **信号中心** | 快速扫描按钮、信号评分卡片、历史信号时间线 |
| 📊 **回测数据** | 信号统计分布、回测结果、策略版本管理、进化日志 |

### 个股详情页

点击自选股名称进入详情页，包含：
- 实时行情卡片（今开/最高/最低/昨收/成交量/成交额/换手率/市盈率）
- 带技术指标的K线图（MA/BOLL/MACD/RSI/KDJ）
- 盘口深度（买卖五档 + 阶段表现）
- 技术面分析（仪表盘评分 + 关键价位 + 信号明细）
- 资金流向（主力/超大单/大单/中单/小单）
- 新闻资讯

## 日度运行节奏

```
08:50-09:15  每日推荐（智能选股TOP10 → 推送）
09:15-11:30  上午盘实时监控（分层扫描 → AI分析 → 买卖信号推送）
11:30-13:00  午间休市休眠
13:00-15:00  下午盘实时监控（分层扫描 → AI分析 → 买卖信号推送）
15:00-15:15  收盘汇总（行情+资金流向+收益回填+后续关注点 → 推送）
15:15-次日   休眠至下一个交易日（周日触发策略进化评估）
周末/假日    全天休眠
```

## 快速开始

```bash
# 1. 克隆仓库
git clone <repo-url>
cd a_stock_monitor

# 2. 创建虚拟环境（需要 Python 3.11）
uv venv .venv --python 3.11
source .venv/bin/activate

# 3. 安装依赖
pip install -e ".[web,notify]"

# 4. 编辑配置
vim config/settings.yaml   # 配置LLM、推送渠道、自选股

# 5. 启动监控（后台运行）
.venv/bin/python -u monitor.py --interval 60 >> logs/monitor.log 2>&1 &

# 6. 启动Web面板
.venv/bin/python main.py --mode web
```

## AI 多模型架构

系统采用多模型协作架构，不同任务分配给最适合的模型：

| 任务类型 | 模型 | 职责 |
|----------|------|------|
| 选股推荐 | MiMo | 短线机会分析、板块热度解读 |
| 技术分析 | GLM-5.1 | 技术指标深度分析、趋势研判 |
| 新闻分析 | DeepSeek | 新闻情感分析、政策解读 |
| 回测归因 | Gemini | 信号准确性评估、策略优化建议 |

## 推送策略

| 信号 | 推送 |
|------|------|
| 🔴 strong_buy（评分≥60） | 钉钉 + Server酱 |
| 🟠 buy（评分≥30） | 钉钉 + Server酱 |
| ⚪ hold（观望） | 不推送 |
| 🟢 sell（评分≤-30） | 钉钉 + Server酱 |
| 🔵 strong_sell（评分≤-60） | 钉钉 + Server酱 |

## 项目结构

```
a_stock_monitor/
├── main.py                     # 统一入口（监控/回测/优化/Web）
├── monitor.py                  # 旧版主程序（兼容保留）
├── config/settings.yaml        # 配置文件（不提交git）
├── src/
│   ├── core/
│   │   ├── config.py           # 配置管理（单例）
│   │   └── base.py             # 基础数据结构
│   ├── data/
│   │   ├── collector.py        # 行情/K线/资金流采集（腾讯API+AKShare）
│   │   ├── news.py             # 新闻采集（东方财富）
│   │   ├── manager.py          # 数据管理器（带缓存）
│   │   ├── cache.py            # 内存缓存
│   │   └── store.py            # SQLite存储（信号/交易/持仓/K线）
│   ├── analysis/
│   │   ├── technical.py        # 技术分析（MA/MACD/RSI/KDJ/布林带/K线形态）
│   │   └── signal_engine.py    # 多因子信号融合引擎
│   ├── scanner/
│   │   ├── smart_picker.py     # 智能选股（东方财富API）
│   │   └── market_scanner.py   # 全市场扫描器
│   ├── strategy/               # 策略模块（回测用）
│   │   ├── base.py             # 策略基类
│   │   ├── technical.py        # 技术策略
│   │   ├── capital_flow.py     # 资金流策略
│   │   ├── news_sentiment.py   # 新闻情绪策略
│   │   ├── ensemble.py         # 集成策略
│   │   ├── multi_timeframe.py  # 多周期策略
│   │   ├── volume_pattern.py   # 量价形态策略
│   │   └── trend_strength.py   # 趋势强度策略
│   ├── engine/
│   │   ├── live.py             # 实时交易引擎
│   │   ├── backtest.py         # 回测引擎
│   │   └── signal_bus.py       # 信号总线
│   ├── execution/
│   │   ├── broker.py           # 模拟券商
│   │   ├── order.py            # 订单管理
│   │   └── position.py         # 持仓管理
│   ├── risk/
│   │   ├── manager.py          # 风险管理器
│   │   └── rules.py            # 风险规则
│   ├── analytics/
│   │   ├── metrics.py          # 绩效指标
│   │   └── report.py           # 报告生成
│   ├── optimization/
│   │   └── grid_search.py      # 参数网格搜索
│   ├── llm/
│   │   ├── depot.py            # 多模型LLM调度中心
│   │   ├── analyzer.py         # AI量化分析引擎
│   │   ├── evolver.py          # 策略自进化引擎
│   │   └── client.py           # LLM客户端
│   ├── notify/
│   │   └── notifier.py         # 多渠道推送
│   └── web/
│       ├── app.py              # Streamlit Web面板（v4，侧边栏导航+6页面）
│       ├── styles.py           # 全局CSS样式
│       ├── charts.py           # 图表组件（K线/仪表盘/热力图/资金流）
│       ├── helpers.py          # 工具函数（格式化/市场数据API）
│       ├── pages/
│       │   ├── market.py       # 大盘行情页（板块热力图/涨跌榜）
│       │   ├── screener.py     # 选股筛选器页
│       │   └── risk.py         # 风险监控页
│       ├── dashboard.py        # 旧版Web面板（兼容保留）
│       └── portfolio.py        # 旧版持仓管理（兼容保留）
├── data/
│   ├── holdings.json           # 旧版持仓数据
│   ├── watch_pool.json         # 旧版关注池
│   ├── stock_monitor.db        # SQLite数据库（信号/交易/持仓/K线）
│   └── backtest.db             # 旧版回测数据库
├── logs/                       # 日志文件
└── pyproject.toml
```

## 信号评分体系

| 策略 | 权重 | 说明 |
|------|------|------|
| 技术分析 | 40% | MA排列/MACD/RSI/KDJ/布林带/K线形态 |
| 资金流向 | 20% | 主力净流入/流出 |
| 新闻情绪 | 25% | LLM分析新闻情感（仅持仓股） |
| 基本面 | 15% | PE/营收等基础指标 |

### 信号阈值

| 综合评分 | 操作 |
|---------|------|
| ≥ 60 | 🔴 强烈买入 |
| 30 ~ 60 | 🟠 买入 |
| -30 ~ 30 | ⚪ 观望 |
| -60 ~ -30 | 🟢 卖出 |
| ≤ -60 | 🔵 强烈卖出 |

## 配置说明

`config/settings.yaml`（已加入 `.gitignore`）：

```yaml
watchlist:           # 自选股(stocks + funds)
llm_models:          # 多模型配置
llm:                 # 旧版单模型配置（兼容）
ai_analysis:         # AI分析开关
notify:              # 推送渠道
signal:              # 信号阈值 + 权重
schedule:            # 扫描间隔
risk:                # 风控参数
backtest:            # 回测参数
```

## 外部依赖

```
akshare >= 1.14     # A股数据
pandas >= 2.0       # 数据处理
requests            # HTTP
rich                # CLI输出
pyyaml              # 配置
openai              # LLM客户端
streamlit           # Web面板
plotly              # 图表
pydantic            # 数据验证
apscheduler         # 调度
beautifulsoup4      # 网页解析
mplfinance          # K线图
```
