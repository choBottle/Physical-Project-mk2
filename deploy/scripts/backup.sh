#!/usr/bin/env bash
# MK2 저장 축 백업 — MySQL(mk2) + TimescaleDB(mk2) 논리 덤프.
#
#   ./deploy/scripts/backup.sh                  # → deploy/backups/<UTC 시각>/
#   ./deploy/scripts/backup.sh /mnt/backup/mk2  # 다른 위치로
#
# 무엇을 백업하지 않나: Kafka(장기 저장소가 아니다 — 7일 버퍼) · Prometheus/Loki/Tempo(관측, 보존 기간이 곧 정책) ·
# 촬영본 아카이브(be-capture 의 /data/media_capture — 용량이 커서 파일시스템 수준 백업 대상. docs/deployment/database.md §6).
# 복구: ./deploy/scripts/restore.sh <백업 디렉터리>
set -euo pipefail
cd "$(dirname "$0")/.."
export MSYS_NO_PATHCONV=1

OUT="${1:-backups/$(date -u +%Y%m%dT%H%M%SZ)}"
mkdir -p "${OUT}"

echo "[backup] MySQL mk2 → ${OUT}/mysql_mk2.sql.gz"
docker compose exec -T mysql sh -c \
  'mysqldump -uroot -p"$MYSQL_ROOT_PASSWORD" --single-transaction --routines --triggers --set-gtid-purged=OFF --databases mk2 2>/dev/null' \
  | gzip > "${OUT}/mysql_mk2.sql.gz"

echo "[backup] TimescaleDB mk2 → ${OUT}/timescaledb_mk2.dump"
# -Fc(사용자 정의 형식) — restore 가 timescaledb_pre_restore()/post_restore() 사이에서 pg_restore 로 푼다
docker compose exec -T timescaledb pg_dump -U postgres -d mk2 -Fc > "${OUT}/timescaledb_mk2.dump"

{
  echo "created_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "git_commit=$(git rev-parse --short HEAD 2>/dev/null || echo unknown)"
  docker compose config --images 2>/dev/null | grep -E '^(mysql|timescale)' | sed 's/^/image=/' || true
} > "${OUT}/MANIFEST"

ls -la "${OUT}"
echo "[backup] 완료 — 비밀번호는 포함되지 않는다. deploy/.env 는 따로 안전한 곳에 보관한다."
