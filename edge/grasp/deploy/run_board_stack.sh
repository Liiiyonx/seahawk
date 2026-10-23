#!/usr/bin/env bash
# ============================================================
# 板子侧统一启动器：厂商 ROS 栈 + （board_agent | 作业台）
# ============================================================
# 为什么需要它
# ------------
# 这块 ArmPi FPV 板上，ROS Melodic 只装在 **python2.7** 下，而厂商 IK
# （kinematics.ik_inverse_kinematics）**只在 python3.6 下可用**（实测：
# py2.7 那份 .so 报 `undefined symbol: _Py_FalseStruct`）。所以板上天然是
# 双解释器分工：
#
#   board_agent.py  (py2.7) —— 订阅相机/舵机话题、下发脉宽、回读舵机状态
#   ik_worker.py    (py3.6) —— 由 board_agent 拉起的子进程，专门算 IK
#
# 本脚本负责把「ROS 栈 + board_agent」这一套拉起来。作业台（标定/示教用）
# 走 --console，跑 py3.6 且自己直连本机 ROS。
#
# 用法（板上）
# -----------
#   bash run_board_stack.sh --agent                 # ROS 栈 + board_agent（平台派单用）
#   bash run_board_stack.sh --console               # ROS 栈 + 作业台 :8090（标定/示教）
#   bash run_board_stack.sh --stack-only --check    # 只起 ROS 栈并自检，不跑业务进程
#   bash run_board_stack.sh --no-stack --agent      # 假定 ROS 栈已在跑，只起 agent
#
# ★ 不要启动厂商 start_functions.launch：它会把 object_sorting / tracking /
#   warehouse 等 7 个 required=true 节点全拉起来，抢走相机与控制权。
set -o pipefail

# ---------------------------------------------------------------- CRLF 自愈
# ★ 实测坑（必读）：**Windows 的 scp.exe 在传输时会把 LF 转成 CRLF**。
#   后果极其隐蔽：脚本本身照样能跑，但 bash 数组/变量里会带上不可见的 \r，
#   于是 `roslaunch "${ARR[1]}"` 报
#       RLException: [pkg/x.launch] is not a launch file name
#   而**手动敲同样的字面量命令却完全正常** —— 因为字面量不带 \r。
#   本机仓库里的文件是纯 LF（.gitattributes 保证），是传输环节加的。
#   这里在启动时自愈一次，避免依赖"传输工具的行为"。
strip_cr() {
  local f
  for f in "$@"; do
    if [ -f "$f" ] && grep -q $'\r' "$f" 2>/dev/null; then
      sed -i 's/\r$//' "$f"
      echo "[preflight] 已去除 $f 的 CRLF"
    fi
  done
}
strip_cr "$0"
strip_cr "$(dirname "$0")/run_autopick.sh"

MODE=""            # agent | console
START_STACK=1
CHECK_ONLY=0
KEEP_STACK=0
ROS_SETUP="${OCEANUS_ROS_SETUP:-/home/ubuntu/armpi_fpv/devel/setup.bash}"
ROS_DISTRO_SETUP="/opt/ros/melodic/setup.bash"
LOG_DIR="${OCEANUS_LOG_DIR:-/tmp/oceanus-board}"
TOPIC_TIMEOUT="${OCEANUS_TOPIC_TIMEOUT:-60}"
AGENT_DIR="${OCEANUS_AGENT_DIR:-/home/ubuntu/oceanus_board}"
AGENT_PORT="${OCEANUS_AGENT_PORT:-8093}"
PI_USER_HOME="${HOME:-/home/ubuntu}"
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"   # …/edge

while [[ $# -gt 0 ]]; do
  case "$1" in
    --agent)        MODE="agent"; shift ;;
    --console)      MODE="console"; shift ;;
    --no-stack)     START_STACK=0; shift ;;
    --check)        CHECK_ONLY=1; shift ;;
    --keep-stack)   KEEP_STACK=1; shift ;;
    --topic-timeout) TOPIC_TIMEOUT="$2"; shift 2 ;;
    --ros-setup)    ROS_SETUP="$2"; shift 2 ;;
    --log-dir)      LOG_DIR="$2"; shift 2 ;;
    --agent-dir)    AGENT_DIR="$2"; shift 2 ;;
    --port)         AGENT_PORT="$2"; shift 2 ;;
    -h|--help)      sed -n '2,30p' "$0"; exit 0 ;;
    *) echo "未知参数：$1" >&2; exit 2 ;;
  esac
done

log()  { echo "[$(date '+%F %T')] $*"; }
warn() { echo "[$(date '+%F %T')] ! $*" >&2; }
die()  { echo "[$(date '+%F %T')] x $*" >&2; exit "${2:-2}"; }

mkdir -p "$LOG_DIR" 2>/dev/null || true

