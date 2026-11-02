#!/usr/bin/env bash
# MK2 스키마 마이그레이션 — 기존 서버에 server/infra/sql/migrations/ 의 변경분을 순서대로 적용한다.
#
#   ./deploy/scripts/migrate.sh              # 적용됨/대기 목록 → 대기분 적용 → TimescaleDB 보존·압축 정책 반영
#   ./deploy/scripts/migrate.sh --dry-run    # 목록과 할 일만 보여 준다(DB 를 바꾸지 않는다)
#   ./deploy/scripts/migrate.sh --no-retention   # 보존·압축 정책(apply-retention.sh)은 건드리지 않는다
#
# 규칙 (docs/deployment/database.md §4)
#   - 파일 이름: YYYYMMDD_<주제>.sql (MySQL) · YYYYMMDD_<주제>_tsdb.sql (TimescaleDB). 같은 날 여러 개면
#     YYYYMMDD_1_<주제> 처럼 번호를 붙인다. 적용 순서 = 엔진별 파일 이름 사전순.
#   - 판 이름(version) = 파일 이름에서 .sql 을 뺀 것. 각 DB 의 schema_migrations 표에 기록된다.
#   - 적용은 root(MySQL)·postgres(TimescaleDB)로 컨테이너 안에서 한다. 앱 계정(mk2_app)은 이 표를 읽지도 못한다.
#   - 첫 오류에서 멈춘다. 실패한 파일은 기록되지 않고, 그 뒤 파일은 적용하지 않는다.
#     TimescaleDB 파일은 기록과 함께 한 트랜잭션으로 들어간다(실패 = 아무것도 안 바뀜).
#     MySQL DDL 은 트랜잭션이 안 되므로 실패 시 파일 일부가 반영됐을 수 있다 — 파일을 재실행 안전하게 쓰는 이유다.
#   - 추적 도입(이 스크립트) 전에 초기화된 서버: 표가 없으면 만들고 00000000_baseline 으로 표시한다.
#
# 먼저 백업한다: ./scripts/backup.sh
# 종료 코드: 0 = 성공(또는 할 일 없음), 1 = 오류.
set -euo pipefail

cd "$(dirname "$0")/.."
export MSYS_NO_PATHCONV=1   # Git Bash(Windows)에서 컨테이너 경로가 바뀌지 않게

SQL_DIR="../server/infra/sql"
MIG_DIR="${SQL_DIR}/migrations"
NAME_RE='^[0-9]{8}_[A-Za-z0-9_]+\.sql$'

DRY=0
RETENTION=1
for a in "$@"; do
  case "${a}" in
    --dry-run) DRY=1 ;;
    --no-retention) RETENTION=0 ;;
    -h|--help) sed -n '2,20p' "$0"; exit 0 ;;
    *) echo "알 수 없는 인자: ${a} (--dry-run · --no-retention)" >&2; exit 1 ;;
  esac
done

die() { echo "[migrate] ❌ $*" >&2; exit 1; }

