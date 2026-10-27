#!/usr/bin/env bash
# 트윈 시연 띄우기 — 중앙 스택(deploy/)이 떠 있는 기기에서 저장소 루트로 실행한다.
#   hardware/twin/demo/run-demo.sh [이미지]
# 이미지: ROS 2 Jazzy + Gazebo Harmonic 이 든 것. 기본 osrf/ros:jazzy-desktop-full
# 열리는 것 (이 기기에서만): 6080 Gazebo 화면(noVNC) · 25010/udp 360 장애물 입구
set -euo pipefail
IMAGE="${1:-osrf/ros:jazzy-desktop-full}"
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
NET="$(docker network ls --format '{{.Name}}' | grep -E '(^|_)mk2$' | head -1)"
[ -n "$NET" ] || { echo "중앙 스택 네트워크가 없습니다 — deploy/ 에서 docker compose up 먼저"; exit 1; }
docker rm -f twin-demo >/dev/null 2>&1 || true
MSYS_NO_PATHCONV=1 docker run -d --name twin-demo --network "$NET" \
  -p 127.0.0.1:6080:6080 -p 127.0.0.1:25010:25010/udp \
  -v "$ROOT:/repo:ro" "$IMAGE" bash /repo/hardware/twin/demo/gazebo-demo.sh >/dev/null
echo "twin-demo 기동 중 (패키지 설치에 1~3분). 진행: docker logs -f twin-demo"
