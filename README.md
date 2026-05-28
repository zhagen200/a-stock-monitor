# A股量化交易系统

多策略融合的A股量化交易系统，支持回测、实盘扫描、参数优化、Web监控。

## 架构

```
数据层 (data) → 策略层 (strategy) → 风控层 (risk) → 执行层 (execution)
                              ↕
                         信号总线 (signal_bus)
                              ↕
                        通知推送 (notifier)
```

## 快速开始

```bash
# 扫描全部自选股
./deploy.sh once

# 持续监控(每5分钟)
./deploy.sh            # 前台
./deploy.sh bg         # 后台(screen)

# 回测
python main.py --mode backtest

# 参数优化
python main.py --mode optimize

# Web面板
./deploy.sh web
```

## 策略体系 (6策略融合)

| 策略 | 权重 | 说明 |
|------|------|------|
| 技术分析 | 0.30 | MA排列/MACD/RSI/KDJ/量能/市场状态 |
| 资金流向 | 0.15 | 主力净流入(3源回退) |
| 多时间框架 | 0.15 | 日线/60分/15分趋势一致性 |
| 成交量形态 | 0.15 | 缩量见底/量价背离/底部放量 |
| 趋势强度 | 0.10 | ADX/DMI/布林带位置 |
| 新闻情绪 | 0.15 | LLM分析(需配置) |

## 信号阈值

| 评分 | 操作 | 仓位 |
|------|------|------|
| ≥55 | 强烈买入 | ≤20% |
| ≥25 | 买入 | ≤10% |
| -25~25 | 观望 | 0% |
| ≤-25 | 卖出 | 减仓 |
| ≤-55 | 强烈卖出 | 清仓 |

## 配置 (`config/settings.yaml`)

```yaml
# 自选股
watchlist:
  stocks:
    - code: "600519"
      name: "贵州茅台"
  funds:
    - code: "510300"
      name: "沪深300ETF"

# 策略权重
signal:
  weights:
    technical: 0.30
    capital_flow: 0.15
    multi_timeframe: 0.15
    volume_pattern: 0.15
    trend_strength: 0.10
    news_sentiment: 0.15

# 通知 (至少配置一个)
notify:
  wecom_webhook: "https://qyapi.weixin.qq.com/..."
  dingtalk_webhook: "https://oapi.dingtalk.com/..."
  serverchan_key: "SCT..."
  bark_url: ""           # iOS

# 风控
risk:
  max_position_pct: 20
  max_industry_pct: 30
  consecutive_loss_limit: 3

# LLM (可选)
llm:
  enabled: true
  api_base: "http://localhost:11434/v1"
  model: "qwen2.5"
```

## 部署

```bash
./deploy.sh bg          # screen后台运行
./deploy.sh stop        # 停止
./deploy.sh status      # 状态
./deploy.sh autostart   # 开机自启(launchd)

tail -f logs/monitor.log      # 实时日志
```

## 数据存储

SQLite (`data/stock_monitor.db`):
- `kline_data` — K线数据(支持日/60分/15分)
- `signals` — 信号历史
- `trades` — 交易记录
- `positions` — 持仓

## 通知渠道

| 渠道 | 限额 | 配置字段 |
|------|------|---------|
| 企业微信 | 无限制 | `wecom_webhook` |
| 钉钉 | 无限制 | `dingtalk_webhook` |
| Server酱 | 5次/日 | `serverchan_key` |
| Bark | 无限制 | `bark_url` |
