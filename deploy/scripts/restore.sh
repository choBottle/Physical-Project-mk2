#!/usr/bin/env bash
# MK2 저장 축 복구 — backup.sh 가 만든 디렉터리에서 MySQL·TimescaleDB 를 되살린다.
#
#   ./deploy/scripts/restore.sh deploy/backups/20261026T061500Z
#
# ⚠ 대상 DB 의 현재 내용을 **덮어쓴다**. 백엔드(be-*)를 먼저 멈추고, 끝나면 다시 띄운다.
# 앱 계정(mk2_app)과 권한은 덤프에 들어 있지 않다 — 새 서버로 옮기는 경우 그 서버의 최초 초기화가 만든다.
set -euo pipefail
cd "$(dirname "$0")/.."
export MSYS_NO_PATHCONV=1

SRC="${1:?사용법: restore.sh <백업 디렉터리>}"
[[ -f "${SRC}/mysql_mk2.sql.gz" && -f "${SRC}/timescaledb_mk2.dump" ]] || { echo "백업 파일이 없다: ${SRC}"; exit 1; }

read -r -p "mk2 DB 두 개를 ${SRC} 로 덮어쓴다. 계속할까? [y/N] " ans
[[ "${ans}" == "y" || "${ans}" == "Y" ]] || { echo "취소"; exit 1; }

echo "[restore] 백엔드 정지"
docker compose stop be-ingest be-storage be-gateway be-capture

echo "[restore] MySQL"
gunzip -c "${SRC}/mysql_mk2.sql.gz" | docker compose exec -T mysql sh -c 'mysql -uroot -p"$MYSQL_ROOT_PASSWORD" 2>/dev/null'

echo "[restore] TimescaleDB"
docker compose exec -T timescaledb psql -U postgres -d mk2 -qc "SELECT timescaledb_pre_restore();" >/dev/null
docker compose exec -T timescaledb pg_restore -U postgres -d mk2 --clean --if-exists --no-owner --no-privileges < "${SRC}/timescaledb_mk2.dump" || true
docker compose exec -T timescaledb psql -U postgres -d mk2 -qc "SELECT timescaledb_post_restore();" >/dev/null
# --no-privileges 로 풀었으므로 앱 계정 권한을 정본 템플릿에서 다시 건다
sed "s|<MK2_TSDB_PASSWORD>|$(grep '^MK2_TSDB_PASSWORD=' .env | cut -d= -f2)|g" ../server/infra/sql/mk2_grants_tsdb.sql.example \
  | docker compose exec -T timescaledb psql -U postgres -d mk2 -q >/dev/null

echo "[restore] 백엔드 기동"
docker compose up -d --wait be-ingest be-storage be-gateway be-capture
echo "[restore] 완료 — ./scripts/healthcheck.sh 로 확인한다."
