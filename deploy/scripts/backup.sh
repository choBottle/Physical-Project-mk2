#!/usr/bin/env bash
# MK2 저장 축 백업 — MySQL(mk2) + TimescaleDB(mk2) 논리 덤프.
#
#   ./deploy/scripts/backup.sh                  # → deploy/backups/<UTC 시각>/
#   ./deploy/scripts/backup.sh /mnt/backup/mk2  # 다른 위치로 (상대경로면 명령을 실행한 위치 기준)
#
# 무엇을 백업하지 않나: Kafka(장기 저장소가 아니다 — 7일 버퍼) · Prometheus/Loki/Tempo(관측, 보존 기간이 곧 정책) ·
# 촬영본 아카이브(be-capture 의 /data/media_capture — 용량이 커서 파일시스템 수준 백업 대상. docs/deployment/database.md §6).
# 복구: ./deploy/scripts/restore.sh <백업 디렉터리>
set -euo pipefail
OUT="${1:-}"
# 인자로 준 경로는 호출한 위치 기준(cd 전에 절대경로로). 안 주면 deploy/backups/<UTC>
if [[ -n "${OUT}" && "${OUT}" != /* && ! "${OUT}" =~ ^[A-Za-z]: ]]; then OUT="${PWD}/${OUT}"; fi
cd "$(dirname "$0")/.."
export MSYS_NO_PATHCONV=1
OUT="${OUT:-backups/$(date -u +%Y%m%dT%H%M%SZ)}"
mkdir -p "${OUT}"

echo "[backup] MySQL mk2 → ${OUT}/mysql_mk2.sql.gz"
docker compose exec -T mysql sh -c \
  'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysqldump -uroot --single-transaction --routines --triggers --set-gtid-purged=OFF --databases mk2' \
  | gzip > "${OUT}/mysql_mk2.sql.gz"

echo "[backup] TimescaleDB mk2 → ${OUT}/timescaledb_mk2.dump"
# -Fc(사용자 정의 형식) — restore 가 timescaledb_pre_restore()/post_restore() 사이에서 pg_restore 로 푼다
docker compose exec -T timescaledb pg_dump -U postgres -d mk2 -Fc > "${OUT}/timescaledb_mk2.dump"
echo "[backup] 참고: 위의 pg_dump 'circular foreign-key constraints' 경고·hint 는 무해하다 — TimescaleDB 내부 카탈로그 표 때문이며, restore.sh 가 timescaledb_pre_restore()/post_restore() 사이에서 푼다."

{
  echo "created_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "git_commit=$(git rev-parse --short HEAD 2>/dev/null || echo unknown)"
  docker compose config --images 2>/dev/null | grep -E '^(mysql|timescale)' | sed 's/^/image=/' || true
} > "${OUT}/MANIFEST"

ls -la "${OUT}"
echo "[backup] 완료 — 비밀번호는 포함되지 않는다. deploy/.env 는 따로 안전한 곳에 보관한다."
