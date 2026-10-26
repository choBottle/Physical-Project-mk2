#!/usr/bin/env bash
# MK2 배포 헬스체크 — "떠 있다"가 아니라 "흐른다"를 본다.
#
#   ./deploy/scripts/healthcheck.sh            # 전체(생존 + 업무 관통 + 관측 + 권한)
#   ./deploy/scripts/healthcheck.sh --quick    # 생존만
#
# 모든 검사는 도커 망 안에서 한다(docker compose exec) — 호스트 포트·방화벽 설정과 무관하게 같은 결과.
# 업무 관통 검사는 hc-<시각> 이름의 시험 장치로 4건을 발행한다. 계측 원본은 지우지 않는다(앱 계정에
# DELETE 가 없다 — 의도). 시험 행은 source_id 접두사 hc- 로 구분된다.
# 종료 코드: 0 = 전부 통과, 1 = 하나 이상 실패.
set -uo pipefail

cd "$(dirname "$0")/.." || exit 1
export MSYS_NO_PATHCONV=1   # Git Bash(Windows)에서 컨테이너 경로가 바뀌지 않게

PASS=0; FAIL=0
ok()   { echo "  ✅ $*"; PASS=$((PASS+1)); }
bad()  { echo "  ❌ $*"; FAIL=$((FAIL+1)); }
check(){ local name="$1"; shift; if "$@" >/dev/null 2>&1; then ok "${name}"; else bad "${name}"; fi; }
dc()   { docker compose "$@"; }
prom() { dc exec -T prometheus wget -qO- "$1" 2>/dev/null; }

echo "▶ 1. 컨테이너 생존"
for svc in mosquitto kafka mysql timescaledb otel-collector prometheus loki tempo grafana \
           be-ingest be-storage be-gateway be-capture; do
  state="$(dc ps --format '{{.State}} {{.Health}}' "${svc}" 2>/dev/null | head -1)"
  case "${state}" in
    "running healthy"|"running ") ok "${svc} (${state% })" ;;
    *) bad "${svc} (${state:-없음})" ;;
  esac
done
init="$(dc ps -a --format '{{.State}} {{.ExitCode}}' kafka-init 2>/dev/null | head -1)"
[[ "${init}" == "exited 0" ]] && ok "kafka-init (토픽 생성 완료)" || bad "kafka-init (${init:-없음})"

if [[ "${1:-}" == "--quick" ]]; then
  echo; echo "결과: 통과 ${PASS} · 실패 ${FAIL}"; [[ ${FAIL} -eq 0 ]]; exit $?
fi

echo "▶ 2. 저장 축 스키마"
check "MySQL mk2 테이블 9개" bash -c \
  "[[ \$(docker compose exec -T mysql sh -c 'mysql -uroot -p\"\$MYSQL_ROOT_PASSWORD\" -N -e \"SELECT COUNT(*) FROM information_schema.TABLES WHERE TABLE_SCHEMA=\\\"mk2\\\"\"' 2>/dev/null | tr -d '\r') == 9 ]]"
check "TimescaleDB telemetry 하이퍼테이블" bash -c \
  "docker compose exec -T timescaledb psql -U postgres -d mk2 -tAc \"SELECT 1 FROM timescaledb_information.hypertables WHERE hypertable_name='telemetry'\" | grep -q 1"
check "Kafka 토픽 3개" bash -c \
  "[[ \$(docker compose exec -T kafka /opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 --list | grep -c '^mk2\.telemetry\.') == 3 ]]"

echo "▶ 3. 업무 관통 (MQTT → ingest → Kafka → storage → TimescaleDB · MySQL)"
EID="hc-$(date +%s)"
dc exec -T be-ingest python tests/publisher.py --host mosquitto --eid "${EID}" --count 3 --interval 0.2 >/dev/null 2>&1
dc exec -T be-ingest python tests/publisher.py --host mosquitto --eid "${EID}" --channel status >/dev/null 2>&1
rows=0
for _ in $(seq 1 15); do
  rows="$(dc exec -T timescaledb psql -U postgres -d mk2 -tAc "SELECT count(*) FROM telemetry WHERE source_id='${EID}'" 2>/dev/null | tr -d '[:space:]')"
  [[ "${rows}" == "4" ]] && break
  sleep 2
done
[[ "${rows}" == "4" ]] && ok "TimescaleDB 적재 4/4 (source_id=${EID})" || bad "TimescaleDB 적재 ${rows:-0}/4 (source_id=${EID})"
check "MySQL 레지스트리 관측 등록" bash -c \
  "docker compose exec -T mysql sh -c 'mysql -uroot -p\"\$MYSQL_ROOT_PASSWORD\" -N -e \"SELECT entity_id FROM mk2.registry_entity_observed WHERE entity_id=\\\"${EID}\\\"\"' 2>/dev/null | grep -q ${EID}"