# MySQL root — 인자는 mysql 클라이언트로 그대로 넘긴다. 비밀번호는 컨테이너 안 환경변수에서.
# shellcheck disable=SC2016  # $MYSQL_ROOT_PASSWORD 는 컨테이너 안에서 펼친다
mysql_root() { docker compose exec -T mysql sh -c 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" exec mysql -uroot "$@"' _ "$@"; }
psql_pg()    { docker compose exec -T timescaledb psql -X -U postgres -d mk2 -v ON_ERROR_STOP=1 "$@"; }

running="$(docker compose ps --status running --services 2>/dev/null || true)"
for svc in mysql timescaledb; do
  grep -qx "${svc}" <<<"${running}" || die "${svc} 컨테이너가 떠 있지 않다 — docker compose up -d --wait ${svc}"
done

# ── 파일 목록 (이름 규약 검사 — 규약 밖 파일은 조용히 건너뛰지 않고 멈춘다) ──
MYSQL_FILES=(); TSDB_FILES=()
if [[ -d "${MIG_DIR}" ]]; then
  while IFS= read -r f; do
    name="$(basename "${f}")"
    [[ "${name}" =~ ${NAME_RE} ]] || die "이름 규약 밖의 마이그레이션 파일: ${name} (YYYYMMDD_<주제>[_tsdb].sql)"
    if [[ "${name}" == *_tsdb.sql ]]; then TSDB_FILES+=("${name}"); else MYSQL_FILES+=("${name}"); fi
  done < <(find "${MIG_DIR}" -maxdepth 1 -type f -name '*.sql' | LC_ALL=C sort)
fi

PENDING_TOTAL=0

# 한 엔진의 상태를 보이고 대기분을 적용한다.
#   $1 = mysql | tsdb,  나머지 = 그 엔진의 파일 이름(정렬됨)
run_engine() {
  local engine="$1"; shift
  local files=("$@") exists applied_rows label

  if [[ "${engine}" == mysql ]]; then
    label="MySQL"
    exists="$(mysql_root -N -B -e "SELECT COUNT(*) FROM information_schema.TABLES WHERE TABLE_SCHEMA='mk2' AND TABLE_NAME='schema_migrations'" | tr -d '\r')"
    [[ "${exists}" == 1 ]] && exists=t || exists=f
  else
    label="TimescaleDB"
    exists="$(psql_pg -tAc "SELECT to_regclass('public.schema_migrations') IS NOT NULL" | tr -d '\r')"
  fi
  [[ "${exists}" == t || "${exists}" == f ]] || die "${label}: schema_migrations 확인 실패 (응답='${exists}')"

  echo "▶ ${label}"
  if [[ "${exists}" == f ]]; then
    if [[ ${DRY} -eq 1 ]]; then
      echo "  (추적표 없음 — 추적 도입 전 서버. 실제 실행 때 schema_migrations 를 만들고 00000000_baseline 으로 표시한다)"
    else
      echo "  추적표 없음 — 추적 도입 전 서버로 보고 schema_migrations 를 만들고 00000000_baseline 으로 표시한다"
    fi
  fi
  if [[ ${DRY} -eq 0 ]]; then
    # 재실행 안전(IF NOT EXISTS · baseline 은 이미 있으면 그대로) — 표가 있어도 매번 돌려 정본과 맞춘다
    if [[ "${engine}" == mysql ]]; then
      mysql_root < "${SQL_DIR}/mk2_schema_migrations_mysql.sql" || die "${label}: 추적표 생성 실패"
    else
      psql_pg -q < "${SQL_DIR}/mk2_schema_migrations_tsdb.sql" || die "${label}: 추적표 생성 실패"
    fi
    exists=t
  fi

  if [[ "${exists}" == t ]]; then
    if [[ "${engine}" == mysql ]]; then
      applied_rows="$(mysql_root -N -B -e "SELECT version, applied_by, DATE_FORMAT(applied_at, '%Y-%m-%dT%H:%i:%sZ') FROM mk2.schema_migrations ORDER BY version" | tr -d '\r')"
    else
      applied_rows="$(psql_pg -tA -F $'\t' -c "SELECT version, applied_by, to_char(applied_at AT TIME ZONE 'UTC', 'YYYY-MM-DD\"T\"HH24:MI:SS\"Z\"') FROM public.schema_migrations ORDER BY version" | tr -d '\r')"
    fi
  else
    applied_rows=$'00000000_baseline\tbaseline\t(예정)'
  fi

  local -A applied=()
  local v by at
  while IFS=$'\t' read -r v by at; do
    [[ -n "${v}" ]] || continue
    applied["${v}"]=1
    if [[ "${v}" == 00000000_baseline || -f "${MIG_DIR}/${v}.sql" ]]; then
      echo "  ✔ ${v}  (${by}, ${at})"
    else
      echo "  ⚠ ${v}  (${by}, ${at}) — 기록은 있는데 파일이 없다(옛 판으로 되돌렸나?)"
    fi
  done <<<"${applied_rows}"

  local pending=() f
  for f in "${files[@]}"; do
    [[ -n "${applied[${f%.sql}]:-}" ]] || pending+=("${f}")
  done
  echo "  적용됨 ${#applied[@]} · 대기 ${#pending[@]}"
  PENDING_TOTAL=$((PENDING_TOTAL + ${#pending[@]}))

  for f in "${pending[@]}"; do
    v="${f%.sql}"
    if [[ ${DRY} -eq 1 ]]; then
      echo "  … 대기: ${f}"
      continue
    fi
    echo "  → 적용: ${f}"
    if [[ "${engine}" == mysql ]]; then
      # mysql 배치 모드는 첫 오류에서 멈추고 0 이 아닌 값으로 끝난다 — 기록 INSERT 는 파일이 다 성공해야 닿는다
      if ! { cat "${MIG_DIR}/${f}"
             printf "\nINSERT IGNORE INTO mk2.schema_migrations (version, applied_by) VALUES ('%s', 'migrate.sh');\n" "${v}"
           } | mysql_root mk2; then
        die "${label}: ${f} 적용 실패 — 기록하지 않았고 뒤 파일도 적용하지 않았다. MySQL DDL 은 일부만 반영됐을 수 있다. 원인을 고친 뒤 다시 실행한다."
      fi
    else
      if ! { cat "${MIG_DIR}/${f}"
             printf "\nINSERT INTO public.schema_migrations (version, applied_by) VALUES ('%s', 'migrate.sh') ON CONFLICT (version) DO NOTHING;\n" "${v}"
           } | psql_pg -q --single-transaction; then
        die "${label}: ${f} 적용 실패 — 트랜잭션이 되돌려졌다(기록 없음). 뒤 파일도 적용하지 않았다. 원인을 고친 뒤 다시 실행한다."
      fi
    fi
    echo "  ✔ ${v}  (migrate.sh, 방금)"
  done
}

[[ ${DRY} -eq 1 ]] && echo "[migrate] --dry-run — DB 를 바꾸지 않는다"
run_engine mysql "${MYSQL_FILES[@]}"
run_engine tsdb "${TSDB_FILES[@]}"
if [[ ${DRY} -eq 1 ]]; then
  echo "[migrate] 대기 합계 ${PENDING_TOTAL}"
else
  echo "[migrate] 대기 합계 0 (이번에 ${PENDING_TOTAL}건 적용)"
fi

if [[ ${RETENTION} -eq 1 ]]; then
  if [[ ${DRY} -eq 1 ]]; then ./scripts/apply-retention.sh --dry-run; else ./scripts/apply-retention.sh; fi
fi
echo "[migrate] 완료"