# ---------------------------------------------------------------- ROS 环境
[[ -f "$ROS_DISTRO_SETUP" ]] || die "找不到 $ROS_DISTRO_SETUP（没装 ROS Melodic？）"
[[ -f "$ROS_SETUP" ]] || die "找不到厂商工作空间 $ROS_SETUP（先 catkin_make）"
# ★ 不能开 set -u：ROS 的 setup.bash 链里引用未定义变量（ROS_DISTRO）
# shellcheck disable=SC1090
source "$ROS_DISTRO_SETUP"
# shellcheck disable=SC1090
source "$ROS_SETUP"
log "ROS 已 source：master=${ROS_MASTER_URI:-<未设置>}"

# ---------------------------------------------------------------- 回收
# ★ launch 用**绝对路径**，不用 `pkg/file.launch` 相对形式。
#   实测：同样一条命令，相对形式在这块板上时好时坏（`rospack find` 明明能找到包），
#   绝对路径则稳定成功。启动脚本要的是确定性，所以显式解析成绝对路径。
resolve_launch() {
  local pkg="$1" file="$2" root
  root="$(rospack find "$pkg" 2>/dev/null)" || return 1
  [[ -n "$root" && -f "$root/launch/$file" ]] || return 1
  printf '%s/launch/%s' "$root" "$file"
}

BE_ROOT="$(rospack find armpi_fpv_bringup 2>/dev/null || true)"
SC_ROOT="$(rospack find hiwonder_servo_controllers 2>/dev/null || true)"
[[ -n "$BE_ROOT" ]] || die "rospack 找不到 armpi_fpv_bringup —— 厂商工作空间没 source 好？"
[[ -n "$SC_ROOT" ]] || die "rospack 找不到 hiwonder_servo_controllers"

LAUNCHES=(
  "$BE_ROOT/launch/start_dependence.launch"
  "$BE_ROOT/launch/start_camera.launch"
  "$SC_ROOT/launch/controller_manager.launch"
)
LAUNCH_NAMES=(dependence camera servo)
for f in "${LAUNCHES[@]}"; do
  [[ -f "$f" ]] || die "launch 文件不存在：$f"
done

STACK_STARTED=0
ROSCORE_PID=""

stop_stack() {
  [[ "$STACK_STARTED" -eq 1 ]] || return 0
  [[ "$KEEP_STACK" -eq 1 ]] && { warn "--keep-stack：保留 ROS 栈"; return 0; }
  log "回收 ROS 栈"
  local pids
  for f in "${LAUNCHES[@]}"; do
    pids="$(pgrep -f -- "$f" 2>/dev/null || true)"
    [[ -n "$pids" ]] && kill -TERM $pids 2>/dev/null || true
  done
  local i
  for i in $(seq 1 20); do
    local alive=""
    for f in "${LAUNCHES[@]}"; do alive="$alive$(pgrep -f -- "$f" 2>/dev/null || true)"; done
    [[ -z "$alive" ]] && break
    sleep 0.25
  done
  for f in "${LAUNCHES[@]}"; do
    pids="$(pgrep -f -- "$f" 2>/dev/null || true)"
    [[ -n "$pids" ]] && kill -KILL $pids 2>/dev/null || true
  done
  # roscore 由本脚本自己起（见下），也由本脚本收
  if [[ -n "$ROSCORE_PID" ]] && kill -0 "$ROSCORE_PID" 2>/dev/null; then
    kill -TERM "$ROSCORE_PID" 2>/dev/null || true
  fi
  log "ROS 栈已退出"
}
trap 'rc=$?; stop_stack; exit $rc' EXIT

wait_topic() {
  local topic="$1" label="$2" frames="${3:-}"
  local deadline=$(( SECONDS + TOPIC_TIMEOUT ))
  while (( SECONDS < deadline )); do
    if rostopic list 2>/dev/null | grep -qx -- "$topic"; then
      if [[ "$frames" == "--frames" ]]; then
        timeout 4 rostopic echo -n 1 "$topic" >/dev/null 2>&1 && { log "  ok $label（$topic 有数据）"; return 0; }
      else
        log "  ok $label（$topic 在列表）"; return 0
      fi
    fi
    sleep 1
  done
  return 1
}

# ---------------------------------------------------------------- 起 ROS 栈
# 起之前先清场。为什么必须做这一步（实测踩过）：
#   上一次 roslaunch 被 timeout / kill 掉时，会自动拉起的 rosmaster 和
#   子节点可能变成孤儿留下。此时**再起 roslaunch 会报
#   `RLException: [...] is not a launch file name`** —— 一个和真实原因
#   （残留 master）完全不相干的报错，极难排查。实测：彻底清掉残留进程后，
#   同样的命令立刻恢复正常。
kill_stale_stack() {
  local pats=("roslaunch" "usb_cam_node" "controller_manager.py" "hiwonder_servo_serialproxy")
  local p
  for p in "${pats[@]}"; do
    pgrep -f -- "$p" >/dev/null 2>&1 && { log "清理残留：$p"; pkill -f -- "$p" 2>/dev/null || true; }
  done
  sleep 2
  # roslaunch 会自动拉 rosmaster；残留 master 会让后续启动报
  # "run_id on parameter server does not match declared run_id"（实测踩到）
  if pgrep -f 'rosmaster' >/dev/null 2>&1; then
    log "清理残留 rosmaster"
    pkill -f rosmaster 2>/dev/null || true
    sleep 3
  fi
}