echo "▶ 4. 관측 평면 (metric · log · 대시보드)"
targets="$(prom 'http://localhost:9090/api/v1/targets?state=active')"
for job in otel_collector otel_collector_self prometheus loki tempo; do
  echo "${targets}" | grep -q "\"job\":\"${job}\"" && ok "Prometheus 수집 대상 ${job}" || bad "Prometheus 수집 대상 ${job}"
done
down="$(prom 'http://localhost:9090/api/v1/query?query=count(up==0)' | grep -o '"value":\[[^]]*\]' | grep -o '"[0-9]*"$' | tr -d '"')"
[[ -z "${down}" || "${down}" == "0" ]] && ok "모든 수집 대상 up" || bad "down 인 수집 대상 ${down}개"
# 백엔드 metric export 주기가 15초라 첫 표본까지 기다린다
seen=""
for _ in $(seq 1 12); do
  seen="$(prom 'http://localhost:9090/api/v1/query?query=sum(be_ingest_received_total)' | grep -o '"value"' | head -1)"
  [[ -n "${seen}" ]] && break
  sleep 5
done
[[ -n "${seen}" ]] && ok "백엔드 지표 be_ingest_received_total 수신" || bad "백엔드 지표 없음 (Collector → Prometheus 경로)"
check "Loki 에 백엔드 로그(be-*)" bash -c \
  "docker compose exec -T prometheus wget -qO- 'http://loki:3100/loki/api/v1/label/service_name/values' | grep -q 'be-'"
# Tempo 는 기동 뒤 ~15초 워밍업 동안 /ready 가 503 이다
tready=""
for _ in $(seq 1 12); do
  tready="$(dc exec -T prometheus wget -qO- http://tempo:3200/ready 2>/dev/null)"
  [[ "${tready}" == *ready* ]] && break
  sleep 5
done
[[ "${tready}" == *ready* ]] && ok "Tempo 준비" || bad "Tempo 준비 (/ready 503)"
# trace 경로 — 백엔드 span 은 아직 없으므로(명령 경로 span 은 인증·감사 단계) 시험 span 1개로 경로를 판정한다
dc exec -T be-storage python -c "
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
p = TracerProvider(resource=Resource.create({'service.name': 'mk2-healthcheck'}))
p.add_span_processor(SimpleSpanProcessor(OTLPSpanExporter(endpoint='http://otel-collector:4317', insecure=True)))
with p.get_tracer('healthcheck').start_as_current_span('healthcheck'): pass
p.shutdown()
" >/dev/null 2>&1
tseen=""
for _ in $(seq 1 12); do
  tseen="$(dc exec -T prometheus wget -qO- 'http://tempo:3200/api/search/tag/service.name/values' 2>/dev/null | grep -o mk2-healthcheck)"
  [[ -n "${tseen}" ]] && break
  sleep 5
done
[[ -n "${tseen}" ]] && ok "trace 경로 (Collector → Tempo)" || bad "trace 경로 (시험 span 이 Tempo 에 없음)"
check "Grafana API" bash -c "docker compose exec -T prometheus wget -qO- http://grafana:3000/api/health | grep -q '\"database\": *\"ok\"'"

echo "▶ 5. 권한 — 앱 계정이 감사·실행기록을 고치지 못해야 한다(음성 대조)"
check "MySQL mk2_app: UPDATE audit_log · DELETE mission_event · CREATE 거부" \
  docker compose exec -T be-storage python -c "
import os, sys, pymysql
c = pymysql.connect(host='mysql', user='mk2_app', password=os.environ['MK2_MYSQL_PASSWORD'], database='mk2')
cur = c.cursor()
for q in ('UPDATE audit_log SET actor_kind=actor_kind', 'DELETE FROM mission_event', 'CREATE TABLE hc_x(i int)'):
    try:
        cur.execute(q); sys.exit('허용됨: ' + q)
    except pymysql.err.OperationalError as e:
        if e.args[0] != 1142: raise
"
check "TimescaleDB mk2_app: DELETE telemetry 거부" \
  docker compose exec -T be-storage python -c "
import os, sys, psycopg
c = psycopg.connect(host='timescaledb', dbname='mk2', user='mk2_app', password=os.environ['MK2_TSDB_PASSWORD'])
try:
    c.execute('DELETE FROM telemetry WHERE false'); sys.exit('허용됨')
except psycopg.errors.InsufficientPrivilege:
    pass
"

echo
echo "결과: 통과 ${PASS} · 실패 ${FAIL}"
[[ ${FAIL} -eq 0 ]]
