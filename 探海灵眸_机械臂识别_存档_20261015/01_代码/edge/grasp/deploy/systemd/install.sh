#!/usr/bin/env bash
# ============================================================
# Oceanus 机械臂边缘服务 · systemd 开机自启安装脚本（在树莓派上运行）
# ============================================================
# 用法：
#   sudo bash install.sh --repo /home/pi/oceanus --broker 192.168.137.1 --mode autopick
#
# 必填：
#   --repo      本仓库在树莓派上的根目录（形如 /home/pi/oceanus）
#   --broker    平台那侧 MQTT broker 的地址（笔记本 ICS 地址 / 服务器 IP）
#
# 可选：
#   --mode      autopick（默认）| dispatch | console | all
#                 autopick  开机后自己反复找目标抓，不依赖平台派单
#                 dispatch  等平台派单，派一次抓一个
#                 console   只起作业台网页 :8090（采集 / 标注 / 训练 / 部署 / 标定都在这做）
#                 all       三套单元文件都装，但只 enable console；真机作业模式自己二选一
#   --pi-user   运行服务的用户（默认 pi）
#   --ros-setup 厂商工作空间的 setup.bash（默认 ~/armpi_fpv/devel/setup.bash）
#
# ★ autopick 与 dispatch 互斥：两者都会驱动同一台机械臂，脚本会自动 disable 另一个，
#   避免两个进程同时下发舵机指令抢总线。
#
# 装完看状态：
#   systemctl status oceanus-arm-autopick
#   journalctl -u oceanus-arm-autopick -f
#
# 上真机前先自检（模型 / 标定 / 相机 / ROS 四项前置）：
#   cd <repo> && python3 edge/grasp/tools/precheck.py
set -euo pipefail

REPO=""
BROKER=""
MODE="autopick"
PI_USER="pi"
ROS_SETUP="$HOME/armpi_fpv/devel/setup.bash"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo)      REPO="${2:-}"; shift 2 ;;
    --broker)    BROKER="${2:-}"; shift 2 ;;
    --mode)      MODE="${2:-}"; shift 2 ;;
    --pi-user)   PI_USER="${2:-}"; shift 2 ;;
    --ros-setup) ROS_SETUP="${2:-}"; shift 2 ;;
    -h|--help)   sed -n '2,30p' "$0"; exit 0 ;;
    *) echo "未知参数：$1" >&2; exit 2 ;;
  esac
done

[[ -n "$REPO" ]]   || { echo "缺少 --repo" >&2; exit 2; }
[[ -n "$BROKER" ]] || { echo "缺少 --broker" >&2; exit 2; }
[[ -d "$REPO/edge" ]] || { echo "$REPO/edge 不存在：--repo 要指向仓库根目录" >&2; exit 2; }
[[ "$(id -u)" -eq 0 ]] || { echo "请用 sudo 运行" >&2; exit 2; }

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEST=/etc/systemd/system
UNITS=(oceanus-grasp-console oceanus-arm-bridge oceanus-arm-autopick)

install_unit() {
  local name="$1"
  sed -e "s|__REPO__|$REPO|g" \
      -e "s|__PI_USER__|$PI_USER|g" \
      -e "s|__BROKER__|$BROKER|g" \
      -e "s|__ROS_SETUP__|$ROS_SETUP|g" \
      "$HERE/$name.service" > "$DEST/$name.service"
  echo "  写出 $DEST/$name.service"
}

echo "安装 systemd 单元 → $DEST"
for u in "${UNITS[@]}"; do install_unit "$u"; done
systemctl daemon-reload

enable_only() {
  local target="$1"
  for u in "${UNITS[@]}"; do
    if [[ "$u" == "$target" ]]; then
      systemctl enable --now "$u"
      echo "已启用并启动：$u"
    else
      systemctl disable --now "$u" >/dev/null 2>&1 || true
    fi
  done
}

case "$MODE" in
  autopick) enable_only oceanus-arm-autopick ;;
  dispatch) enable_only oceanus-arm-bridge ;;
  console)  enable_only oceanus-grasp-console ;;
  all)
    for u in "${UNITS[@]}"; do
      systemctl disable --now "$u" >/dev/null 2>&1 || true
    done
    systemctl enable --now oceanus-grasp-console
    echo "三套单元都已装好；当前只启用 oceanus-grasp-console（作业台 :8090）。"
    echo "真机作业模式二选一（互斥，别同时开）："
    echo "  sudo systemctl enable --now oceanus-arm-autopick   # 常驻自捡"
    echo "  sudo systemctl enable --now oceanus-arm-bridge     # 平台派单"
    ;;
  *) echo "未知 --mode：$MODE" >&2; exit 2 ;;
esac

echo
echo "下一步：先自检四项前置，再让它跑"
echo "  cd $REPO && python3 edge/grasp/tools/precheck.py"
