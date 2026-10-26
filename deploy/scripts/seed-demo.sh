#!/usr/bin/env bash
# 레지스트리 선언 축에 데모 시드를 넣는다(root, INSERT IGNORE — 재실행 안전).
#   ./deploy/scripts/seed-demo.sh [시드 파일]     # 기본: deploy/server/seed/registry-demo.sql
set -euo pipefail
cd "$(dirname "$0")/.."
SEED="${1:-server/seed/registry-demo.sql}"
docker compose exec -T mysql sh -c 'mysql -uroot -p"$MYSQL_ROOT_PASSWORD" -t' < "${SEED}"
