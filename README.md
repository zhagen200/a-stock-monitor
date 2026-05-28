# A股量化交易系统

多策略融合的A股量化交易系统，支持自选股扫描、技术分析、资金流向、LLM新闻情绪、回测验证、参数优化，可对接实盘券商。

```
数据层 → 策略层 → 风控层 → 执行层
                   ↕
              信号总线 → 通知推送
```

## 快速安装

```bash
# 1. 克隆仓库
git clone git@github.com:zhagen200/a-stock-monitor.git
cd a-stock-monitor

# 2. 创建虚拟环境
python3.11 -m venv .venv
source .venv/bin/activate

# 3. 安装依赖
pip install akshare pandas requests rich pyyaml openai beautifulsoup4 apscheduler
# Web面板 (可选)
pip install streamlit

# 4. 创建配置文件
cp config/settings.yaml.example config/settings.yaml
vim config/settings.yaml    # 编辑自选股和通知

# 5. 首次扫描测试
python main.py
```

## 运行模式

| 命令 | 说明 |
|------|------|
| `python main.py` | 扫描全部自选股一次 |
| `python main.py --scan-code 600519` | 扫描单只股票 |
| `python main.py --mode loop --interval 5` | 持续监控(每5分钟,前台) |
| `python main.py --mode backtest` | 回测验证 |
| `python main.py --mode optimize` | 参数优化 |
| `python main.py --mode web` | Web监控面板(:8501) |

## 策略体系

| 策略 | 默认权重 | 评分范围 | 说明 |
|------|---------|---------|------|
| 技术分析 | 0.30 | -100~100 | MA排列(4档)/MACD金叉死叉/MACD柱方向/RSI(4档)/KDJ/量能/市场状态(bull/oscillate/bear) |
| 资金流向 | 0.15 | -100~100 | 主力净流入(3源回退: AKShare→东方财富→行情估算) |
| 多时间框架 | 0.15 | -40~40 | 日线/60分/15分趋势一致性，三周期同向加仓 |
| 成交量形态 | 0.15 | -30~30 | 缩量见底/量价齐升/放量滞涨/量价背离/底部放量 |
| 趋势强度 | 0.10 | -30~30 | ADX趋势强度/DMI方向/布林带上下轨/连续阴阳线 |
| 新闻情绪 | 0.15 | -100~100 | LLM分析新闻标题情感(需配置LLM) |

### 信号阈值

| 综合评分 | 操作 | 建议仓位 |
|---------|------|---------|
| ≥ 55 | 强烈买入 | ≤ 20% |
| 25 ~ 55 | 买入 | ≤ 10% |
| -25 ~ 25 | 观望 | 0 |
| -55 ~ -25 | 卖出 | 减仓 |
| ≤ -55 | 强烈卖出 | 清仓 |

## 配置说明

配置文件 `config/settings.yaml`（已加入 `.gitignore`，不提交密钥）：

### 自选股

```yaml
watchlist:
  stocks:
    - code: "002640"
      name: "跨境通"
      cost: 5.6       # 持仓成本(选填,有则启用LLM分析和仓位监控)
      shares: 2400     # 持仓数量(选填)
    - code: "600519"
      name: "贵州茅台"
  funds:
    - code: "510300"
      name: "沪深300ETF"
```

### 策略权重

```yaml
signal:
  thresholds:
    buy: 25
    sell: -25
    strong_buy: 55
    strong_sell: -55
  weights:
    technical: 0.30
    capital_flow: 0.15
    multi_timeframe: 0.15
    volume_pattern: 0.15
    trend_strength: 0.10
    news_sentiment: 0.15
```

### 通知渠道（至少配一个）

```yaml
notify:
  enabled: true
  wecom_webhook: "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxx"
  dingtalk_webhook: "https://oapi.dingtalk.com/robot/send?access_token=xxx"
  serverchan_key: "SCTxxx"
  bark_url: "https://api.day.app/xxx"
```

| 渠道 | 方式 | 限制 |
|------|------|------|
| 企业微信 | 群机器人Webhook | 无限制 |
| 钉钉 | 群机器人Webhook | 无限制 |
| Server酱 | API推送 | 5次/日 |
| Bark | iOS推送 | 无限制 |

### 风控参数

```yaml
risk:
  max_position_pct: 20       # 单只股票最大仓位(%)
  max_industry_pct: 30       # 单行业最大仓位(%)
  consecutive_loss_limit: 3  # 连续亏损N次后暂停交易
```

### LLM 新闻分析（可选）

```yaml
llm:
  enabled: true
  api_base: "http://localhost:11434/v1"   # Ollama / 任何OpenAI兼容API
  model: "qwen2.5"
  api_key: "not-needed"
```

## 接入实盘券商

### 方案一：迅投QMT（推荐）

**支持券商：** 国金、国信、华泰、招商、中信建投等30+家支持QMT量化终端

**步骤：**

