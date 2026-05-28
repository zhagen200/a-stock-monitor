#!/bin/bash
# A股监控服务 - 带日志输出
# 用法: ./run_monitor.sh          (前台运行)
#       ./run_monitor.sh bg       (后台运行，日志到 logs/monitor.log)

cd "$(dirname "$0")"

LOG_DIR="logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/monitor.log"

# 激活 venv
source .venv/bin/activate

if [ "$1" = "bg" ]; then
    echo "启动后台监控，日志: $LOG_FILE"
    nohup python -u monitor.py --interval 5 >> "$LOG_FILE" 2>&1 &
    echo "PID: $!"
    echo "查看日志: tail -f $LOG_FILE"
else
    python -u monitor.py --interval 5 2>&1 | tee -a "$LOG_FILE"
fi
