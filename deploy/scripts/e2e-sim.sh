#!/usr/bin/env bash
# 장비 없이 하는 전 구간(E2E) 시험 — 말단 → 중앙 → 관제 화면 구독.
#
#   ./deploy/scripts/e2e-sim.sh        # 중앙 스택이 떠 있어야 한다(healthcheck 통과 뒤)
#
# healthcheck 의 업무 관통 검사는 시험용 발행기(server/tests/publisher.py)를 쓴다. 이 시험은 **실제 말단 노드 코드**
# (hardware/pi 의 sensor_node — Pi 에서 도는 그 파일)를 컨테이너로 띄워 중앙 Mosquitto 에 붙인다. 바뀌는 것은
# 센서 입력 하나뿐이다 — 노드에 들어 있는 가짜 수위 센서(read_sensor)와 강우 스위치(/tmp/rain)를 쓴다.
#
#   ① 평시   — 주기 보고(periodic)가 관제 화면 구독(/state, VZ 형식)에 도착하는가
#   ② 사건   — 강우 스위치를 켜면 임계 초과(threshold_exceeded) → 고주기(event) 전환이 화면까지 오는가
#   ③ 해제   — 스위치를 끄면 임계 해제(threshold_cleared) → 평시(normal) 복귀가 오는가
#   ④ 저장   — 같은 값이 TimescaleDB · MySQL 레지스트리에 남는가
#   ⑤ 관측   — 노드 자신의 metric(OTel → Collector → Prometheus)이 오는가
#
# 노드 컨테이너는 python:3.12-slim 에 Pi 와 같은 라이브러리(pi_base_setup.sh)를 받아 쓴다 — 인터넷이 필요하다.
# 종료 코드: 0 = 전부 통과, 1 = 하나 이상 실패. 시험 행은 source_id 접두사 wl-e2e- 로 구분된다.
set -uo pipefail

cd "$(dirname "$0")/.." || exit 1
export MSYS_NO_PATHCONV=1   # Git Bash(Windows)에서 컨테이너 경로가 바뀌지 않게

PASS=0; FAIL=0
ok()  { echo "  ✅ $*"; PASS=$((PASS+1)); }
bad() { echo "  ❌ $*"; FAIL=$((FAIL+1)); }
dc()  { docker compose "$@"; }
prom(){ dc exec -T prometheus wget -qO- "$1" 2>/dev/null; }

EID="wl-e2e-$(date +%s)"
NODE="mk2-e2e-sensor"
LOG="$(mktemp)"
PROBE_PID=""
cleanup() {
  [[ -n "${PROBE_PID}" ]] && kill "${PROBE_PID}" 2>/dev/null
  docker rm -f "${NODE}" >/dev/null 2>&1
  rm -f "${LOG}"
}
trap cleanup EXIT

# 중앙 스택의 도커 망 — 노드를 그 안에 넣는다(실배치의 터널·LAN 자리)
NET="$(docker inspect -f '{{range $k, $v := .NetworkSettings.Networks}}{{$k}} {{end}}' "$(dc ps -q mosquitto)" 2>/dev/null | awk '{print $1}')"
[[ -n "${NET}" ]] || { echo "중앙 스택이 떠 있지 않다 — docker compose up -d --wait 먼저"; exit 1; }
PI_DIR="$(cd ../hardware/pi && (pwd -W 2>/dev/null || pwd))"

echo "▶ 0. 말단 노드 기동 (hardware/pi/sensor — entity=${EID})"
docker rm -f "${NODE}" >/dev/null 2>&1
docker run -d --name "${NODE}" --hostname e2e-pi --network "${NET}" -v "${PI_DIR}:/pi:ro" -w /pi \
  -e HW_ENTITY_ID="${EID}" -e HW_ZONE_ID=zoneA \
  -e HW_BROKER_HOST=mosquitto -e HW_OTEL_ENDPOINT=http://otel-collector:4317 \
  -e HW_REPORT_INTERVAL_NORMAL=5 -e HW_SPOOL_PATH=/tmp/spool.jsonl -e PYTHONUNBUFFERED=1 \
  python:3.12-slim sh -c "pip install -q --root-user-action=ignore --disable-pip-version-check \
    paho-mqtt opentelemetry-sdk opentelemetry-exporter-otlp psutil protobuf && exec python -m sensor.sensor_node" >/dev/null \
  || { bad "노드 컨테이너 기동"; exit 1; }

# 관제 화면 자리 — VZ 앱(viz-debugger WsTransport)과 같은 구독 메시지를 /state 에 보내고 받은 봉투를 한 줄씩 적는다.
# 게이트웨이 컨테이너 안에서 돈다(토큰은 그 컨테이너의 MK2_WS_TOKEN — 호스트 포트·방화벽과 무관).
dc exec -T be-gateway python -u - "${EID}" > "${LOG}" 2>&1 <<'PY' &
import asyncio, json, os, sys, time
from datetime import datetime
from websockets.asyncio.client import connect

eid = sys.argv[1]

