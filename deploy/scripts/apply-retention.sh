#!/usr/bin/env bash
# MK2 TimescaleDB 보존·압축 정책 — deploy/.env 의 값과 실제 정책(timescaledb_information.jobs)을 맞춘다. 재실행 안전.
#
#   ./deploy/scripts/apply-retention.sh             # 반영 (migrate.sh 가 끝에 부른다)
#   ./deploy/scripts/apply-retention.sh --dry-run   # 지금 정책과 원하는 정책만 보여 준다
#
#   MK2_TSDB_RETENTION_DAYS=365        이보다 오래된 청크를 지운다(add_retention_policy). 비우면 끔
#   MK2_TSDB_COMPRESS_AFTER_DAYS=7     이보다 오래된 청크를 압축한다(add_compression_policy). 비우면 끔
#
# 값은 셸 환경변수가 있으면 그것, 없으면 deploy/.env 에서 읽는다. 양의 정수(일)만 받는다.
# 선언형이다: 값을 비우면 그 정책을 **지운다**(압축을 끌 때 이미 압축된 청크는 그대로 둔다 — 풀지 않는다).
# 값이 같으면 아무것도 하지 않는다(정책 job 을 다시 만들지 않는다). 값이 바뀌면 정책을 지우고 새 값으로 다시 건다.
# 대상 하이퍼테이블: telemetry (server/infra/sql/mk2_tsdb_schema.sql — 하이퍼테이블은 이것 하나다).
# 문서: docs/deployment/database.md §6
set -euo pipefail

cd "$(dirname "$0")/.."
export MSYS_NO_PATHCONV=1

DRY=0
case "${1:-}" in
  "") ;;
  --dry-run) DRY=1 ;;
  -h|--help) sed -n '2,16p' "$0"; exit 0 ;;
  *) echo "알 수 없는 인자: $1 (--dry-run)" >&2; exit 1 ;;
esac

die() { echo "[retention] ❌ $*" >&2; exit 1; }
psql_pg() { docker compose exec -T timescaledb psql -X -U postgres -d mk2 -v ON_ERROR_STOP=1 "$@"; }

# 환경변수 우선, 없으면 .env (따옴표·주석 없는 KEY=값 한 줄 — .env.example 규약)
envval() {
  local name="$1"
  if [[ -n "${!name+x}" ]]; then printf '%s' "${!name}"; return; fi
  [[ -f .env ]] || return 0
  grep -E "^${name}=" .env | tail -1 | cut -d= -f2- | tr -d '\r' || true
}

RET="$(envval MK2_TSDB_RETENTION_DAYS)"
CMP="$(envval MK2_TSDB_COMPRESS_AFTER_DAYS)"
for pair in "MK2_TSDB_RETENTION_DAYS=${RET}" "MK2_TSDB_COMPRESS_AFTER_DAYS=${CMP}"; do
  [[ -z "${pair#*=}" || "${pair#*=}" =~ ^[1-9][0-9]{0,5}$ ]] || die "${pair%%=*} 는 비우거나 양의 정수(일)여야 한다: '${pair#*=}'"
done
if [[ -n "${RET}" && -n "${CMP}" && "${CMP}" -ge "${RET}" ]]; then
  echo "[retention] ⚠ 압축 시점(${CMP}일)이 보존 기간(${RET}일) 이상이다 — 압축되기 전에 지워진다"
fi

sql_interval() { if [[ -n "$1" ]]; then echo "INTERVAL '$1 days'"; else echo "NULL::interval"; fi; }
WANT_RET="$(sql_interval "${RET}")"
WANT_CMP="$(sql_interval "${CMP}")"

echo "[retention] telemetry — 보존 ${RET:-끔}${RET:+일} · 압축 ${CMP:-끔}${CMP:+일 뒤}"
echo "[retention] 지금 정책:"
psql_pg -tA -F ' ' -c "SELECT '  ' || proc_name, 'job=' || job_id, config::text FROM timescaledb_information.jobs
                         WHERE hypertable_schema = 'public' AND hypertable_name = 'telemetry' ORDER BY job_id" \
  | tr -d '\r' | sed '/^$/d' | grep . || echo "  (없음)"

if [[ ${DRY} -eq 1 ]]; then
  echo "[retention] --dry-run — 바꾸지 않는다"
  exit 0
fi

# 하나의 트랜잭션 — 정책 교체(지우고 다시 걸기) 도중에 실패하면 옛 정책이 그대로 남는다
psql_pg -q --single-transaction <<SQL
DO \$mk2\$
DECLARE
    want interval := ${WANT_RET};
    cur  interval;
BEGIN
    SELECT (config->>'drop_after')::interval INTO cur
      FROM timescaledb_information.jobs
     WHERE proc_name = 'policy_retention' AND hypertable_schema = 'public' AND hypertable_name = 'telemetry'
     LIMIT 1;
    IF cur IS NOT DISTINCT FROM want THEN
        RAISE NOTICE '[mk2] 보존: 변경 없음 (%)', coalesce(want::text, '끔');
        RETURN;
    END IF;
    IF cur IS NOT NULL THEN
        PERFORM remove_retention_policy('public.telemetry');
    END IF;
    IF want IS NOT NULL THEN
        PERFORM add_retention_policy('public.telemetry', drop_after => want);
    END IF;
    RAISE NOTICE '[mk2] 보존: % → %', coalesce(cur::text, '끔'), coalesce(want::text, '끔');
END
\$mk2\$;

DO \$mk2\$
DECLARE
    want    interval := ${WANT_CMP};
    cur     interval;
    enabled boolean;
BEGIN
    SELECT (config->>'compress_after')::interval INTO cur
      FROM timescaledb_information.jobs
     WHERE proc_name = 'policy_compression' AND hypertable_schema = 'public' AND hypertable_name = 'telemetry'
     LIMIT 1;
    IF cur IS NOT DISTINCT FROM want THEN
        RAISE NOTICE '[mk2] 압축: 변경 없음 (%)', coalesce(want::text, '끔');
        RETURN;
    END IF;
    IF cur IS NOT NULL THEN
        PERFORM remove_compression_policy('public.telemetry');
    END IF;
    IF want IS NOT NULL THEN
        SELECT compression_enabled INTO enabled
          FROM timescaledb_information.hypertables
         WHERE hypertable_schema = 'public' AND hypertable_name = 'telemetry';
        IF NOT coalesce(enabled, false) THEN
            -- 유일 키(ts, stream_topic, stream_partition, stream_offset)의 칼럼은 segmentby/orderby 에 있어야 한다.
            -- stream_topic = 채널(토픽 3개) · stream_partition(1개)라 세그먼트 수가 작다.
            ALTER TABLE public.telemetry SET (
                timescaledb.compress,
                timescaledb.compress_segmentby = 'stream_topic, stream_partition',
                timescaledb.compress_orderby   = 'ts DESC, stream_offset DESC'
            );
        END IF;
        PERFORM add_compression_policy('public.telemetry', compress_after => want);
    END IF;
    RAISE NOTICE '[mk2] 압축: % → %', coalesce(cur::text, '끔'), coalesce(want::text, '끔');
END
\$mk2\$;
SQL

echo "[retention] 반영 뒤 정책:"
psql_pg -tA -F ' ' -c "SELECT '  ' || proc_name, 'job=' || job_id, config::text FROM timescaledb_information.jobs
                         WHERE hypertable_schema = 'public' AND hypertable_name = 'telemetry' ORDER BY job_id" \
  | tr -d '\r' | sed '/^$/d' | grep . || echo "  (없음)"
