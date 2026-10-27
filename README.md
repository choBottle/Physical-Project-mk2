# Physical-Project-mk2

<p align="center">
  <a href="docs/deployment/README.md"><img src="https://img.shields.io/badge/Docs-배포_가이드-FFD700?style=for-the-badge" alt="Documentation"></a>
  <a href="https://github.com/choBottle/Physical-Project-mk2/discussions"><img src="https://img.shields.io/badge/Discussions-181717?style=for-the-badge&logo=github&logoColor=white" alt="Discussions"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-green?style=for-the-badge" alt="License: MIT"></a>
  <a href="https://github.com/choBottle/Physical-Project-mk2/releases"><img src="https://img.shields.io/github/v/release/choBottle/Physical-Project-mk2?include_prereleases&style=for-the-badge" alt="Release"></a>
  <a href="README.en.md"><img src="https://img.shields.io/badge/Lang-English-red?style=for-the-badge" alt="English"></a>
</p>

<p align="center">
  <a href="https://github.com/choBottle/Physical-Project-mk2/actions/workflows/ci.yml"><img src="https://github.com/choBottle/Physical-Project-mk2/actions/workflows/ci.yml/badge.svg" alt="ci"></a>
  <a href="https://github.com/choBottle/Physical-Project-mk2/actions/workflows/deploy-smoke.yml"><img src="https://github.com/choBottle/Physical-Project-mk2/actions/workflows/deploy-smoke.yml/badge.svg" alt="deploy-smoke"></a>
</p>

**재난·국가 인프라 현장을 위한 오픈 피지컬 AI 플랫폼.** 센서·로봇·드론·카메라가 만든 데이터를 구역 엣지와 중앙 서버에서
성격별(업무·관측·영상)로 수집·저장·관측하고, 디지털 트윈과 관제 화면으로 잇는다. ROS 2 가 로봇 분야에서 그렇듯,
국방·기후환경·재난 대응 기관이 **가져다 자기 현장에 세울 수 있는 열린 플랫폼**을 목표로 한다.

특정 제품에 묶이지 않는다 — MQTT · Kafka · OpenTelemetry · Tailscale 은 **교체 가능한 현재 구현**이고,
파트 사이의 약속은 코드가 아니라 **JSON Schema 공통 규격**이다.

<table>
<tr><td><b>빈 서버에서 한 번에 재현</b></td><td>중앙 스택 13개 서비스(Mosquitto · Kafka · TimescaleDB · MySQL · OTel Collector · Prometheus · Loki · Tempo · Grafana · 백엔드 4종)를 <code>docker compose</code> 한 번으로. 비밀값은 <code>.env</code> 하나, DB 스키마·권한은 최초 기동 때 자동 초기화.</td></tr>
<tr><td><b>데이터 성격이 채널을 정한다</b></td><td>업무 = MQTT(말단) → Kafka(백본), 관측 = OpenTelemetry, 영상 = 별도 미디어 경로, 브라우저 = WebSocket. 기능이 늘어도 채널은 늘지 않는다.</td></tr>
<tr><td><b>부하가 구역 수에 비례</b></td><td>구역마다 엣지(Mosquitto · OTel Agent · 엣지 Prometheus)가 1차 수용하고, 중앙은 터널 너머로 페더레이션한다.</td></tr>
<tr><td><b>말단부터 화면까지</b></td><td>라즈베리파이 센서·로봇(Go1 · RoboMaster EP)·액추에이터 노드, PX4 드론 SAR, Insta360 앵커 카메라 → 중앙 → <code>viz-debugger</code> 관제 화면 · Unity 디지털 트윈.</td></tr>
<tr><td><b>능력 기반 AI</b></td><td><code>perception-framework</code> — 인지·위험 판단·계획을 장치 능력(capability) 단위로 조립, DEVS 시뮬레이터 포함.</td></tr>
<tr><td><b>스스로 관측한다</b></td><td>장치만이 아니라 백엔드 자신도 metric · log · trace 를 낸다. 대시보드 · 알림 규칙까지 저장소에 커밋되어 있다.</td></tr>
<tr><td><b>배포를 CI 가 증명</b></td><td>매 PR 마다 빈 러너에서 스택을 세우고 헬스체크(32항목) → 실제 말단 노드 코드로 전 구간 시험 → 백엔드 회귀 → 백업·복구 왕복까지 돈다.</td></tr>
</table>

