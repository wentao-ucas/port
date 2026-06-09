SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

APP_NAME="aat-data-collector"
APP_PATH="$SCRIPT_DIR/../aat_data_collector.py"
PID_FILE="$SCRIPT_DIR/app.pid"
LOG_FILE_PRE="/opt/afhm/output/logs"
LOG_FILE="$LOG_FILE_PRE/aat-data-output.log"
CRON_CMD="*/2 * * * * sh $SCRIPT_DIR/control.sh aat_data_monitor"
CRON_CMD_DEL="control.sh aat_data_monitor"

# 判断日志目录是否存在
if [ ! -d "$LOG_FILE_PRE" ]; then
	# 如果目录不存在，则创建目录
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
    nohup python3.9 "$APP_PATH" > "$LOG_FILE" 2>&1 &
    echo $! > "$PID_FILE"
    echo "$APP_NAME started with PID $(cat "$PID_FILE")."

    # 检查crontab任务是否存在
    if ! crontab -l | grep -qF "$CRON_CMD_DEL"; then
        (crontab -l 2>/dev/null; echo "$CRON_CMD") | crontab -
        echo "Crontab task added to monitor $APP_NAME."
    else
        echo "Crontab task already exists, no need to add."
    fi
}


stop() {
    if [ ! -f "$PID_FILE" ] || ! kill -0 $(cat "$PID_FILE") > /dev/null 2>&1; then
        echo "$APP_NAME is stopped."
        return 1
    fi

    echo "Stopping $APP_NAME..."
    kill -9 $(cat "$PID_FILE")
    rm -f "$PID_FILE"
    echo "$APP_NAME stopped."

    # 删除监控程序的crontab任务
    crontab -l 2>/dev/null | grep -v "$CRON_CMD_DEL" | crontab -
    echo "Crontab task removed."
}

status() {
    if [ -f "$PID_FILE" ] && kill -0 $(cat "$PID_FILE") > /dev/null 2>&1; then
        echo "$APP_NAME is running with PID $(cat "$PID_FILE")."
    else
        echo "$APP_NAME is stopped."
    fi
}

aat_data_monitor() {
    if [ ! -f "$PID_FILE" ] || ! kill -0 $(cat "$PID_FILE") > /dev/null 2>&1; then
        echo "$APP_NAME is not running. Restarting..."
        start
    else
        echo "$APP_NAME is running."
    fi
}


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
        stop
        start
        ;;
    aat_data_monitor)
        aat_data_monitor
        ;;
    *)
        echo "Usage: $0 {start|stop|status|restart|aat_data_monitor}"
        exit 1
        ;;
esac

exit 0