1. **开权限** — 联系券商开通QMT量化交易权限
2. **安装QMT** — 下载安装券商提供的QMT终端并登录
3. **安装xtquant** — 在QMT终端的Python环境或本机安装：
   ```bash
   pip install xtquant
   ```
4. **配置账户** — `config/settings.yaml`：
   ```yaml
   broker:
     type: xtquant
     account_id: "你的资金账号"
     password: "你的交易密码"
   ```
5. **启动自动交易**：
   ```bash
   python main.py --mode loop --auto-execute
   ```

> **安全建议：** 先不加 `--auto-execute` 跑几天观察信号准确性，确认稳定后再开启自动下单。

### 方案二：自定义券商

继承 `RealBroker` 实现接口：

```python
from src.execution.broker import RealBroker, OrderResult
from src.core.base import Order

class MyBroker(RealBroker):
    def connect(self) -> bool:
        return True

    def buy(self, order: Order) -> OrderResult:
        # 调用你的交易API
        ...

    def sell(self, order: Order) -> OrderResult:
        ...
```

### 交易流程

```
信号生成 → 风控检查 → 通知推送 → 人工确认 → Broker执行
                                     ↓
                             auto_execute=true
                             时自动跳过确认
```

## 部署

### macOS 部署

```bash
# 后台运行 (screen)
./deploy.sh bg
# 查看状态
./deploy.sh status
# 进入控制台 (Ctrl+A D 分离)
screen -r astock_monitor
# 停止
./deploy.sh stop

# 设置开机自启 (launchd)
./deploy.sh autostart
```

### 生产级部署 (Linux)

```bash
# systemd 服务 (参考)
cat > /etc/systemd/system/astock-monitor.service <<EOF
[Unit]
Description=A股量化交易系统
After=network.target

[Service]
Type=simple
WorkingDirectory=/opt/a-stock-monitor
ExecStart=/opt/a-stock-monitor/.venv/bin/python main.py --mode loop
Restart=always
RestartSec=30

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now astock-monitor
```

### 日志

```bash
tail -f logs/monitor.log      # 运行日志
tail -f logs/launchd.log      # launchd日志
tail -f logs/push_counter.db  # 推送计数
```

## 数据存储

SQLite 数据库 `data/stock_monitor.db`:

| 表 | 说明 | 关键字段 |
|----|------|---------|
| `kline_data` | K线数据 | code, period(daily/60min/15min), date, OHLCV |
| `signals` | 信号历史 | action, score, 各策略细分评分, 置信度 |
| `trades` | 交易记录 | direction, price, volume, fee |
| `positions` | 持仓 | volume, cost_price, profit_pct |

## 项目结构

```
├── main.py                     # 统一入口
├── deploy.sh                   # 部署脚本
├── config/settings.yaml        # 配置文件(不提交git)
├── src/
│   ├── core/                   # 核心定义
│   │   ├── base.py             #   DataClass: TradeSignal/Order/Position
│   │   └── config.py           #   YAML配置读取
│   ├── data/                   # 数据层
│   │   ├── collector.py        #   行情/K线/资金流采集(腾讯API+AKShare)
│   │   ├── store.py            #   SQLite存储
│   │   ├── manager.py          #   统一数据入口+缓存
│   │   ├── cache.py            #   TTL内存缓存
│   │   └── news.py             #   新闻采集
│   ├── strategy/               # 策略层
│   │   ├── technical.py        #   技术分析(MA/MACD/RSI/KDJ)
│   │   ├── capital_flow.py     #   资金流向
│   │   ├── multi_timeframe.py  #   多时间框架
│   │   ├── volume_pattern.py   #   成交量形态
│   │   ├── trend_strength.py   #   趋势强度
│   │   ├── news_sentiment.py   #   新闻情绪(LLM)
│   │   └── ensemble.py         #   加权融合引擎
│   ├── risk/                   # 风控层
│   │   ├── rules.py            #   4条风控规则
│   │   └── manager.py          #   规则链遍历
│   ├── execution/              # 执行层
│   │   ├── broker.py           #   券商接口(Mock/QMT)
│   │   ├── order.py            #   订单工厂
│   │   └── position.py         #   持仓管理
│   ├── engine/                 # 引擎层
│   │   ├── live.py             #   实盘引擎
│   │   ├── backtest.py         #   回测引擎
│   │   └── signal_bus.py       #   信号总线
│   ├── optimization/           # 优化
│   │   └── grid_search.py      #   网格参数搜索
│   ├── analytics/              # 分析
│   │   ├── metrics.py          #   绩效指标
│   │   └── report.py           #   报告生成
│   ├── web/                    # Web面板
│   │   └── app.py              #   Streamlit
│   ├── llm/                    # LLM
│   │   └── client.py           #   OpenAI兼容客户端
│   └── notify/                 # 通知
│       └── notifier.py         #   4渠道推送
├── DESIGN.md                   # 设计文档
└── pyproject.toml              # 项目配置
```
