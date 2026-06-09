#!/bin/bash
# 工时报工系统控制脚本

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

APP_NAME="worktime-system"
BACKEND_DIR="$PROJECT_DIR/backend"
APP_PATH="$BACKEND_DIR/app.py"
PID_FILE="$BACKEND_DIR/app.pid"
LOG_FILE_PRE="$BACKEND_DIR/logs"
LOG_FILE="$LOG_FILE_PRE/app.log"

# 判断日志目录是否存在
if [ ! -d "$LOG_FILE_PRE" ]; then
    mkdir -p "$LOG_FILE_PRE"
    echo "Directory $LOG_FILE_PRE created."
fi

start() {
    if [ -f "$PID_FILE" ]; then
        if kill -0 $(cat "$PID_FILE") > /dev/null 2>&1; then
            echo "$APP_NAME is already running."
            return 1
        else
            rm -f "$PID_FILE"
        fi
    fi

    echo "Starting $APP_NAME..."
    cd "$BACKEND_DIR" || exit 1
    
    # 激活conda环境
    if command -v conda &> /dev/null; then
        source "$(conda info --base)/etc/profile.d/conda.sh"
        conda activate tornado
    fi

    nohup python app.py > "$LOG_FILE" 2>&1 &
    echo $! > "$PID_FILE"
    echo "$APP_NAME started with PID $(cat "$PID_FILE")."
    echo "Log file: $LOG_FILE"
    echo "Access: http://localhost:8888"
}

# 停止服务
stop() {
    if ! is_running; then
        echo -e "${YELLOW} 服务未运行${NC}"
        log "服务未运行，无需停止"
        return 1
    fi

    PID=$(cat "$PID_FILE")
    echo -e "${YELLOW}正在停止服务 (PID: $PID)...${NC}"
    log "开始停止服务，PID: $PID"

    kill "$PID"
    
    # 等待进程结束
    for i in {1..10}; do
        if ! ps -p "$PID" > /dev/null 2>&1; then
            break
        fi
        sleep 1
    done

    # 如果还在运行，强制杀死
    if ps -p "$PID" > /dev/null 2>&1; then
        echo -e "${RED} 进程未响应，强制结束${NC}"
        log "强制结束进程"
        kill -9 "$PID"
    fi

stop() {
    if [ ! -f "$PID_FILE" ] || ! kill -0 $(cat "$PID_FILE") > /dev/null 2>&1; then
        echo "$APP_NAME is stopped."
        return 1
    fi
status() {
    if [ -f "$PID_FILE" ] && kill -0 $(cat "$PID_FILE") > /dev/null 2>&1; then
        echo "$APP_NAME is running with PID $(cat "$PID_FILE")."
        echo "Log file: $LOG_FILE"
        echo "Access: http://localhost:8888"
    else
        echo "$APP_NAME is stopped."
    fi
}

restart() {
    stop
    sleep 2
    start控制脚本

使用方法:
    $0 {start|stop|restart|status|logs|cleanup|help}

命令说明:
    start    - 启动服务
    stop     - 停止服务
    restart  - 重启服务
    status   - 查看服务状态
    logs     - 查看实时日志
    cleanup  - 清理30天前的日志
logs() {
    if [ -f "$LOG_FILE" ]; then
        tail -f "$LOG_FILE"
    else
        echo "Log file not found: $LOG_FILE"
    fi
}

cleanup() {
    echo "Cleaning logs older than 30 days..."
    find "$LOG_FILE_PRE" -name "*.log.*" -type f -mtime +30 -delete
    echo "Cleanup completed."c

exit 0
case "$1" in
    start)
        start
        ;;
    stop)
        stop
        ;;
    status)
        status
        ;;
    restart)
        restart
        ;;
    logs)
        logs
        ;;
    cleanup)
        cleanup
        ;;
    *)
        echo "Usage: $0 {start|stop|status|restart|logs|cleanup}"