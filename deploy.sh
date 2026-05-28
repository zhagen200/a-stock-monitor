#!/bin/bash
# A股量化交易系统 - 部署运行脚本
# 用法:
#   ./deploy.sh             启动 loop 持续监控 (前台)
#   ./deploy.sh bg          后台运行 (screen)
#   ./deploy.sh web         启动 Web 面板
#   ./deploy.sh once        立即扫描一次
#   ./deploy.sh stop        停止后台运行
#   ./deploy.sh status      查看运行状态

cd "$(dirname "$0")"
PROJECT_DIR=$(pwd)
VENV="$PROJECT_DIR/.venv/bin/python"
SESSION_NAME="astock_monitor"
LOG_DIR="$PROJECT_DIR/logs"

mkdir -p "$LOG_DIR"

export NO_PROXY="*"
export no_proxy="*"

case "${1:-loop}" in
  once)
    $VENV main.py 2>&1
    ;;
  web)
    echo "🌐 启动 Web 面板: http://localhost:8501"
    $VENV main.py --mode web
    ;;
  bg)
    screen -dmS "$SESSION_NAME" \
      bash -c "cd $PROJECT_DIR && exec $VENV main.py --mode loop --interval 5"
    echo "✅ 后台监控已启动 (screen session: $SESSION_NAME)"
    echo "   查看日志: tail -f $LOG_DIR/monitor.log"
    echo "   进入终端: screen -r $SESSION_NAME"
    ;;
  stop)
    screen -S "$SESSION_NAME" -X quit 2>/dev/null
    pkill -f "main.py --mode loop" 2>/dev/null || true
    launchctl unload ~/Library/LaunchAgents/com.astock.monitor.plist 2>/dev/null || true
    echo "🛑 已停止"
    ;;
  status)
    if screen -list | grep -q "$SESSION_NAME"; then
      echo "✅ 运行中 (screen)"
      screen -list | grep "$SESSION_NAME"
    elif launchctl list | grep -q "com.astock.monitor"; then
      echo "✅ 运行中 (launchd)"
    else
      echo "❌ 未运行"
    fi
    ;;
  autostart)
    launchctl load ~/Library/LaunchAgents/com.astock.monitor.plist
    echo "✅ 已设置为登录时自启动"
    echo "   查看日志: tail -f $LOG_DIR/launchd.log"
    ;;
  loop|*)
    echo "🔍 启动持续监控 (按 Ctrl+C 停止)"
    $VENV main.py --mode loop --interval "${2:-5}" 2>&1 | tee -a "$LOG_DIR/monitor.log"
    ;;
esac
