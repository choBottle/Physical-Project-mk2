# 포트 레지스트리 (단일 출처)

새 포트를 쓰기 전에 이 표를 먼저 본다. 포트를 추가·변경하는 PR 은 이 표도 함께 고친다.
(2026-10-26 기준 — 각 파트 브랜치의 코드·설정에서 수집)

## 중앙 서버 (`deploy/docker-compose.yml`)

| 포트 | 프로토콜 | 서비스 | 바인딩 | 누가 붙나 |
|---|---|---|---|---|
| 1883 | MQTT | Mosquitto | `MK2_EDGE_BIND` | 말단·엣지 발행자 |
| 9001 | MQTT/WS | Mosquitto | `MK2_EDGE_BIND` | 브라우저 도구 |
| 4316 · 4317 | OTLP gRPC | OTel Collector (같은 수신단) | `MK2_EDGE_BIND` | 백엔드 · HW 노드 · AI · 엣지 Collector |
| 4318 | OTLP HTTP | OTel Collector | `MK2_EDGE_BIND` | 브라우저(가시화 화면, CORS) |
| 8765 | WS | be-gateway `/state` · `/media` | `MK2_EDGE_BIND` | 관제 화면(뷰어) — 토큰 |
| 8766 | WS | be-gateway `/ingest` | `MK2_EDGE_BIND` | 엣지 미디어 송신 — 토큰 |
| 8767 | HTTP | be-capture `PUT /capture` | `MK2_EDGE_BIND` | 로봇 촬영본 업로드 — 토큰 |
| 9095 | Kafka | Kafka EDGE 리스너 | `MK2_EDGE_BIND` | 원격 엣지 브릿지 |
| 9092 | Kafka | Kafka PLAINTEXT | `127.0.0.1` 고정 | 서버 안 호스트 프로세스(pytest) |
| 7858 | MySQL | MySQL | `MK2_ADMIN_BIND` · `MK2_PORT_MYSQL` | 운영자 · 호스트 도구 |
| 7859 | PostgreSQL | TimescaleDB | `MK2_ADMIN_BIND` · `MK2_PORT_TSDB` | 운영자 · 호스트 도구 |
| 7861 | HTTP | Prometheus | `MK2_ADMIN_BIND` · `MK2_PORT_PROMETHEUS` | 운영자 |
| 7862 | HTTP | Grafana | `MK2_ADMIN_BIND` · `MK2_PORT_GRAFANA` | 운영자 |
| 3100 | HTTP | Loki | `MK2_ADMIN_BIND` · `MK2_PORT_LOKI` | 운영자 |
| 3200 | HTTP | Tempo | `MK2_ADMIN_BIND` · `MK2_PORT_TEMPO` | 운영자 |

엣지 입구 포트(1883 · 4316~4318 · 8765~8767 · 9095)는 장치·엣지 쪽 설정과 짝이라 **고정**이다. 운영자 포트는 `.env` 로 옮길 수 있다.

## 구역 엣지 (`deploy/edge/`)

| 포트 | 서비스 | 바인딩 |
|---|---|---|
| 1883 · 9001 | Mosquitto | `MK2_EDGE_LAN_BIND` (구역 LAN) |
| 4317 · 4318 | OTel Collector (Agent) | `MK2_EDGE_LAN_BIND` |
| 9090 | 엣지 Prometheus (`/federate`) | `MK2_EDGE_TUNNEL_BIND` (터널) |

## 파트별 (현재 코드 기준)

| 파트 | 포트 | 무엇 |
|---|---|---|
| hardware | UDP 5004 | RTP/JPEG 미디어 |
| hardware | UDP 15200 → 15201 | 로봇 상태 중계 → 트윈(Unity 등) |
| hardware | UDP 5009 | Go1 장애물·모션 → 트윈 |
| hardware | UDP 15100 · 15110 → 15101 · 15102 | 트윈 → Go1 명령·경로, Go1 상태·미러 → 트윈 (`unity_bridge.py`) |
| hardware | 8090 · 8091 · 8443 | MJPEG 카메라 뷰 |
| hardware | 9105 | 엣지 가용성 참조 구현 `/metrics` |
| ai | 8775 | `perception-framework` status UI (`tools/status_ui/serve.py`, 이미지 기본 명령) |
| ai | 8000 | 데모 탐지 API |
| visualization | 5174 · 5175 | viz-debugger UI (dev · preview) |
| visualization | 8790 | viz-debugger 게이트웨이 |
| visualization | 8801 · 8802 · 8803 | STT · 생성 · llama-server |
| visualization | 5173 · 8787 | web-dashboard(동결 기준판) UI · 모의 게이트웨이 |
| drone | **8766** | SAR 데이터 서버 |
| drone | **8767** · 8768 · 18766 | SSH 역터널 |
| drone | 8890 | 드론 에이전트 |
| drone | UDP 14660 | RTCM 중계 |
| drone | 5760 · 14540 · 14551 | MAVLink |
| camera360 | 7866 | 파노라마 수신 |
| camera360 | 10001 ~ 10004 | 소스별 수집(360 · 드론 · 로봇) |
| camera360 | 6380 | Redis Stream |
| camera360 | UDP 5010 | 360 장애물 → 트윈(Unity 등) |
| hardware | UDP 25201 · 25010 · 25009 (예) → 25500 | 트윈 게이트웨이 받기 (Unity와 같은 기기일 때) → 중립 JSON 내보내기. `hardware/twin/twin.example.json` |
| camera360 | 1935 | RTMP(카메라 → 노트북) |
| osmocam | 38090 | MJPEG `/stream` |

## 충돌 정리 (2026-10-26)

| 포트 | 충돌 | 상태 |
|---|---|---|
| 8765 | 중앙 be-gateway ↔ ai status UI | ✅ 해결 — status UI 기본값을 **8775** 로 옮겼다 |
| 8766 | 중앙 be-gateway `/ingest` ↔ drone SAR 데이터 서버 | 🟡 기기가 달라 실제로는 안 부딪힌다 — 아래 참고 |
| 8767 | 중앙 be-capture ↔ drone 역터널(`-L`) | 🟡 기기가 달라 실제로는 안 부딪힌다 — 아래 참고 |

드론의 8766 은 **Pi · 현장 노트북**에서, 8767 은 **현장 노트북**의 터널 입구다. 중앙 서버에서 도는 드론 구성
(`deploy/server/sar-server.sh`)은 8768 · 18766 만 쓰므로 중앙 백엔드와 겹치지 않는다. 현장 장비에 이미 설치된 값이라
기본값은 바꾸지 않았다.

**한 기기에 다 올릴 때**(전시 시연용 노트북 한 대 등)만 드론 쪽을 환경변수로 옮긴다 — 코드 수정은 필요 없다.

```bash
PORT=8776 ./sar-laptop.sh                          # 노트북 SAR 데이터 서버 (Pi 는 SAR_DATA_PORT)
LOCAL_DATA=8776 LOCAL_VIEW=8777 ./sar-tunnel.sh    # 터널 입구
```

**규칙(새 서비스):** `8765~8769` 는 중앙 백엔드 예약, 파트별 보조 서비스는 `8770~8799`.
