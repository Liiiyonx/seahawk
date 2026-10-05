#!/usr/bin/env bash
# 重建治理大屏截图（图 5-2），消除左侧视频墙的 NetworkError。
#
# 前置条件（缺任一都会退回「视频墙报错」的旧图）：
#   1. Docker Desktop 已由用户手动启动（本机安全策略拦截 wsl.exe，Agent 起不了）
#   2. 前端本地 vite 已起在 5173（.env.local 指向 127.0.0.1:8001）
#
# 关键点：go2rtc 的 `ffmpeg:/config/demo/*.mp4` 源在**容器内**解析路径，
# 所以 ./deploy/go2rtc/demo 必须挂载进容器（见 docker-compose.yml）。
# 只挂 yaml 不挂目录 → 四路流全部读不到文件 → 大屏又出现整片报错区。
set -euo pipefail
cd "C:/Users/Liii/Desktop/seahawk"

echo "== 1/5 检查 Docker"
if ! docker info >/dev/null 2>&1; then
  echo "  ✗ Docker 未运行。请手动双击启动 Docker Desktop 后重跑本脚本。" >&2
  exit 1
fi
echo "  ✓ Docker 运行中"

echo "== 2/5 启动依赖（含 go2rtc）"
docker compose up -d postgres redis minio emqx go2rtc 2>&1 | tail -3
docker compose build backend 2>&1 | tail -2
docker compose up -d backend 2>&1 | tail -2

echo "== 3/5 等待后端健康"
for i in $(seq 1 40); do
  if curl -sf http://127.0.0.1:8001/health >/dev/null 2>&1; then
    echo "  ✓ 后端就绪（第 ${i} 次探测）"; break
  fi
  sleep 2
done

echo "== 4/5 验证 go2rtc 四路流可解码"
# go2rtc API 列出 streams；source 指向 /config/demo/*.mp4 时应能起 ffmpeg 子进程
curl -s http://127.0.0.1:1984/api/streams 2>/dev/null \
  | "C:/Users/Liii/.workbuddy/binaries/python/versions/3.13.12/python.exe" -c "
import json,sys
try:
    d=json.load(sys.stdin)
except Exception:
    print('  ! 无法解析 go2rtc API（容器可能仍在启动）'); raise SystemExit(0)
for k,v in d.items():
    prod=v.get('producers') or []
    print(f'  {k}: producers={len(prod)}  {\"OK\" if prod else \"无画面（检查 demo 目录挂载）\"}')
" || true

echo "== 5/5 重拍大屏截图"
export PLAYWRIGHT_CORE_PATH="C:/Users/Liii/.workbuddy/binaries/node/workspace/node_modules/playwright-core"
export SEASIGHT_FRONTEND_URL="http://127.0.0.1:5173"
node scripts/ui_responsive_audit.mjs 2>&1 | tail -12

echo
echo "完成。请检查 artifacts/ui-responsive/1920x1080-dashboard.png 的视频墙是否出画面。"
echo "若仍是报错区，贴给我，我看 go2rtc 日志定位。"
