# 구역 엣지 노드

> 구역(zone)마다 엣지 하나. 말단 장치의 업무·관측을 1차 수용해 중앙 부하를 **구역 수에 비례**하게 묶는다.
> 엣지↔중앙은 사설망이라 **터널이 강제**다(현재 구현: Tailscale — 교체 가능).

## 1. 무엇이 어디서 도나

| 층 | 무엇 | 배포 자산 |
|---|---|---|
| 엣지 공용 스택 | Mosquitto(+중앙 브릿지) · OTel Collector(Agent) · 엣지 Prometheus | [`deploy/edge/`](../../deploy/edge/) (이 문서) |
| 장치 노드 | 센서 · 로봇(Go1/RoboMaster EP) · 액추에이터 · 탐지 브리지 | [`hardware/pi/deploy/`](../../hardware/pi/deploy/) — systemd 유닛 + `hw-robot` 이미지 · 설치 안내 [`hardware/docs/EDGE_SETUP.md`](../../hardware/docs/EDGE_SETUP.md) |
| 드론 컴패니언 | SAR 패스 · RTK 중계 · 비행 로그 | [`drone/deploy/pi/`](../../drone/deploy/pi/) · [`FIELD_CHECKLIST.md`](../../drone/FIELD_CHECKLIST.md) |

### 경로

```text
업무  장치 ─MQTT─▶ 엣지 Mosquitto(1883) ══브릿지(터널)══▶ 중앙 Mosquitto(1883) ─▶ be-ingest ─▶ Kafka ─▶ TimescaleDB·MySQL
명령  장치 ◀────── 엣지 Mosquitto ◀══════브릿지══════════ 중앙 Mosquitto ◀─ 명령 발행자
관측  장치 ─OTLP─▶ 엣지 Collector(4317) ─┬─ metric ─▶ 엣지 Prometheus ◀─/federate(요약)─ 중앙 Prometheus
                                         └─ log·trace ─▶ 중앙 Collector(4317)
```

엣지 Mosquitto 의 브릿지(`deploy/edge/config/mosquitto-entrypoint.sh` 가 `deploy/edge/.env` 로 기동 때 생성)가 넘기는 토픽:

| 방향 | 토픽 | 무엇 |
|---|---|---|
| 엣지 → 중앙 | `+/+/+/state` · `+/+/+/status` · `+/+/+/heartbeat` | 텔레메트리 3채널 — `{zone}/{etype}/{eid}/{channel}`, 중앙 `be-ingest` 가 구독하는 것과 같다 |
| 엣지 → 중앙 | `terminal/+/uplink` | 명령 응답 · Capability |
| 중앙 → 엣지 | `terminal/+/downlink` | 명령 |

그 밖의 토픽(장치 사이의 로컬 토픽 등)은 엣지 안에 머문다. 브릿지는 구역마다 고정 client id(`mk2-edge-<zone>`)와
지속 세션으로 붙는다 — 터널이 끊긴 동안 중앙에 쌓인 명령(QoS 1)은 다시 붙을 때 넘어온다. 반대로 터널이 끊긴 동안의
텔레메트리는 엣지 Mosquitto 가 브릿지 세션에 쌓아 두었다가 넘긴다. 상한은 Mosquitto 기본 `max_queued_messages`(1000건)이고
넘치면 버린다(장치는 엣지 브로커에는 붙어 있어 자기 spool 로 재전송하지 않는다). 긴 단절이 예상되면 `deploy/edge/site/mosquitto/`
에 `max_queued_messages` 를 올린 `.conf` 를 둔다.

## 2. 순서

### ① 터널

중앙 서버와 엣지 둘 다 같은 tailnet 에 넣고 주소를 확인한다.

```bash
tailscale up            # 처음 한 번 (기관 계정으로)
tailscale ip -4         # 이 주소가 아래의 <터널 주소>
```

### ② 중앙 서버 — 입구를 터널 주소로

중앙 `deploy/.env`:

```bash
MK2_EDGE_BIND=<중앙 터널 주소>
```

Kafka EDGE 리스너(9095)는 **1.0 에서 쓰지 않는다** — 엣지는 Kafka 에 붙지 않고 MQTT 브릿지로 중앙 Mosquitto 에 넘긴다.
`MK2_KAFKA_EDGE_BIND`·`MK2_KAFKA_EDGE_ADVERTISED` 는 기본값(loopback·localhost) 그대로 둔다(§4 실험 배치에서만 바꾼다).

`docker compose up -d` 후, 엣지에서 `nc -zv <중앙 터널 주소> 1883 4317 8766` 이 모두 열려 있어야 한다.

### ③ 엣지 공용 스택

```bash
cd deploy/edge
cp .env.example .env
#   MK2_ZONE_ID=zoneA
#   MK2_CENTRAL_OTLP=<중앙 터널 주소>:4317
#   MK2_CENTRAL_MQTT_HOST=<중앙 터널 주소>    ← 업무 브릿지가 붙을 중앙 Mosquitto (포트는 MK2_CENTRAL_MQTT_PORT, 기본 1883)
#   MK2_EDGE_TUNNEL_BIND=<엣지 터널 주소>     ← 중앙이 페더레이션으로 당겨 갈 입구
docker compose up -d --wait
```