start_stack() {
  # ★ 必须先把 roscore 单独起稳，再启动其余 launch。
  #   为什么（实测血泪）：如果并行起多个 roslaunch，每个都会"顺手"去拉自己的
  #   rosmaster，互相抢参数服务器，报
  #       RLException: run_id on parameter server does not match declared run_id
  #   表现是三个节点里只有一两个起来，且每次不一样 —— 极难定位。
  #   所以这里：roscore 单独起 → 等它真能应答 → 再顺序起 launch。
  log "启动 roscore"
  setsid roscore >"$LOG_DIR/roscore.log" 2>&1 &
  local i
  for i in $(seq 1 40); do
    if timeout 3 rostopic list >/dev/null 2>&1; then
      log "  roscore 就绪"
      break
    fi
    sleep 1
  done
  if ! timeout 3 rostopic list >/dev/null 2>&1; then
    warn "roscore 30s 内未就绪，见 $LOG_DIR/roscore.log"
    exit 4
  fi

  # 顺序启动：每起一个给一点时间，避免同时争用参数服务器
  local idx
  for idx in 0 1 2; do
    log "  启动 ${LAUNCH_NAMES[$idx]}（${LAUNCHES[$idx]}）"
    setsid roslaunch "${LAUNCHES[$idx]}" >"$LOG_DIR/${LAUNCH_NAMES[$idx]}.log" 2>&1 &
    sleep 4
  done
  STACK_STARTED=1
}

stack_ready() {
  wait_topic /usb_cam/image_raw "相机出帧" --frames || return 1
  wait_topic /servo_controllers/port_id_1/servo_states "舵机回读" || return 1
  return 0
}

stack_has_rlexception() {
  grep -l 'RLException' "$LOG_DIR"/dependence.log "$LOG_DIR"/camera.log "$LOG_DIR"/servo.log 2>/dev/null | head -1
}

if [[ "$START_STACK" -eq 1 ]]; then
  kill_stale_stack
  log "启动厂商 bringup（依赖/相机/舵机控制器；不含 start_functions）"
  start_stack
  log "  日志：$LOG_DIR/{dependence,camera,servo}.log"

  if ! stack_ready; then
    # 区分两种失败：roslaunch 自己没解析成功（多为残留污染）→ 清场重试一次；
    # 真起不来（串口/相机被占）→ 直接报错给日志。
    if [[ -n "$(stack_has_rlexception)" ]]; then
      warn "roslaunch 报 RLException（常见于残留 ROS master 污染），清场后重试一次"
      stop_stack
      STACK_STARTED=0
      kill_stale_stack
      start_stack
      if ! stack_ready; then
        warn "重试仍失败，日志见 $LOG_DIR/*.log"
        exit 4
      fi
    else
      warn "ROS 栈 ${TOPIC_TIMEOUT}s 内未就绪，逐个看日志："
      warn "  tail -n 40 $LOG_DIR/camera.log"
      warn "  tail -n 40 $LOG_DIR/servo.log"
      warn "  tail -n 40 $LOG_DIR/dependence.log"
      exit 4
    fi
  fi
  log "ROS 栈就绪"
else
  log "--no-stack：假定 ROS 栈已在运行"
fi

if [[ "$CHECK_ONLY" -eq 1 ]]; then
  log "--check：栈自检完成，不启动业务进程"
  exit 0
fi

# ---------------------------------------------------------------- 业务进程
case "$MODE" in
  agent)
    [[ -f "$AGENT_DIR/board_agent.py" ]] || die "找不到 $AGENT_DIR/board_agent.py"
    log "启动 board_agent（py2.7，端口 $AGENT_PORT）"
    cd "$AGENT_DIR" || die "无法进入 $AGENT_DIR"
    # board_agent 用 py2.7：ROS 节点 + 舵机下发/回读，IK 交给它拉起的 py3.6 子进程
    exec python2 -u board_agent.py --port "$AGENT_PORT" \
         --params "$AGENT_DIR/board_params.json"
    ;;
  console)
    log "启动作业台（py3.6，:8090）—— 标定 / 放置点示教 / 采集 / 部署"
    cd "$REPO_DIR" || die "无法进入 $REPO_DIR"
    exec python3 -u -m grasp.web.server --config "$REPO_DIR/grasp/config.yaml"
    ;;
  *)
    die "必须指定 --agent 或 --console（或 --check 只验栈）"
    ;;
esac
