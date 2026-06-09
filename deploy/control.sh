#!/bin/sh
# 工时报工 后端 控制脚本（与 afhm 其它服务一致：nohup + PID + crontab 看门狗）
# 放到 /opt/worktime/backend/bin/control.sh（脚本自动往上一级找 app.py），两台后端各一份
# env.sh / app.py / logs / app.pid 都在上一级 backend/ 目录
#   sh control.sh start | stop | restart | status | monitor
# monitor 由 crontab 每2分钟调用，挂了自动拉起（start 时会自动加这条 cron）

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# app.py 在脚本同级，或脚本放 bin/ 时在上一级；自动定位，两种放法都支持
if [ -f "$SCRIPT_DIR/app.py" ]; then
    APP_DIR="$SCRIPT_DIR"
else
    APP_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
fi

APP_NAME="worktime-backend"
APP_PATH="$APP_DIR/app.py"
PID_FILE="$APP_DIR/app.pid"
LOG_DIR="$APP_DIR/logs"
LOG_FILE="$LOG_DIR/service.out.log"

# 报工时间戳按东八区（避免服务器是 UTC 时算错日期）
export TZ="Asia/Shanghai"

# 生产环境变量(DB/端口/门禁密码/可选 PYTHON_BIN)：env.sh 放在 app.py 同级目录；存在则加载
if [ -f "$APP_DIR/env.sh" ]; then set -a; . "$APP_DIR/env.sh"; set +a; fi

# Python 解释器：服务器已配好 python3.9 环境变量（在 PATH）。如需指定别的，在 env.sh 设 PYTHON_BIN
PYTHON="${PYTHON_BIN:-python3.9}"

CRON_TAG="worktime-backend monitor"
CRON_CMD="*/2 * * * * sh $SCRIPT_DIR/control.sh monitor >/dev/null 2>&1 # $CRON_TAG"

mkdir -p "$LOG_DIR"

is_running() {
    [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null
}

start() {
    if is_running; then
        echo "$APP_NAME already running (PID $(cat "$PID_FILE"))."
        return 0
    fi
    [ -f "$PID_FILE" ] && rm -f "$PID_FILE"

    echo "Starting $APP_NAME (TZ=$TZ, python=$PYTHON)..."
    cd "$APP_DIR" || exit 1
    nohup "$PYTHON" "$APP_PATH" >> "$LOG_FILE" 2>&1 &
    echo $! > "$PID_FILE"
    echo "$APP_NAME started (PID $(cat "$PID_FILE"))."

    # 加看门狗 cron（不存在才加）
    if ! crontab -l 2>/dev/null | grep -qF "$CRON_TAG"; then
        (crontab -l 2>/dev/null; echo "$CRON_CMD") | crontab -
        echo "Watchdog cron added (every 2 min)."
    fi
}

stop() {
    # 先撤看门狗，再杀进程！否则 kill 后 cron 会在 2 分钟内把它拉回来
    crontab -l 2>/dev/null | grep -vF "$CRON_TAG" | crontab -
    echo "Watchdog cron removed."

    if is_running; then
        PID="$(cat "$PID_FILE")"
        echo "Stopping $APP_NAME (PID $PID)..."
        kill "$PID" 2>/dev/null               # 先优雅退出
        i=0
        while kill -0 "$PID" 2>/dev/null && [ $i -lt 10 ]; do sleep 1; i=$((i+1)); done
        kill -0 "$PID" 2>/dev/null && kill -9 "$PID" 2>/dev/null   # 还没退就强杀
        echo "$APP_NAME stopped."
    else
        echo "$APP_NAME not running."
    fi
    rm -f "$PID_FILE"
}

status() {
    if is_running; then
        echo "$APP_NAME is running (PID $(cat "$PID_FILE"))."
    else
        echo "$APP_NAME is stopped."
    fi
}

monitor() {
    if is_running; then
        :
    else
        echo "$(date '+%F %T') $APP_NAME not running, restarting..." >> "$LOG_FILE"
        start
    fi
}

case "$1" in
    start)   start ;;
    stop)    stop ;;
    restart) stop; start ;;
    status)  status ;;
    monitor) monitor ;;
    *) echo "Usage: $0 {start|stop|restart|status|monitor}"; exit 1 ;;
esac
exit 0
