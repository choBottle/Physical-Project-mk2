#!/usr/bin/env bash
# MQTT 운영 프로파일(계정) 시험 — 중앙 Mosquitto 가 익명을 거부할 때 백엔드가 계정으로 붙는가.
#
#   ./deploy/scripts/mqtt-auth-check.sh [백엔드 이미지]     # 기본: $MK2_BACKEND_IMAGE, 없으면 server/ 에서 빌드
#
# 문서(docs/deployment/security.md §3-1 · deploy/site/mosquitto/auth.conf.example)의 절차를 **격리된 일회용 자원**으로
# 재현한다 — 실행 중인 스택·deploy/site/ 를 건드리지 않는다:
#   추적 설정(server/config/mosquitto.conf) + auth.conf.example 을 site.d 로 → mosquitto_passwd 로 백엔드 계정
#   ① 익명 구독·발행 거부   ② 틀린 비밀번호 거부
#   ③ be-ingest 클라이언트(make_mqtt_client)가 MK2_MQTT_USERNAME/PASSWORD 로 접속·구독 → 시험 발행자(계정)가 보낸 1건 수신
#   ④ 같은 클라이언트가 계정 없이(익명)는 구독에 이르지 못한다(음성 대조)
# 종료 코드: 0 = 전부 통과, 1 = 하나 이상 실패.
set -uo pipefail

cd "$(dirname "$0")/.." || exit 1          # deploy/
export MSYS_NO_PATHCONV=1                  # Git Bash(Windows)에서 컨테이너 경로가 바뀌지 않게

PASS=0; FAIL=0
ok()  { echo "  ✅ $*"; PASS=$((PASS+1)); }
bad() { echo "  ❌ $*"; FAIL=$((FAIL+1)); }
hostpath() { (cd "$1" && (pwd -W 2>/dev/null || pwd)); }

IMG="${1:-${MK2_BACKEND_IMAGE:-mk2-backend:auth-check}}"
# 브로커 판은 compose 와 같은 것을 쓴다(두 벌이 되면 시험이 다른 브로커를 본다)
MQ_IMG="$(awk '/image: eclipse-mosquitto:/ {print $2; exit}' docker-compose.yml)"
TAG="mk2-authchk-$$"
SITE="$(mktemp -d)"
USER_OK="mk2-backend"
PASS_OK="$(LC_ALL=C tr -dc 'A-Za-z0-9' < /dev/urandom | head -c 24)"

cleanup() {
  docker rm -f "${TAG}-mqtt" >/dev/null 2>&1
  docker network rm "${TAG}" >/dev/null 2>&1
  docker volume rm "${TAG}-data" >/dev/null 2>&1
  rm -rf "${SITE}"
}
trap cleanup EXIT

if ! docker image inspect "${IMG}" >/dev/null 2>&1; then
  echo "▶ 백엔드 이미지 빌드 (${IMG})"
  docker build -q -t "${IMG}" ../server >/dev/null || { echo "이미지 빌드 실패"; exit 1; }
fi

echo "▶ 0. Mosquitto 운영 프로파일 기동 (${MQ_IMG} · site.d/auth.conf ← auth.conf.example)"
cp site/mosquitto/auth.conf.example "${SITE}/auth.conf"
chmod 755 "${SITE}"; chmod 644 "${SITE}/auth.conf"
docker network create "${TAG}" >/dev/null
docker volume create "${TAG}-data" >/dev/null
# 문서 절차의 mosquitto_passwd 와 같다(compose exec 대신 일회용 컨테이너). 브로커는 mosquitto 사용자로 읽는다.
# shellcheck disable=SC2016  # $1·$2 는 컨테이너 안 sh 가 펼친다
docker run --rm -v "${TAG}-data:/mosquitto/data" "${MQ_IMG}" sh -c \
  'mosquitto_passwd -c -b /mosquitto/data/passwd "$1" "$2" && chown mosquitto:mosquitto /mosquitto/data/passwd && chmod 0600 /mosquitto/data/passwd' \
  _ "${USER_OK}" "${PASS_OK}" || { echo "password_file 생성 실패"; exit 1; }
docker run -d --name "${TAG}-mqtt" --network "${TAG}" --network-alias mosquitto \
  -v "$(hostpath server/config)/mosquitto.conf:/mosquitto/config/mosquitto.conf:ro" \
  -v "$(hostpath "${SITE}"):/mosquitto/config/site.d:ro" \
  -v "${TAG}-data:/mosquitto/data" "${MQ_IMG}" >/dev/null || { echo "브로커 기동 실패"; exit 1; }
