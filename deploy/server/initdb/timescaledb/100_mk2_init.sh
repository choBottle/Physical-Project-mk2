#!/bin/bash
# MK2 TimescaleDB 최초 초기화 — 데이터 볼륨이 비어 있을 때 **한 번만** 돈다(postgres 이미지 규약).
#
# 이미지 자체 스크립트(000_install_timescaledb.sh · 001_timescaledb_tune.sh) 뒤에 돌도록 100_ 이다.
# 정본은 server/infra/sql/ (/mk2-sql 로 읽기 전용 마운트):
#   1) mk2_tsdb_schema.sql           telemetry 하이퍼테이블 + 인덱스
#   2) mk2_grants_tsdb.sql.example   mk2_app — SELECT·INSERT 만, DDL 없음
#   3) pg_hba 한정                   전면 허용(host all all all)을 지우고 mk2_app 을 도커 대역으로만
#
# 운영 서버에서는 3) 을 기동 뒤 사람이 손으로 했다(infra/README.md §4). 여기서는 같은 결과를 최초 초기화에서
# 만든다 — postgres 슈퍼유저는 TCP 로 못 붙고 컨테이너 안 소켓(docker compose exec)으로만 들어간다.
set -euo pipefail

: "${MK2_TSDB_PASSWORD:?MK2_TSDB_PASSWORD 가 없다}"
: "${MK2_NET_SUBNET:=172.28.0.0/16}"

psql_mk2() { psql -v ON_ERROR_STOP=1 --username "${POSTGRES_USER:-postgres}" --dbname mk2 "$@"; }

echo "[mk2-init] 1/3 스키마"
psql_mk2 -q -f /mk2-sql/mk2_tsdb_schema.sql

echo "[mk2-init] 2/3 앱 계정·권한"
sed "s|<MK2_TSDB_PASSWORD>|${MK2_TSDB_PASSWORD}|g" /mk2-sql/mk2_grants_tsdb.sql.example | psql_mk2 -q

echo "[mk2-init] 3/3 pg_hba — mk2_app 을 ${MK2_NET_SUBNET} 로 한정"
HBA="${PGDATA}/pg_hba.conf"
cp "${HBA}" "${HBA}.bak_before_mk2"
# pg_hba 는 첫 매치가 이긴다 — 전면 허용을 남긴 채 뒤에 붙이면 한정 규칙에 도달하지 못한다
sed -i -E '/^[[:space:]]*host[[:space:]]+all[[:space:]]+all[[:space:]]+all[[:space:]]/d' "${HBA}"
cat >> "${HBA}" <<EOF

# ── MK2 (BE-S-01 계측 저장) — 앱 계정만, 도커 대역에서만 ──
host    mk2     mk2_app     ${MK2_NET_SUBNET}     scram-sha-256
EOF

echo "[mk2-init] 완료"
