#!/usr/bin/env bash
# ============================================================
# 板子重启后一条命令恢复：ROS 栈 + board_agent（常驻）
# ============================================================
# 为什么需要它
# ------------
# 这块 ArmPi FPV 的 RTC 没有电池，掉电/重启后：
#   1. 系统时间会跳回出厂日期（实测停在 2023-12-07）；
#   2. /tmp 被清空 —— 之前放在 /tmp/oceanus-board 的日志全部丢失；
#   3. roslaunch 起的厂商节点、board_agent、ik_worker 全部消失，
#      笔记本上的作业台就会一直报「板上代理不可达」，表现为机械臂失控。
#
# 手工重新拉起要走「清残留 → 起 roscore → 顺序起三个 launch → 起 board_agent」，
# 中间几个坑（并行起 roslaunch 互抢 rosmaster 报 run_id 不匹配、残留进程污染）
# 都在 run_board_stack.sh 里处理掉了。本脚本只负责「脱离 ssh 会话地常驻启动 + 自检」。
#
# 用法（板上）：
#   bash /home/ubuntu/oceanus/edge/grasp/deploy/board_bringup.sh
#
# 自检通过会打印 AGENT_READY。
set -o pipefail

REPO="${OCEANUS_REPO:-/home/ubuntu/oceanus}"
LOG_DIR="${OCEANUS_LOG_DIR:-/tmp/oceanus-board}"
AGENT_PORT="${OCEANUS_AGENT_PORT:-8093}"
RUNNER="$REPO/edge/grasp/deploy/run_board_stack.sh"

mkdir -p "$LOG_DIR" || true

log() { echo "[bringup] $*"; }

[[ -f "$RUNNER" ]] || { echo "找不到 $RUNNER —— 代码没在板上？" >&2; exit 2; }

log "清理旧进程（上一次可能留下的孤儿会污染 roslaunch）"
for p in 'roslaunch' 'rosmaster' 'usb_cam_node' 'controller_manager.py' 'board_agent.py' 'ik_worker.py'; do
  pkill -f -- "$p" 2>/dev/null && log "  killed: $p"
done
sleep 3

log "后台常驻启动 run_board_stack.sh --agent"
cd "$REPO/edge" || exit 2
nohup setsid bash "$RUNNER" --agent --log-dir "$LOG_DIR" \
    >"$LOG_DIR/agent_runner.log" 2>&1 < /dev/null &
disown 2>/dev/null || true

log "等 board_agent 监听 :$AGENT_PORT（最多 150s）"
for _ in $(seq 1 50); do
  ss -lnt 2>/dev/null | grep -q ":$AGENT_PORT" && break
  sleep 3
done

if ! ss -lnt 2>/dev/null | grep -q ":$AGENT_PORT"; then
  echo "board_agent 没起来，日志尾部：" >&2
  tail -20 "$LOG_DIR/agent_runner.log" >&2
  exit 4
fi

log "协议自检"
python3 - <<PYEOF
import json, socket, sys
try:
    s = socket.create_connection(("127.0.0.1", $AGENT_PORT), timeout=8)
    f = s.makefile("rwb")
    f.write((json.dumps({"op": "status"}) + "\n").encode()); f.flush()
    st = json.loads(f.readline().decode())
    print("[bringup] ros_error=%s ik_ready=%s frames=%s servos=%s" % (
        st.get("ros_error"), st.get("ik_ready"),
        (st.get("frame") or {}).get("count"), st.get("servo_state_count")))
    if st.get("ros_error") or not st.get("ik_ready"):
        sys.exit(1)
    s.close()
except Exception as exc:
    print("[bringup] 自检失败: %s: %s" % (type(exc).__name__, exc))
    sys.exit(1)
PYEOF
rc=$?
if [[ $rc -ne 0 ]]; then
  echo "自检未通过，看 $LOG_DIR/{dependence,camera,servo}.log" >&2
  exit 4
fi

log "完成。笔记本上的作业台会自动恢复（它会重连）"
echo "AGENT_READY"
