#!/bin/bash
# =============================================================================
# OrangeServer 开发模式启动脚本
# =============================================================================
# 用法：
#   ./start.sh start      # 后台启动 init.py（开发模式）
#   ./start.sh stop       # 停 init.py
#   ./start.sh restart    # 重启
#   ./start.sh status     # 查看状态
#   ./start.sh tail       # 实时跟踪日志
#
# Python3 解释器解析优先级：
#   1) 环境变量 OGS_PYTHON3_PATH（推荐，运维可控）
#   2) 环境变量 PYTHON3_PATH（兼容老方式）
#   3) $(command -v python3) 自动检测
# 历史兼容说明: 旧版 install.sh 曾 sed 改写本文件的 python3_path,
# v4.0 起已移除该逻辑, 现在只按下方 env 变量 / PATH 顺序解析。
# =============================================================================

# Python3 解释器路径（install.sh 会 sed 修改本行；OgsBackend 标准路径兼容）
python3_path="${OGS_PYTHON3_PATH:-${PYTHON3_PATH:-$(command -v python3)}}"
# Python3 自检：避免空字符串 / sed 残留默认值启动失败
if [ -z "$python3_path" ] || [ ! -x "$python3_path" ]; then
  log_error "找不到 python3 解释器，请设置 OGS_PYTHON3_PATH 或 PYTHON3_PATH 环境变量"
  log_error "当前 python3_path=$python3_path"
  exit 1
fi

dir=$(cd "$(dirname "$0")";pwd)
log=$dir/log

# PID 文件（用于 stop/status 精确定位）
PID_FILE=$log/orange_server.pid

mkdir -p "$log"

now() { date "+%Y-%m-%d %H:%M:%S"; }

function log_info()  { echo "[$(now)] [INFO]  $1"; }
function log_warn()  { echo "[$(now)] [WARN]  $1" >&2; }
function log_error() { echo "[$(now)] [ERROR] $1" >&2; }

function is_running() {
  [ -f "$PID_FILE" ] || return 1
  local pid=$(cat "$PID_FILE" 2>/dev/null)
  [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null
}

function start_app() {
  if is_running; then
    log_warn "orange_server 已在运行 (PID=$(cat $PID_FILE))"
    return 0
  fi

  log_info "--------------------------------------------------"
  log_info "启动 orange_server (dev mode) ......."
  log_info "--------------------------------------------------"

  : > $log/start_init.log
  # ⓘ 死代码清理: start_run.log 从未被代码引用, 不再预创建

  # REVIEW-15-P0-2: setsid 让进程脱离父 shell 的进程组，
  #   父 shell 退出不影响子进程存活；systemd/supervisor 仍可见
  # REV48 (P1-4): start.sh 的 dir 一直是 ops/ (脚本所在), init.py 在 backend/, 加 cd ../backend
  cd "${dir}/../backend" && setsid $python3_path init.py >>$log/start_init.log 2>&1 &
  echo $! > $PID_FILE
  sleep 3

  if is_running; then
    log_info "orange_server 启动成功 (PID=$(cat $PID_FILE))"
    log_info "日志: tail -f $log/start_init.log"
  else
    log_error "orange_server 启动失败，查看日志:"
    tail -20 $log/start_init.log
    return 1
  fi
}

function stop_app() {
  log_info "--------------------------------------------------"
  log_info "停止 orange_server ......."
  log_info "--------------------------------------------------"

  if [ ! -f "$PID_FILE" ]; then
    log_warn "PID 文件不存在，未运行?"
    return 0
  fi

  local pid=$(cat "$PID_FILE")
  # REVIEW-15-P0-2: TERM 信号让 gevent 排空 WebSocket；
  #   KILL 兜底防僵尸进程
  if kill -0 "$pid" 2>/dev/null; then
    kill -TERM "$pid" 2>/dev/null
    for i in 1 2 3 4 5 6 7 8 9 10; do
      kill -0 "$pid" 2>/dev/null || break
      sleep 1
    done
    if kill -0 "$pid" 2>/dev/null; then
      log_warn "TERM 10s 未退出，强 KILL"
      kill -KILL "$pid" 2>/dev/null
    fi
    log_info "orange_server 已停止 (PID=$pid)"
  else
    log_warn "PID=$pid 不存在，清理 PID 文件"
  fi
  rm -f "$PID_FILE"
}

function status_app() {
  if is_running; then
    log_info "orange_server 运行中 (PID=$(cat $PID_FILE))"
    ps -p $(cat $PID_FILE) -o pid,ppid,etime,cmd 2>/dev/null
  else
    log_warn "orange_server 未运行"
    return 1
  fi
}

function tail_app() {
  if [ -f "$log/start_init.log" ]; then
    tail -f $log/start_init.log
  else
    log_warn "日志文件不存在: $log/start_init.log"
  fi
}

case "${1:-}" in
  'start')   start_app ;;
  'stop')    stop_app ;;
  'restart') stop_app; start_app ;;
  'status')  status_app ;;
  'tail')    tail_app ;;
  *)
    echo "用法: $0 {start|stop|restart|status|tail}"
    echo "生产环境请用: supervisorctl start orange:*"
    exit 1
    ;;
esac