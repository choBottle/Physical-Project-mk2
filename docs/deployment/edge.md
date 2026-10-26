# 구역 엣지 노드

> 구역(zone)마다 엣지 하나. 말단 장치의 업무·관측을 1차 수용해 중앙 부하를 **구역 수에 비례**하게 묶는다.
> 엣지↔중앙은 사설망이라 **터널이 강제**다(현재 구현: Tailscale — 교체 가능).

## 1. 무엇이 어디서 도나

| 층 | 무엇 | 배포 자산 |
|---|---|---|
| 엣지 공용 스택 | Mosquitto · OTel Collector(Agent) · 엣지 Prometheus | [`deploy/edge/`](../../deploy/edge/) (이 문서) |
| 장치 노드 | 센서 · 로봇(Go1/RoboMaster EP) · 액추에이터 · 탐지 브리지 | [`hardware/pi/deploy/`](../../hardware/pi/deploy/) — systemd 유닛 + `hw-robot` 이미지 · 설치 안내 [`hardware/docs/EDGE_SETUP.md`](../../hardware/docs/EDGE_SETUP.md) |
| 드론 컴패니언 | SAR 패스 · RTK 중계 · 비행 로그 | [`drone/viz-debugger/drone/deploy/pi/`](../../drone/viz-debugger/drone/deploy/pi/) · [`FIELD_CHECKLIST.md`](../../drone/viz-debugger/drone/FIELD_CHECKLIST.md) |

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
MK2_KAFKA_EDGE_ADVERTISED=<중앙 터널 주소>
```

`docker compose up -d` 후, 엣지에서 `nc -zv <중앙 터널 주소> 1883 4317 8766` 이 모두 열려 있어야 한다.

### ③ 엣지 공용 스택

```bash
cd deploy/edge
cp .env.example .env
#   MK2_ZONE_ID=zoneA
#   MK2_CENTRAL_OTLP=<중앙 터널 주소>:4317
#   MK2_EDGE_TUNNEL_BIND=<엣지 터널 주소>    ← 중앙이 페더레이션으로 당겨 갈 입구
docker compose up -d --wait
```

### ④ 장치 노드

장치 노드 설정(`hardware/pi/deploy/hw-node.env.example`)의 두 값을 엣지로 향하게 한다:

| 변수 | 값 |
|---|---|
| `HW_BROKER_HOST` | 엣지 자신(`localhost`) 또는 엣지 LAN 주소 |
| `HW_OTEL_ENDPOINT` | `http://<엣지 주소>:4317` |
| `HW_ZONE_ID` | `deploy/edge/.env` 의 `MK2_ZONE_ID` 와 같은 값 |

### ⑤ 중앙 페더레이션 켜기

[observability.md §6](observability.md#6-엣지-페더레이션-2계층).

## 3. 검증

| 확인 | 방법 | 기대 |
|---|---|---|
| 엣지 log 가 중앙에 | 중앙 Grafana → Explore → Loki `{zone_id="zoneA"}` | 장치 노드 로그 (리소스 속성 `agg_layer=edge`) |
| 엣지 metric 이 엣지에 | `curl http://<엣지 터널 주소>:9090/api/v1/label/__name__/values` | `hw_*` |
| 중앙 페더레이션 | 중앙 Prometheus `up{job="edge_federate"}` | `1` |

2026-10-26 검증: 엣지 스택(시험용 구역 `zoneT`)에 보낸 log 가 중앙 Loki 에 `zone_id=zoneT`·`agg_layer=edge` 로 도착.

## 4. 현재 한계 (v1.0 범위 밖)

- **업무 경로의 엣지 Kafka 브릿지**: 아키텍처 기준은 "엣지 Mosquitto → 엣지 브릿지 → 중앙 Kafka(EDGE 9095)"이나, 현재 백엔드
  ingest 는 중앙에서 돈다. 지금은 장치가 **중앙 Mosquitto(1883, 터널)** 로 직접 발행하는 배치가 검증된 경로다. 엣지에서
  `be-ingest` 를 돌리는 구성(`MK2_KAFKA_BOOTSTRAP=<중앙>:9095`)은 2026-09-19 컴퓨터 임시 엣지로 실증됐으나 엣지 compose 에는
  아직 넣지 않았다 — [RELEASE.md 로드맵](../RELEASE.md).
- k3s 기반 엣지 오케스트레이션은 [`hardware/k3s/README.md`](../../hardware/k3s/README.md) 의 복구 기록 수준이다.
- 장치 노드 유닛이 사용자 `physical`·`/home/physical` 을 가정한다 — [OPEN_SOURCE_READINESS.md](../OPEN_SOURCE_READINESS.md).
