# A股智能量化监控系统

基于本地大模型的A股+基金智能监控系统，融合技术分析、新闻舆情、政策解读，
实时生成买卖信号、建仓/清仓建议、止盈止损点位。

## 快速开始

```bash
# 1. 安装依赖
cd /Users/tianye/Downloads/a_stock_monitor
uv pip install --python .venv/bin/python akshare pandas pandas-ta plotly mplfinance openai rich pyyaml streamlit

# 2. 编辑配置 (添加自选股)
vim config/settings.yaml

# 3. 运行模式选择

# 单次扫描
python start.py --mode once

# 持续监控 (每5分钟扫描)
python start.py --mode loop --interval 5

# Web面板
python start.py --mode web
```

## 功能特性

- 📊 实时行情监控 (A股+ETF基金)
- 📈 技术指标分析 (MA/MACD/RSI/KDJ/布林带/ATR)
- 🕯️ K线形态识别 (锤子线/吞没/十字星)
- 💰 资金流向分析 (主力/大单/北向)
- 📰 新闻舆情分析 (本地大模型驱动)
- 🎯 多因子信号融合 (技术40%+资金20%+消息25%+基本面15%)
- ⚠️ 风险管理 (ATR止损/分批止盈/仓位控制)
- 📱 多渠道通知 (企业微信/钉钉/Server酱/Bark)
- 🖥️ Web监控面板 (交互式K线+信号流)

## 配置说明

编辑 `config/settings.yaml`:

```yaml
# 添加自选股
watchlist:
  stocks:
    - code: "600519"
      name: "贵州茅台"

# 配置本地大模型 (可选)
llm:
  api_base: "http://localhost:11434/v1"  # Ollama
  model: "qwen2.5"

# 配置通知 (至少一个)
notify:
  wecom_webhook: "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxx"
```

## 信号解读

| 评分 | 操作 | 仓位建议 |
|------|------|----------|
| >60 | 强烈买入 | 15-20% |
| 30~60 | 买入 | 5-15% |
| -30~30 | 观望 | 0% |
| -60~-30 | 卖出 | 减仓 |
| <-60 | 强烈卖出 | 清仓 |
