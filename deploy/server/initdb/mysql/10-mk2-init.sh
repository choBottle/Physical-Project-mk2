#!/bin/bash
# MK2 MySQL 최초 초기화 — 데이터 볼륨이 비어 있을 때 **한 번만** 돈다(mysql 이미지 규약).
#
# 정본은 server/infra/sql/ 이고 여기서는 순서만 정한다(/mk2-sql 로 읽기 전용 마운트):
#   1) mk2_mysql_schema.sql          DB + 테이블 8
#   2) 앱 계정 생성                   (media_capture.sql 안의 GRANT 가 계정을 요구한다)
#   3) mk2_media_capture.sql         테이블 1 + GRANT
#   4) mk2_grants_mysql.sql.example  테이블별 차등 권한(DDL 없음 · 감사/실행기록 append-only)
#   5) mk2_schema_migrations_mysql.sql  스키마 판 추적표 + baseline. 정본은 이미 최신이므로 migrations/ 의
#                                    MySQL 파일(*_tsdb.sql 제외)도 전부 적용된 것으로 표시한다(applied_by=init)
#
# 운영 서버 원본의 계정 host 는 '172.18.%'(그 서버의 docker 기본 브리지)였다. 여기서는 compose 가
# 대역을 고정하므로(MK2_NET_SUBNET) 그 패턴을 MK2_DB_APP_HOST 로 바꿔 적용한다.
# 비밀번호는 환경변수에서 바로 치환해 파이프한다 — 실제 값이 든 SQL 파일을 남기지 않는다.
set -euo pipefail

: "${MK2_MYSQL_PASSWORD:?MK2_MYSQL_PASSWORD 가 없다}"
: "${MK2_DB_APP_HOST:=172.28.%}"

mysql_root() { mysql --protocol=socket -uroot -p"${MYSQL_ROOT_PASSWORD}"; }
subst() {
  sed -e "s|'172\.18\.%'|'${MK2_DB_APP_HOST}'|g" \
      -e "s|<MK2_MYSQL_PASSWORD>|${MK2_MYSQL_PASSWORD}|g" "$1"
}

echo "[mk2-init] 1/5 스키마"
mysql_root < /mk2-sql/mk2_mysql_schema.sql

echo "[mk2-init] 2/5 앱 계정 mk2_app@'${MK2_DB_APP_HOST}'"
mysql_root <<SQL
CREATE USER IF NOT EXISTS 'mk2_app'@'${MK2_DB_APP_HOST}'
    IDENTIFIED WITH caching_sha2_password BY '${MK2_MYSQL_PASSWORD}';
SQL

echo "[mk2-init] 3/5 media_capture"
subst /mk2-sql/mk2_media_capture.sql | mysql_root > /dev/null

echo "[mk2-init] 4/5 권한"
subst /mk2-sql/mk2_grants_mysql.sql.example | mysql_root

echo "[mk2-init] 5/5 스키마 판 추적(schema_migrations)"
mysql_root < /mk2-sql/mk2_schema_migrations_mysql.sql
for f in /mk2-sql/migrations/*.sql; do
  [[ -e "${f}" ]] || continue
  name="$(basename "${f}")"
  [[ "${name}" == *_tsdb.sql ]] && continue
  # 이름 규약(migrate.sh 와 같다) 밖의 파일은 표시하지 않는다 — SQL 에 그대로 들어가는 값이다
  [[ "${name}" =~ ^[0-9]{8}_[A-Za-z0-9_]+\.sql$ ]] || { echo "[mk2-init]   건너뜀(이름 규약 밖): ${name}"; continue; }
  echo "INSERT IGNORE INTO mk2.schema_migrations (version, applied_by) VALUES ('${name%.sql}', 'init');" | mysql_root
done

echo "[mk2-init] 완료"