mq() { docker exec "${TAG}-mqtt" "$@"; }
up=""
for _ in $(seq 1 30); do
  up="$(mq mosquitto_sub -h localhost -u "${USER_OK}" -P "${PASS_OK}" -t '$SYS/broker/uptime' -C 1 -W 2 2>/dev/null)" && break
  sleep 1
done
[[ -n "${up}" ]] && ok "계정 접속(\$SYS 구독) — 브로커 준비" || { bad "브로커 미준비"; docker logs "${TAG}-mqtt" 2>&1 | tail -20; exit 1; }

echo "▶ 1. 익명·틀린 계정은 거부된다"
if mq mosquitto_pub -h localhost -t zoneA/sensor/auth-probe/state -m anon >/dev/null 2>&1; then
  bad "익명 발행이 받아들여졌다 (allow_anonymous false 가 안 먹었다)"
else ok "익명 발행 거부"; fi
if mq mosquitto_sub -h localhost -t '$SYS/broker/uptime' -C 1 -W 3 >/dev/null 2>&1; then
  bad "익명 구독이 받아들여졌다"
else ok "익명 구독 거부"; fi
if mq mosquitto_pub -h localhost -u "${USER_OK}" -P wrongpassword -t zoneA/sensor/auth-probe/state -m bad >/dev/null 2>&1; then
  bad "틀린 비밀번호가 받아들여졌다"
else ok "틀린 비밀번호 거부"; fi

# be-ingest 의 MQTT 클라이언트 그대로(make_mqtt_client — 계정은 환경변수에서). Kafka 는 필요 없다 — 수신을 가로채 센다.
PROBE='
import sys, time, uuid
sys.path.insert(0, "/app/tests")
from backend import settings
from backend.ingest.bridge import SUBSCRIPTIONS, make_mqtt_client
expect = sys.argv[1]
state = {"subscribed": 0, "refused": None, "got": []}
c = make_mqtt_client("mk2-auth-check-" + uuid.uuid4().hex[:6])
def on_connect(cl, u, f, rc, p=None):
    if rc.is_failure:
        state["refused"] = str(rc)
    else:
        cl.subscribe(SUBSCRIPTIONS)
c.on_connect = on_connect
c.on_subscribe = lambda cl, u, mid, rcs, p=None: state.update(subscribed=len(rcs))
c.on_message = lambda cl, u, m: state["got"].append(m.topic)
c.connect(settings.mqtt_host(), settings.mqtt_port(), keepalive=10)
c.loop_start()
deadline = time.time() + (15 if expect == "ok" else 6)
while time.time() < deadline and not state["subscribed"] and not state["refused"]:
    time.sleep(0.2)
if expect == "reject":
    c.loop_stop()
    print("refused=%s subscribed=%s" % (state["refused"], state["subscribed"]))
    sys.exit(0 if state["subscribed"] == 0 else 1)
if not state["subscribed"]:
    print("구독 실패 refused=%s" % state["refused"]); sys.exit(1)
import publisher
topic = "zoneA/sensor/auth-probe/state"
publisher.publish(topic, {"probe": uuid.uuid4().hex}, host=settings.mqtt_host(), port=settings.mqtt_port())
while time.time() < deadline and topic not in state["got"]:
    time.sleep(0.2)
c.loop_stop()
print("user=%s subscribed=%s got=%s" % (settings.mqtt_username(), state["subscribed"], state["got"]))
sys.exit(0 if topic in state["got"] else 1)
'
probe() {  # probe <ok|reject> <user> <password>
  docker run --rm -i --network "${TAG}" \
    -e MK2_MQTT_HOST=mosquitto -e MK2_MQTT_PORT=1883 -e MK2_OTEL_ENDPOINT= \
    -e MK2_MQTT_USERNAME="$2" -e MK2_MQTT_PASSWORD="$3" \
    "${IMG}" python -c "${PROBE}" "$1"
}

echo "▶ 2. 백엔드(be-ingest 클라이언트)가 MK2_MQTT_USERNAME/PASSWORD 로 붙는다"
if out="$(probe ok "${USER_OK}" "${PASS_OK}" 2>&1)"; then
  ok "계정 접속 → 구독 → 시험 발행자(계정) 1건 수신 (${out##*$'\n'})"
else bad "계정 접속 실패: ${out}"; fi
if out="$(probe reject "" "" 2>&1)"; then
  ok "계정 없이는 구독에 이르지 못한다 (${out##*$'\n'})"
else bad "익명 백엔드가 구독했다: ${out}"; fi

echo; echo "결과: 통과 ${PASS} · 실패 ${FAIL}"
if [[ ${FAIL} -gt 0 ]]; then docker logs --tail 30 "${TAG}-mqtt" 2>&1; fi
[[ ${FAIL} -eq 0 ]]