중앙 Mosquitto 에 계정을 켰다면 브릿지 계정을 `MK2_CENTRAL_MQTT_USER`·`MK2_CENTRAL_MQTT_PASSWORD` 에 넣는다.
엣지 현장 설정(장치 계정·현장 수집 잡)은 추적 파일이 아니라 `deploy/edge/site/`·`deploy/edge/docker-compose.override.yml`
(gitignore)에 둔다 — [operations.md 「현장 설정」](operations.md#현장-설정--추적-파일을-고치지-않는다).

### ④ 장치 노드

장치 노드 설정(`hardware/pi/deploy/hw-node.env.example`)의 세 값을 엣지로 향하게 한다:

| 변수 | 값 |
|---|---|
| `HW_BROKER_HOST` | 엣지 자신(`localhost`) 또는 엣지 LAN 주소 — 엣지 Mosquitto 가 브릿지로 중앙에 넘긴다 |
| `HW_OTEL_ENDPOINT` | `http://<엣지 주소>:4317` |
| `HW_ZONE_ID` | `deploy/edge/.env` 의 `MK2_ZONE_ID` 와 같은 값 |

### ⑤ 중앙 페더레이션 켜기

중앙의 `deploy/site/prometheus/edge-targets/edge.yml` 에 엣지 터널 주소를 더한다 — [observability.md §6](observability.md#6-엣지-페더레이션-2계층).

## 3. 검증

| 확인 | 방법 | 기대 |
|---|---|---|
| 브릿지 연결 | 엣지에서 `docker compose exec mosquitto mosquitto_sub -t '$SYS/broker/connection/#' -v -C 1 -W 5` | `$SYS/broker/connection/mk2-edge-zoneA/state 1` |
| 업무가 중앙 DB 에 | 중앙에서 `docker compose exec timescaledb psql -U postgres -d mk2 -c "SELECT source_id, max(ingest_at) FROM telemetry WHERE zone_id='zoneA' AND ingest_at > now() - interval '10 min' GROUP BY 1"` | 이 구역 장치들이 최근 시각으로 |
| 명령이 엣지에 | 엣지에서 `docker compose exec mosquitto mosquitto_sub -t 'terminal/+/downlink' -v` 를 띄워 두고 중앙에서 명령 발행 | 엣지에 도착 |
| 엣지 metric 이 엣지에 | `curl http://<엣지 터널 주소>:9090/api/v1/label/__name__/values` | `hw_*` |
| 엣지 metric 이 중앙에 (페더레이션) | 중앙 Prometheus `up{job="edge_federate"}` · `count by (zone_id) (hw_publish_count_total{agg_layer="edge"})` (`zone_id` 는 `edge.yml` 타깃 라벨) | `1` · 이 구역 시계열 |

장치 노드는 log 를 OTel 로 내보내지 않는다(Pi 의 journald) — 엣지 경로의 관측 확인은 위처럼 metric 으로 한다. 엣지
Collector 의 log 경로 자체는 열려 있다(2026-10-26 검증: 엣지 Collector 에 **직접 보낸 시험 log** 가 중앙 Loki 에
`zone_id=zoneT`·`agg_layer=edge` 로 도착). 업무 브릿지는 CI(`deploy-smoke` 의 `edge-stack`)가 매 PR 마다 양방향으로 시험한다
(엣지 발행 → 중앙 브로커 도착 · 범위 밖 토픽은 엣지에 머묾 · 중앙 명령 → 엣지 도착).

## 4. 현재 한계 (v1.0 범위 밖)

- **엣지 Kafka 브릿지**: 아키텍처의 최종 형태는 "엣지 Mosquitto → 엣지 ingest → 중앙 Kafka(EDGE 9095)"다. 1.0 은 엣지
  Mosquitto 의 MQTT 브릿지로 중앙 Mosquitto 에 넘기고 ingest 는 중앙에서 돈다(§1 경로). 엣지에서 `be-ingest` 를 돌리는
  구성(`MK2_KAFKA_BOOTSTRAP=<중앙>:9095`, 중앙 `MK2_KAFKA_EDGE_BIND`·`MK2_KAFKA_EDGE_ADVERTISED` 를 터널 주소로)은
  2026-09-19 컴퓨터 임시 엣지로 실증됐으나 엣지 compose 에는 아직 넣지 않았다 — [RELEASE.md 로드맵](../RELEASE.md).
  그때까지 9095 는 터널에 열 필요가 없다.
- 브릿지는 MQTT 평문이다 — 터널이 암호화를 맡는다. 터널 밖 배치는 [security.md](security.md).
- k3s 기반 엣지 오케스트레이션은 [`hardware/k3s/README.md`](../../hardware/k3s/README.md) 의 복구 기록 수준이다.
- 장치 노드 systemd 유닛은 템플릿이다 — `hardware/pi/deploy/install-units.sh --user <사용자>` 로 설치한다(`sudo cp` 로 직접 복사하면 기동 실패).