async def main():
    url = f"ws://127.0.0.1:8765/state?token={os.environ.get('MK2_WS_TOKEN', '')}"
    async with connect(url) as ws:
        await ws.send(json.dumps({"type": "subscribe", "id": "sub-1", "scope": "all",
                                  "selector": {"entity": eid, "node": "*", "channel": "*"}}))
        async for raw in ws:
            msg = json.loads(raw)
            if msg.get("type") != "data" or msg.get("sub") != "sub-1":
                continue
            env = msg["envelope"]
            p = env.get("payload") or {}
            try:
                lag_ms = round((time.time() - datetime.fromisoformat(env["timestamp"]).timestamp()) * 1000)
            except Exception:
                lag_ms = None
            print(json.dumps({"channel": env.get("channel"), "reason": p.get("reason"), "mode": p.get("mode"),
                              "value": p.get("water_level_m"), "alert": p.get("alert"), "lag_ms": lag_ms}), flush=True)

asyncio.run(main())
PY
PROBE_PID=$!

# 기다리기: 로그에 조건에 맞는 줄이 생길 때까지(최대 $2 초)
wait_for() {
  local pat="$1" limit="$2"
  for _ in $(seq 1 "${limit}"); do
    grep -q "${pat}" "${LOG}" && return 0
    sleep 1
  done
  return 1
}

echo "▶ 1. 평시 — 주기 보고가 관제 구독에 도착"
# 첫 기동은 pip 설치 시간이 든다
if wait_for '"reason": "periodic"' 120; then ok "periodic 상태 도착 (/state · VZ 형식)"; else bad "periodic 상태가 오지 않음"; fi

echo "▶ 2. 사건 — 강우 스위치 ON"
docker exec "${NODE}" touch /tmp/rain
if wait_for '"reason": "threshold_exceeded"' 30; then ok "임계 초과(threshold_exceeded) 도착"; else bad "임계 초과가 오지 않음"; fi
if wait_for '"mode": "event"' 10; then ok "고주기(event) 전환이 화면까지"; else bad "event 모드 표시 없음"; fi
sleep 5
docker exec "${NODE}" rm -f /tmp/rain

echo "▶ 3. 해제 — 강우 스위치 OFF"
if wait_for '"reason": "threshold_cleared"' 60; then ok "임계 해제(threshold_cleared) 도착"; else bad "임계 해제가 오지 않음"; fi
sleep 2
grep '"reason": "threshold_cleared"' "${LOG}" | grep -q '"mode": "normal"' \
  && ok "평시(normal) 복귀" || bad "normal 복귀 표시 없음"

received="$(grep -c '"channel": "state"' "${LOG}")"
lags="$(grep -o '"lag_ms": [0-9-]*' "${LOG}" | awk '{print $2}' | sort -n)"
if [[ -n "${lags}" ]]; then
  n="$(echo "${lags}" | wc -l)"
  echo "     관제 구독 수신 ${received}건 · 발행→화면 지연 중앙값 $(echo "${lags}" | sed -n "$(( (n+1)/2 ))p")ms · 최대 $(echo "${lags}" | tail -1)ms"
fi

echo "▶ 4. 저장 — 같은 값이 남는가"
rows=0
for _ in $(seq 1 15); do
  rows="$(dc exec -T timescaledb psql -U postgres -d mk2 -tAc "SELECT count(*) FROM telemetry WHERE source_id='${EID}' AND channel='state'" 2>/dev/null | tr -d '[:space:]')"
  [[ "${rows:-0}" -ge "${received:-1}" ]] && break
  sleep 2
done
[[ "${rows:-0}" -ge "${received:-1}" && "${rows:-0}" -gt 0 ]] \
  && ok "TimescaleDB state ${rows}행 (화면 수신 ${received}건 이상)" || bad "TimescaleDB state ${rows:-0}행 (화면 수신 ${received}건)"
for r in threshold_exceeded threshold_cleared; do
  n="$(dc exec -T timescaledb psql -U postgres -d mk2 -tAc "SELECT count(*) FROM telemetry WHERE source_id='${EID}' AND reason='${r}'" 2>/dev/null | tr -d '[:space:]')"
  [[ "${n:-0}" -ge 1 ]] && ok "TimescaleDB 사건 행 ${r}" || bad "TimescaleDB 사건 행 ${r} 없음"
done
dc exec -T mysql sh -c "mysql -uroot -p\"\$MYSQL_ROOT_PASSWORD\" -N -e \"SELECT entity_id FROM mk2.registry_entity_observed WHERE entity_id='${EID}'\"" 2>/dev/null \
  | grep -q "${EID}" && ok "MySQL 레지스트리 관측 등록" || bad "MySQL 레지스트리에 ${EID} 없음"

echo "▶ 5. 관측 — 노드 자신의 metric"
seen=""
for _ in $(seq 1 12); do
  seen="$(prom "http://localhost:9090/api/v1/query?query=hw_publish_count_total%7Bexported_instance%3D%22${EID}%22%2Coutcome%3D%22ok%22%7D" | grep -o '"value"')"
  [[ -n "${seen}" ]] && break
  sleep 5
done
[[ -n "${seen}" ]] && ok "Prometheus hw_publish_count_total{exported_instance=${EID}}" || bad "노드 metric 이 Prometheus 에 없음"
# 노드 log 는 OTel 로 내보내지 않는다(Pi 의 journald) — 노드 trace 는 명령 경로에만 있다. 그래서 여기서는 metric 만 본다.

echo
echo "결과: 통과 ${PASS} · 실패 ${FAIL}"
[[ ${FAIL} -eq 0 ]]
