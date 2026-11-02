#!/bin/sh
# 엣지 Mosquitto 기동 전에 중앙 브릿지 설정을 만든다 — mosquitto.conf 는 환경변수를 읽지 못한다.
#
# 방향 (토픽 규약: 텔레메트리 {zone}/{etype}/{eid}/{channel} · 명령 terminal/<device-id>/{downlink,uplink})
#   out  엣지 → 중앙   +/+/+/state · +/+/+/status · +/+/+/heartbeat   (중앙 be-ingest 가 구독하는 3채널)
#                      terminal/+/uplink                              (명령 응답·Capability)
#   in   중앙 → 엣지   terminal/+/downlink                            (명령)
# 그 밖의 토픽(장치 간 로컬 토픽 등)은 엣지 안에만 머문다.
# 연결 상태: 엣지 브로커의 $SYS/broker/connection/mk2-edge-<zone>/state (1 = 연결, retained)
set -eu

host="${MK2_CENTRAL_MQTT_HOST:-}"
port="${MK2_CENTRAL_MQTT_PORT:-1883}"
zone="${MK2_ZONE_ID:-}"

die() { echo "mosquitto-entrypoint: $*" >&2; exit 1; }
[ -n "${host}" ] || die "MK2_CENTRAL_MQTT_HOST 가 비었다 — deploy/edge/.env 에 중앙 서버 터널 주소를 넣는다"
[ -n "${zone}" ] || die "MK2_ZONE_ID 가 비었다"
case "${host}" in *[!A-Za-z0-9._:-]*) die "MK2_CENTRAL_MQTT_HOST 가 주소 형식이 아니다: ${host}" ;; esac
case "${port}" in ''|*[!0-9]*) die "MK2_CENTRAL_MQTT_PORT 가 숫자가 아니다: ${port}" ;; esac
case "${zone}" in *[!A-Za-z0-9_-]*) die "MK2_ZONE_ID 에 허용되지 않는 문자: ${zone}" ;; esac

dir=/mosquitto/config/bridge.d
mkdir -p "${dir}"
{
  echo "connection mk2-central"
  echo "address ${host}:${port}"
  # 구역마다 고정 — 중앙이 세션을 기억해 엣지가 끊긴 동안의 명령(QoS 1)을 쌓아 둔다
  echo "remote_clientid mk2-edge-${zone}"
  echo "local_clientid mk2-edge-${zone}-local"
  echo "cleansession false"
  echo "restart_timeout 5 60"
  echo "notifications true"
  echo "notification_topic \$SYS/broker/connection/mk2-edge-${zone}/state"
  echo "notifications_local_only true"
  for ch in state status heartbeat; do
    echo "topic +/+/+/${ch} out 1"
  done
  echo "topic terminal/+/uplink out 1"
  echo "topic terminal/+/downlink in 1"
  if [ -n "${MK2_CENTRAL_MQTT_USER:-}" ]; then
    echo "remote_username ${MK2_CENTRAL_MQTT_USER}"
    echo "remote_password ${MK2_CENTRAL_MQTT_PASSWORD:-}"
  fi
} > "${dir}/bridge.conf"
echo "mosquitto-entrypoint: 중앙 브릿지 → ${host}:${port} (clientid mk2-edge-${zone})"

exec /docker-entrypoint.sh /usr/sbin/mosquitto -c /mosquitto/config/mosquitto.conf
