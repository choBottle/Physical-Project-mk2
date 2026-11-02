#!/usr/bin/env bash
# MK2 저장 축 복구 — backup.sh 가 만든 디렉터리에서 MySQL·TimescaleDB 를 되살린다.
#
#   ./deploy/scripts/restore.sh deploy/backups/20261026T061500Z   # 저장소 루트에서
#   ./scripts/restore.sh backups/20261026T061500Z                 # deploy/ 에서
#
# 백업 경로는 명령을 실행한 위치 기준이다(절대경로도 된다).
# 실패하면 오류를 보여 주고 백엔드를 다시 띄운 뒤 0 이 아닌 값으로 끝난다 — "완료" 는 전부 성공했을 때만 찍힌다.
#
# ⚠ 대상 DB 의 현재 내용을 **덮어쓴다**. 백엔드(be-*)를 먼저 멈추고, 끝나면 다시 띄운다.
# 앱 계정(mk2_app)과 권한은 덤프에 들어 있지 않다 — 새 서버로 옮기는 경우 그 서버의 최초 초기화가 만든다.
set -euo pipefail
SRC="${1:?사용법: restore.sh <백업 디렉터리>}"
# cd 전에 호출한 위치 기준으로 절대경로로 바꾼다 (예전에는 deploy/ 기준이라 문서의 명령이 실패했다)
[[ "${SRC}" == /* || "${SRC}" =~ ^[A-Za-z]: ]] || SRC="${PWD}/${SRC}"
cd "$(dirname "$0")/.."
export MSYS_NO_PATHCONV=1
[[ -f "${SRC}/mysql_mk2.sql.gz" && -f "${SRC}/timescaledb_mk2.dump" ]] || { echo "백업 파일이 없다: ${SRC}"; exit 1; }

read -r -p "mk2 DB 두 개를 ${SRC} 로 덮어쓴다. 계속할까? [y/N] " ans
[[ "${ans}" == "y" || "${ans}" == "Y" ]] || { echo "취소"; exit 1; }

BACKEND=(be-ingest be-storage be-gateway be-capture)
on_fail() {
  local rc=$?
  echo "[restore] 실패 (exit ${rc}) — 위 오류를 확인한다. DB 는 일부만 복구됐을 수 있다." >&2
  echo "[restore] 백엔드를 다시 띄운다" >&2
  docker compose up -d "${BACKEND[@]}" >&2 || true
  exit "${rc}"
}

echo "[restore] 백엔드 정지"
docker compose stop "${BACKEND[@]}"
trap on_fail ERR

echo "[restore] MySQL"
# MYSQL_PWD 로 넘겨 비밀번호 경고 없이 stderr 를 그대로 보여 준다(예전에는 2>/dev/null 로 오류까지 숨겼다)
gunzip -c "${SRC}/mysql_mk2.sql.gz" | docker compose exec -T mysql sh -c 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -uroot'

echo "[restore] TimescaleDB"
docker compose exec -T timescaledb psql -U postgres -d mk2 -v ON_ERROR_STOP=1 -qc "SELECT timescaledb_pre_restore();" >/dev/null
# 예전에는 '|| true' 로 실패해도 "완료" 를 찍었다. 이제 pg_restore 가 실패하면 멈춘다.
docker compose exec -T timescaledb pg_restore -U postgres -d mk2 --clean --if-exists --no-owner --no-privileges < "${SRC}/timescaledb_mk2.dump"
docker compose exec -T timescaledb psql -U postgres -d mk2 -v ON_ERROR_STOP=1 -qc "SELECT timescaledb_post_restore();" >/dev/null
# --no-privileges 로 풀었으므로 앱 계정 권한을 정본 템플릿에서 다시 건다
sed "s|<MK2_TSDB_PASSWORD>|$(grep '^MK2_TSDB_PASSWORD=' .env | cut -d= -f2)|g" ../server/infra/sql/mk2_grants_tsdb.sql.example \
  | docker compose exec -T timescaledb psql -U postgres -d mk2 -q >/dev/null

trap - ERR
echo "[restore] 백엔드 기동"
docker compose up -d --wait "${BACKEND[@]}"
echo "[restore] 완료 — ./scripts/healthcheck.sh 로 확인한다."