---

## 빠른 설치 — 중앙 서버

### Linux · macOS · Windows(WSL2 또는 Git Bash)

Docker(Compose v2.24+)만 있으면 된다.

```bash
git clone https://github.com/choBottle/Physical-Project-mk2.git
cd Physical-Project-mk2/deploy
./scripts/init-env.sh                 # 비밀번호·토큰 자동 생성 → deploy/.env
docker compose up -d --build --wait   # 13개 서비스 (첫 실행 3~5분)
```

> **빌드 없이:** 릴리스 이미지를 쓰려면 `deploy/.env` 에 `MK2_BACKEND_IMAGE=ghcr.io/chobottle/mk2-backend:<버전>` 을 넣고
> `docker compose up -d --wait` — 이미지는 로그인 없이 받아진다.

> **엣지 · 장치:** 구역 엣지는 [`deploy/edge/`](deploy/edge/), 라즈베리파이 노드는 [`hardware/pi/deploy/`](hardware/pi/deploy/)
> (`install-units.sh --user <사용자>`). 절차는 [엣지 가이드](docs/deployment/edge.md).

---

## 시작하기

```bash
./scripts/seed-demo.sh     # (선택) 데모 구역·장치 선언
./scripts/healthcheck.sh   # "떠 있다"가 아니라 "흐른다" — 업무 관통 · 관측 3종 · DB 권한 (32항목)
./scripts/e2e-sim.sh       # 실제 말단 노드 코드(가짜 센서) → 중앙 → 관제 구독 · 저장 · 관측 (10항목)
./scripts/backup.sh        # 백업 (복구: ./scripts/restore.sh)
```

- **Grafana** http://127.0.0.1:7862 (`deploy/.env` 의 `GRAFANA_ADMIN_*`) → **MK2 Backend Overview**
- **시험 데이터:** `docker compose exec be-ingest python tests/publisher.py --host mosquitto --count 10`
- **관제 화면:** `visualization/viz-debugger` 에서 `npm ci && npm run dev` → 연결 관리에서 게이트웨이를 `ws://127.0.0.1:8765/state?token=<MK2_WS_TOKEN>`, 구역을 `zoneA` 로

📖 **[배포 가이드 전체 →](docs/deployment/README.md)**

---

## 구조

```text
[말단]             [구역 엣지]                    [중앙 서버]                                       [사용자]
센서·로봇·드론 ─▶ Mosquitto · OTel Agent ═터널═▶ Kafka ─▶ 저장(TimescaleDB · MySQL)            ─▶ 관제 화면
360·드론 카메라 ─▶ 엣지 Prometheus(raw)          OTel Collector ─▶ Prometheus · Loki · Tempo  ─▶ Grafana
                                                  WS 게이트웨이(실시간 상태 · 영상 중계)        ─▶ Unity 트윈
```

| 폴더 | 파트 | 내용 | 담당 |
| --- | --- | --- | --- |
| [`server/`](server/) | 백엔드 | 수집(ingest) · 저장 · WS 게이트웨이 · 촬영본 수신 · **공통 데이터 규격** · DB 스키마 | @daegyu10 |
| [`hardware/`](hardware/) | 하드웨어 · 엣지 | 라즈베리파이 센서/로봇(Go1 · RoboMaster EP)/액추에이터 노드 · Unity 브리지 · 엣지 참조 구현 | @choBottle |
| [`ai/`](ai/) | AI | perception-framework — 능력 기반 인지·위험 판단·계획 · DEVS 시뮬레이터 | @JNY03 |
| [`visualization/`](visualization/) | 가시화 | viz-debugger 관제 화면(드론 SAR 화면 포함) · 계약(JSON Schema) · STT/생성 실험 | @khw18033 |
| [`drone/`](drone/) | 드론 | PX4 SAR(합성개구레이더) 패스 · RTK 중계 · 비행 데이터 · 레이더 연동 | jhjeong |
| [`camera360/`](camera360/) | 360 카메라 | Insta360 앵커 카메라 → 지면 좌표 장애물 → Unity | @daegyu10 |
| [`osmocam/`](osmocam/) | 카메라 소스 | DJI Osmo 를 무선 MJPEG 소스로 (MIT 포크) | @khw18033 |
| [`deploy/`](deploy/) | **배포** | 중앙 서버 · 엣지 스택(compose) · 관측 설정 · DB 초기화 · 운영 스크립트 | 공동 |
| [`docs/`](docs/) | 문서 | 배포 가이드 · 포트 · 릴리스 · 공개 준비 점검 | 공동 |

