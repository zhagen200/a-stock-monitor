# A股智能量化监控系统 v2

实时监控A股市场，智能选股推荐，多渠道信号推送，Web面板管理。

## 核心功能

| 功能 | 说明 |
|------|------|
| 实时监控 | 交易时段每60秒扫描，自动识别买卖信号 |
| 智能选股 | 每日自动推荐TOP10短线机会（基于资金流入+涨幅+板块热度） |
| 动态监控池 | 推荐股票自动加入，3天过期自动移除 |
| 资金流向 | 每日TOP20个股资金流入 + 板块热度分析 |
| 收盘汇总 | 每日15:00自动推送当日行情+信号+后续关注点 |
| 持仓管理 | Web面板添加/编辑/卖出/删除持仓 |
| 多渠道推送 | 钉钉（免费无限）+ Server酱（微信） |

## 日度运行节奏

```
08:50-09:15  每日推荐（智能选股TOP10 → 推送）
09:15-11:30  上午盘实时监控（60秒/次 → 买卖信号推送）
11:30-13:00  午间休市休眠
13:00-15:00  下午盘实时监控（60秒/次 → 买卖信号推送）
15:00-15:15  收盘汇总（行情+资金流向+后续关注点 → 推送）
15:15-次日   休眠至下一个交易日
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
.venv/bin/python -u monitor.py --interval 60 > /dev/null 2>&1 &

# 6. 启动Web面板
.venv/bin/streamlit run src/web/dashboard.py --server.port 8501 --server.headless true &
```

## 运行命令

```bash
# 后台持续监控（推荐）
.venv/bin/python -u monitor.py --interval 60

# 执行一次扫描
.venv/bin/python monitor.py --once

# 手动每日推荐
.venv/bin/python monitor.py --recommend

# 生成资金流向报表
.venv/bin/python monitor.py --report

# 生成收盘汇总
.venv/bin/python monitor.py --summary
```

## 推送策略

| 信号 | 推送 |
|------|------|
| 🔴 strong_buy（评分≥60） | 钉钉 + Server酱 |
| 🟠 buy（评分≥30） | 钉钉 + Server酱 |
| ⚪ hold（观望） | 不推送 |
| 🟢 sell（评分≤-30） | 钉钉 + Server酱 |
| 🔵 strong_sell（评分≤-60） | 钉钉 + Server酱 |
| 每日推荐 | 钉钉 + Server酱 |
| 收盘汇总 | 钉钉 + Server酱 |

## Web 面板

访问 `http://localhost:8501`，三个页面：

| 页面 | 功能 |
|------|------|
| 📈 行情分析 | 选择股票查看K线、技术分析、资金流向、持仓盈亏 |
| 💼 持仓管理 | 添加/编辑成本数量/全部卖出/删除 |
| 👁️ 关注池 | 手动添加关注股票/移除，查看智能推荐 |

## 配置说明

`config/settings.yaml`（已加入 `.gitignore`）：

### 持仓与关注

```yaml
watchlist:
  stocks:
    - code: "002195"
      name: "岩山科技"
      cost: 9.0         # 持仓成本
      shares: 1000       # 持仓数量
    - code: "002640"
      name: "跨境通"
      cost: 5.6
      shares: 2400
    - code: "600580"
      name: "卧龙电驱"   # 无cost/shares则只监控不计盈亏
  funds:
    - code: "510300"
      name: "沪深300ETF"
    - code: "510500"
      name: "中证500ETF"
```

### LLM 新闻分析

```yaml
llm:
  api_base: "https://token-plan-cn.xiaomimimo.com/v1"
  model: "mimo-v2.5-pro"
  api_key: "your-key"
  enabled: true
```

> LLM 仅对持仓股（岩山科技、跨境通、卧龙电驱）启用新闻分析，减少API调用。

### 通知推送

```yaml
notify:
  enabled: true
  dingtalk_webhook: "https://oapi.dingtalk.com/robot/send?access_token=xxx"
  serverchan_key: "SCTxxx"
```

| 渠道 | 方式 | 限制 |
|------|------|------|
| 钉钉 | 群机器人Webhook | 免费无限 |
| Server酱 | API推送 | 免费版有限额 |
| 企业微信 | 群机器人Webhook | 免费无限 |
| Bark | iOS推送 | 免费无限 |

## 数据存储

```
data/
├── holdings.json      # 持仓数据（Web面板管理）
└── watch_pool.json    # 关注池（手动+自动推荐）
logs/
├── monitor.log        # 运行日志（纯文本，Python logging）
└── watchlist_pool.json # 动态监控池（推荐股票，3天过期）
```

## 项目结构

```
a_stock_monitor/
├── monitor.py                  # 主程序（日度节奏控制）
├── config/settings.yaml        # 配置文件（不提交git）
├── src/
│   ├── data/
│   │   ├── collector.py        # 行情/K线/资金流采集（腾讯API+AKShare）
│   │   └── news.py             # 新闻采集（东方财富）
│   ├── analysis/
│   │   ├── technical.py        # 技术分析（MA/MACD/RSI/KDJ/布林带/K线形态）
│   │   └── signal_engine.py    # 多因子信号融合引擎
│   ├── scanner/
│   │   └── smart_picker.py     # 智能选股（资金流入+涨幅+板块热度）
│   ├── llm/
│   │   └── client.py           # LLM客户端（OpenAI兼容API）
│   ├── notify/
│   │   └── notifier.py         # 多渠道推送（钉钉/Server酱/企微/Bark）
│   └── web/
│       ├── dashboard.py        # Streamlit Web面板（行情/持仓/关注池）
│       └── portfolio.py        # 持仓与关注池数据管理
├── data/                       # 持仓/关注池 JSON 数据
├── logs/                       # 日志文件
├── pyproject.toml
├── README.md
└── DESIGN.md
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

## 智能选股策略

每日 09:00 自动扫描全市场，筛选条件：
1. 主力资金净流入 > 1000万
2. 涨幅 2%~8%（不追涨停，不抄底）
3. 排除ST股和停牌股
4. 涨幅 3%~6% 加分（适中区间）
5. 主力净流入越大评分越高

推荐股票自动加入监控池，3天后无关注价值自动移除。
