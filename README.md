# Physical-Project-mk2

**재난·국가 인프라 현장을 위한 오픈 피지컬 AI 플랫폼** — 센서·로봇·드론·카메라가 만든 데이터를 엣지와 중앙에서
성격별로 수집·저장·관측하고, 디지털 트윈과 관제 화면으로 잇는다.

[![ci](https://github.com/choBottle/Physical-Project-mk2/actions/workflows/ci.yml/badge.svg)](https://github.com/choBottle/Physical-Project-mk2/actions/workflows/ci.yml)
[![deploy-smoke](https://github.com/choBottle/Physical-Project-mk2/actions/workflows/deploy-smoke.yml/badge.svg)](https://github.com/choBottle/Physical-Project-mk2/actions/workflows/deploy-smoke.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

> 🇬🇧 [English summary](#english-summary)

---

## 왜 오픈소스인가

"우리 연구실에서 돈다"로 끝나는 프로젝트는 다른 곳에서 쓸 수 없다. 이 프로젝트의 목표는 **ROS 2 가 로봇 분야에서 그렇듯,
국방·기후환경·재난 대응 기관이 가져다 자기 현장에 세울 수 있는 열린 플랫폼**이다. 그래서 처음부터

- 특정 장치·프로토콜·저장 제품을 핵심에 박지 않고(MQTT·Kafka·OpenTelemetry·Tailscale 은 **교체 가능한 현재 구현**),
- 파트 사이의 약속을 코드가 아니라 **JSON Schema 공통 규격**으로 두고,
- **빈 서버에서 한 번에 재현되는 배포**와 그 배포를 설명하는 문서를 코드와 같은 무게로 관리한다.

> 설계 → 구현 → 시험 → **배포 1.0** 까지. 배포 절차는 사람이 아니라 CI 가 매 PR 마다 빈 환경에서 다시 증명한다.

## 구조

```text
[말단]             [구역 엣지]                    [중앙 서버]                                       [사용자]
센서·로봇·드론 ─▶ Mosquitto · OTel Agent ═터널═▶ Kafka ─▶ 저장(TimescaleDB · MySQL)            ─▶ 관제 화면
360·드론 카메라 ─▶ 엣지 Prometheus(raw)          OTel Collector ─▶ Prometheus · Loki · Tempo  ─▶ Grafana
                                                  WS 게이트웨이(실시간 상태 · 영상 중계)
```

| 폴더 | 파트 | 내용 | 담당 |
|---|---|---|---|
| [`server/`](server/) | 백엔드 | 수집(ingest) · 저장 · WS 게이트웨이 · 촬영본 수신 · **공통 데이터 규격** · DB 스키마 | @daegyu10 |
| [`hardware/`](hardware/) | 하드웨어 · 엣지 | 라즈베리파이 센서/로봇(Go1 · RoboMaster EP)/액추에이터 노드 · 엣지 참조 구현 | @choBottle |
| [`ai/`](ai/) | AI | perception-framework — 능력 기반 인지·위험 판단·계획 · DEVS 시뮬레이터 | @JNY03 |
| [`visualization/`](visualization/) | 가시화 | viz-debugger 관제 화면 · 계약(JSON Schema) · STT/생성 실험 | @khw18033 |
| [`drone/`](drone/) | 드론 | PX4 SAR(합성개구레이더) 패스 · RTK 중계 · 비행 데이터 | jhjeong |
| [`camera360/`](camera360/) | 360 카메라 | Insta360 앵커 카메라 → 지면 좌표 장애물 → Unity | @daegyu10 |
| [`osmocam/`](osmocam/) | 카메라 소스 | DJI Osmo 를 무선 MJPEG 소스로 (MIT 포크) | @khw18033 |
| [`deploy/`](deploy/) | **배포** | 중앙 서버 · 엣지 스택(compose) · 관측 설정 · DB 초기화 · 운영 스크립트 | 공동 |
| [`docs/`](docs/) | 문서 | 배포 가이드 · 포트 · 릴리스 · 공개 준비 점검 | 공동 |

각 폴더는 원래 팀별 브랜치였고 **커밋 히스토리를 보존한 채** 통합했다(`git log -- server/` 로 그 파트의 이력을 본다).

## 빠른 시작 — 중앙 서버 스택

Docker(Compose v2.24+)만 있으면 된다.

```bash
git clone https://github.com/choBottle/Physical-Project-mk2.git
cd Physical-Project-mk2/deploy
./scripts/init-env.sh                 # 비밀번호·토큰 자동 생성 → deploy/.env
docker compose up -d --build --wait   # 13개 서비스 (첫 실행 3~5분)
./scripts/seed-demo.sh                # (선택) 데모 구역·장치 선언
./scripts/healthcheck.sh              # 업무 관통 · 관측 3종 · DB 권한까지 32항목
```

- Grafana http://127.0.0.1:7862 (`deploy/.env` 의 `GRAFANA_ADMIN_*`) → **MK2 Backend Overview**
- 시험 데이터 보내기: `docker compose exec be-ingest python tests/publisher.py --host mosquitto --count 10`

전체 절차·요구 사양·엣지 연결·문제 해결: **[배포 가이드](docs/deployment/README.md)**

## 문서

| 읽는 사람 | 문서 |
|---|---|
| 배포·운영하는 사람 | [배포 가이드](docs/deployment/README.md) · [DB](docs/deployment/database.md) · [관측](docs/deployment/observability.md) · [엣지](docs/deployment/edge.md) · [보안](docs/deployment/security.md) · [운영 런북](docs/deployment/operations.md) · [포트](docs/PORTS.md) |
| 기여하는 사람 | [CONTRIBUTING](CONTRIBUTING.md) · [GOVERNANCE](GOVERNANCE.md) · [행동 강령](CODE_OF_CONDUCT.md) · [릴리스 정책](docs/RELEASE.md) |
| 설계를 알고 싶은 사람 | [아키텍처 기준](server/docs/be/00-architecture.md) · [공통 규격](server/contracts/common/README.md) · 각 파트 폴더의 README |

## 상태

**v1.0.0 후보 단계.** 플랫폼·배포 기반은 갖춰졌고(검증 기록: [배포 가이드 §7](docs/deployment/README.md#7-이-절차의-검증-기록)),
1.0 전에 남은 일은 [릴리스 기준](docs/RELEASE.md#3-v100-출시-기준)과 [공개 준비 점검표](docs/OPEN_SOURCE_READINESS.md)에 있다.
인증·인가(RBAC)·TLS 는 1.x 로드맵이며, 그 전까지는 **터널 안에서만** 운영한다([보안](docs/deployment/security.md)).

## 라이선스

[MIT](LICENSE). 포함된 제3자 구성요소(`osmocam/` 등)는 각 원 라이선스를 따른다 — [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

---

## English summary

**Physical-Project-mk2** is an open edge-to-cloud platform for physical AI in disaster-response and national-infrastructure
settings. Sensors, robots, drones and cameras publish over MQTT/OTLP to zone edge nodes; a central server bridges business
data through Kafka into TimescaleDB (telemetry) and MySQL (audit, registry, mission records), routes observability to
Prometheus/Loki/Tempo, and pushes live state and video to operator consoles over WebSocket. Cross-part interfaces are defined
as JSON Schema contracts, and every technology choice (MQTT, Kafka, OpenTelemetry, Tailscale) is a replaceable implementation.

**Quick start:** `cd deploy && ./scripts/init-env.sh && docker compose up -d --build --wait && ./scripts/healthcheck.sh`
— a reproducible 13-service stack, verified from an empty runner on every pull request.
Documentation is primarily in Korean; issues and pull requests in English are welcome.