각 폴더는 원래 팀별 브랜치였고 **커밋 히스토리를 보존한 채** 통합했다(`git log -- server/` 로 그 파트의 이력을 본다).

---

## 문서

| 문서 | 다루는 것 |
| --- | --- |
| [배포 가이드](docs/deployment/README.md) | 전체 그림 · 요구 사양 · 설치 절차 · 검증 · 문제 해결 |
| [DB](docs/deployment/database.md) | MySQL · TimescaleDB 스키마 · 권한 설계 · 스키마 변경 · 백업/복구 |
| [관측](docs/deployment/observability.md) | Prometheus · Loki · Tempo · Grafana · 지표 목록 · 알림 · 엣지 페더레이션 |
| [엣지](docs/deployment/edge.md) | 구역 엣지 노드 세우기 · 중앙과 연결 · 장치 노드 설치 |
| [전 구간 시험](docs/deployment/e2e.md) | 말단 → 중앙 → 관제 화면 (장비 없이 · 실장비) · 검증 기록 |
| [보안](docs/deployment/security.md) | 노출 정책 · 토큰 · 터널 · 운영 전환 체크리스트 |
| [운영 런북](docs/deployment/operations.md) | 재기동 · 업그레이드 · 백업 · 알림별 대응 |
| [포트](docs/PORTS.md) | 포트 레지스트리(단일 출처) |
| [릴리스 정책](docs/RELEASE.md) | 버전 규칙 · 릴리스 절차 · 1.0 기준 · 1.x 로드맵 |
| [아키텍처 기준](server/docs/be/00-architecture.md) · [공통 규격](server/contracts/common/README.md) | 설계 원칙 · 파트 간 JSON Schema |

---

## 상태

**v1.0.0 후보 단계** — [`v1.0.0-rc.1`](https://github.com/choBottle/Physical-Project-mk2/releases/tag/v1.0.0-rc.1).
플랫폼·배포 기반은 갖춰졌고, 1.0 전에 남은 일은 [릴리스 기준](docs/RELEASE.md#3-v100-출시-기준)과
[공개 준비 점검표](docs/OPEN_SOURCE_READINESS.md)에 있다. 인증·인가(RBAC)·TLS 는 1.x 로드맵이며, 그 전까지는
**터널 안에서만** 운영한다([보안](docs/deployment/security.md)).

---

## 기여하기

기여를 환영한다! 개발 환경 · 코드 규칙 · PR 절차는 [CONTRIBUTING](CONTRIBUTING.md), 의사결정 방식은 [GOVERNANCE](GOVERNANCE.md).

```bash
git clone https://github.com/choBottle/Physical-Project-mk2.git
cd Physical-Project-mk2
# 파트별 시험 — CI 와 같은 명령
(cd ai/perception-framework && pip install -e ".[dev,mqtt,kafka,otel,sim]" && OTEL_SDK_DISABLED=true python -m pytest -q)
(cd visualization/viz-debugger && npm ci && npm run typecheck && npm run build)
(cd drone && pip install -e ".[test,image,base]" && python -m pytest -q)
(cd deploy && ./scripts/init-env.sh && docker compose up -d --build --wait && ./scripts/healthcheck.sh)
```

---

## 커뮤니티

- 💬 [Discussions](https://github.com/choBottle/Physical-Project-mk2/discussions) — 질문 · 아이디어 · 도입 사례
- 🐛 [Issues](https://github.com/choBottle/Physical-Project-mk2/issues) — 버그 · 배포 문제(`healthcheck.sh` 출력을 함께)
- 🔒 [보안 제보](SECURITY.md) — 공개 이슈 대신 비공개 취약점 제보
- 🤝 [행동 강령](CODE_OF_CONDUCT.md)

---

## 라이선스

MIT — [LICENSE](LICENSE) 참고. 포함된 제3자 구성요소(`osmocam/` · 레이더 연동 코드 등)는 각 원 라이선스를 따른다 —
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

Built by the Physical-Project-mk2 contributors —
[@daegyu10](https://github.com/daegyu10) · [@choBottle](https://github.com/choBottle) · [@JNY03](https://github.com/JNY03) · [@khw18033](https://github.com/khw18033) · jhjeong.
