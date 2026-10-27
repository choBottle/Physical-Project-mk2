# 배포 가이드 — 빈 서버에서 MK2 플랫폼 세우기

> 이 문서의 목표: **이 프로젝트를 처음 보는 사람(다른 기관·새 기여자)이 빈 리눅스 서버 한 대에서 30분 안에
> 중앙 서버 스택을 세우고, "데이터가 흐른다"까지 스스로 확인할 수 있게 하는 것.**
> 우리 연구실 서버에서만 도는 상태는 배포된 상태가 아니다.

| 문서 | 내용 |
|---|---|
| **이 문서** | 전체 그림 · 요구 사양 · 설치 절차 · 검증 · 문제 해결 |
| [database.md](database.md) | DB 스키마(MySQL·TimescaleDB) · 권한 설계 · 스키마 변경 절차 · 백업/복구 |
| [observability.md](observability.md) | Prometheus · Loki · Tempo · Grafana · 지표 목록 · 알림 · 엣지 페더레이션 |
| [edge.md](edge.md) | 구역 엣지 노드(라즈베리파이) 세우기 · 중앙과 연결 |
| [security.md](security.md) | 노출 정책 · 토큰 · 터널 · 운영 전환 체크리스트 |
| [operations.md](operations.md) | 운영 런북 — 재기동 · 업그레이드 · 백업 · 알림별 대응 |
| [pluggability.md](pluggability.md) | 바꿔 끼우기 — 다른 360 카메라, 다른 검출 모델, Unity가 아닌 트윈. 설정으로 되는 것과 아직 고정된 것 |
| [endpoints.md](endpoints.md) | 외부 서버 주소가 바뀔 때 — 객체 탐지 스트림·인지·앵커 서버, Unity PC를 옮긴 뒤 바꿀 곳과 확인 |
| [e2e.md](e2e.md) | 전 구간 시험 — 실제 말단 노드 코드 → 중앙 → 관제 화면 (장비 없이 · 실장비) |
| [../PORTS.md](../PORTS.md) | 포트 레지스트리(단일 출처) |

---

## 1. 전체 그림

MK2 는 다섯 구간으로 나뉜다. 이 저장소의 `deploy/` 는 **구간 2(엣지)와 구간 4(중앙 서버)** 를 재현한다.

```text
[1 말단]            [2 구역 엣지]                 [3 터널]         [4 중앙 서버]                          [5 사용자]
센서·로봇·드론 ─MQTT─▶ Mosquitto                                  Mosquitto ─▶ be-ingest ─▶ Kafka ─┬▶ be-storage ─▶ TimescaleDB · MySQL
카메라        ─OTLP─▶ OTel Collector(Agent) ──── Tailscale ────▶ OTel Collector ─▶ Prometheus·Loki·Tempo ─▶ Grafana
              ─영상─▶ (미디어 송신)          (업무·관측·영상     be-gateway /ingest ──────────────┴▶ be-gateway /state·/media ─▶ 관제 화면
                      엣지 Prometheus ◀──── 단일 터널 공유) ── Prometheus(edge_federate)
```

| 데이터 성격 | 채널 | 저장 |
|---|---|---|
| 업무(계측·상태·생존) | MQTT(말단) → Kafka(백본) | 계측 = **TimescaleDB**, 감사·레지스트리·임무 실행 기록 = **MySQL** |
| 관측(metric·log·trace) | OpenTelemetry(OTLP) | **Prometheus** · **Loki** · **Tempo** |
| 영상 | 별도 미디어 경로(WS, 방식 B) | 중계만(촬영본은 파일시스템 + MySQL 메타) |
| 브라우저 | WebSocket(be-gateway) | 저장 안 함(실시간 push) |

설계 근거: [`server/docs/be/00-architecture.md`](../../server/docs/be/00-architecture.md).

### 중앙 서버 구성요소 (`deploy/docker-compose.yml`)

| 서비스 | 이미지(고정 버전) | 역할 |
|---|---|---|
| `mosquitto` | `eclipse-mosquitto:2.0.22` | MQTT 브로커 — 말단·엣지 발행 수용 |
| `kafka` + `kafka-init` | `apache/kafka:4.1.0` (KRaft) | 업무 백본 · 다중 소비자. `kafka-init` 가 토픽 3개 생성 후 종료 |
| `mysql` | `mysql:8.4` | 감사 · 레지스트리 · 임무 실행 기록 · 촬영본 메타 |
| `timescaledb` | `timescale/timescaledb:2.30.0-pg16` | 계측 시계열(`telemetry` 하이퍼테이블) |
| `be-ingest` | `mk2-backend` (`server/Dockerfile`) | MQTT 구독 → 공통 규격 2단 검증 → Kafka |
| `be-storage` | 〃 | Kafka → TimescaleDB · MySQL 레지스트리 |
| `be-gateway` | 〃 | Kafka → WebSocket(`/state`·`/media`) + 엣지 미디어 입구(`/ingest`) |
| `be-capture` | 〃 | 촬영본 업로드(`PUT /capture`) |
| `otel-collector` | `otel/opentelemetry-collector-contrib:0.150.1` | 관측 3종 수집·분배 |
| `prometheus` | `prom/prometheus:v3.9.1` | metric 저장 + 알림 규칙 + 엣지 페더레이션 |
| `loki` | `grafana/loki:3.5.5` | log 저장(보존 14일) |
| `tempo` | `grafana/tempo:2.8.2` | trace 저장(보존 168시간) |
| `grafana` | `grafana/grafana:12.2.0` | 운영 대시보드(데이터소스·대시보드 자동 프로비저닝) |

---

## 2. 요구 사양

| 항목 | 최소 | 권장(현장 1~3 구역) |
|---|---|---|
| OS | Docker 가 도는 64-bit 리눅스(Ubuntu 22.04/24.04 검증 대상) | 같음 |
| CPU / RAM | 4 코어 / 8 GB | 8 코어 / 16 GB 이상 |
| 디스크 | 40 GB | 200 GB 이상 SSD (TimescaleDB·Prometheus·촬영본이 자란다) |
| 소프트웨어 | Docker Engine 24+ · Docker Compose v2.24+ · git · bash | + Tailscale(또는 WireGuard) — 엣지를 붙일 때 |

> Windows/macOS 의 Docker Desktop 에서도 개발·시연 용도로 그대로 돈다(이 문서의 절차는 Docker Desktop 29 에서 검증했다).
> 단 운영 배치는 리눅스를 기준으로 한다.

---

## 3. 설치 — 다섯 단계

```bash
# ① 받기
git clone https://github.com/<org>/Physical-Project-mk2.git
cd Physical-Project-mk2/deploy

# ② 환경변수 — 비밀번호·토큰 8개를 무작위 영숫자 32자로 자동 생성한다(.env, 권한 600, 커밋되지 않음)
./scripts/init-env.sh

# ③ 기동 — 백엔드 이미지를 빌드하고 13개 서비스가 healthy 가 될 때까지 기다린다(첫 실행 3~5분)
docker compose up -d --build --wait

# ④ (선택) 데모 레지스트리 — 구역 2개·장치 2개(그중 하나는 미배포) 선언
./scripts/seed-demo.sh

# ⑤ 검증 — "떠 있다"가 아니라 "흐른다"까지
./scripts/healthcheck.sh
```

마지막 줄이 `결과: 통과 32 · 실패 0` 이면 배포가 끝난 것이다.

말단 장치까지 이어 보려면 `./scripts/e2e-sim.sh` — 실제 노드 코드를 가짜 센서로 붙여 관제 화면 구독까지 본다([e2e.md](e2e.md)).

### 처음 기동할 때 자동으로 일어나는 일

사람이 손으로 하던 서버 작업을 전부 컨테이너 최초 초기화로 옮겼다. 그래서 **같은 결과가 어느 서버에서든 난다.**

| 단계 | 누가 | 무엇 |
|---|---|---|
| MySQL 초기화 | `deploy/server/initdb/mysql/10-mk2-init.sh` | `server/infra/sql/` 의 스키마 → 앱 계정 → `media_capture` → 테이블별 차등 권한 (순서가 강제다: 테이블이 있어야 GRANT 가 걸린다) |
| TimescaleDB 초기화 | `deploy/server/initdb/timescaledb/100_mk2_init.sh` | 하이퍼테이블 스키마 → 앱 계정(SELECT·INSERT 만) → `pg_hba` 를 도커 대역의 앱 계정으로만 한정 |
| Kafka 토픽 | `kafka-init` 서비스 | `mk2.telemetry.{state,status,heartbeat}` 생성(자동 생성은 꺼 둔다 — 오타 토픽 방지) |
| 관측 연결 | Grafana 프로비저닝 | Prometheus·Loki·Tempo 데이터소스 + `MK2 Backend Overview` 대시보드 |

> ⚠ 초기화 스크립트는 **데이터 볼륨이 비어 있을 때 한 번만** 돈다. 스키마를 바꾼 뒤 기존 서버에 반영하는 절차는
> [database.md §4](database.md#4-스키마-변경-절차-마이그레이션).

### 접속 주소 (서버 안에서)

| 무엇 | 주소 | 비고 |
|---|---|---|
| Grafana | http://127.0.0.1:7862 | `GRAFANA_ADMIN_USER` / `GRAFANA_ADMIN_PASSWORD` (`deploy/.env`) |
| Prometheus | http://127.0.0.1:7861 | Alerts 탭에 MK2 알림 규칙 |
| WS 게이트웨이 | ws://127.0.0.1:8765/state?token=`MK2_WS_TOKEN` | 확인용 뷰어: `server/backend/gateway/console.html` |
| MySQL / TimescaleDB | 127.0.0.1:7858 / 127.0.0.1:7859 | 앱 계정 `mk2_app` |

서버 밖(운영자 PC)에서 Grafana 를 보려면 포트를 열지 말고 SSH 터널을 쓴다: `ssh -L 7862:127.0.0.1:7862 <서버>`.

---

## 4. 엣지를 붙일 때 — 노출 정책 바꾸기

기본값은 **모든 입구가 `127.0.0.1`** 이다. 서버 밖에서는 아무것도 붙지 못한다(안전한 기본값).
엣지·뷰어를 붙일 때 `deploy/.env` 두 줄을 서버의 **터널 주소**로 바꾼다:

```bash
MK2_EDGE_BIND=100.x.y.z                # tailscale ip -4 의 결과
MK2_KAFKA_EDGE_ADVERTISED=100.x.y.z    # 같은 주소 — localhost 로 두면 엣지가 자기 자신으로 되돌아간다
```

```bash
docker compose up -d     # 바뀐 서비스만 재생성된다
```

> 🔴 `0.0.0.0` 으로 두지 않는다. MQTT(익명)·OTLP·Kafka EDGE(평문)는 인증이 없는 입구라, 터널 주소에만 바인딩하는
> 것이 곧 접근 통제다. 자세한 근거와 운영 전환 체크리스트는 [security.md](security.md).

엣지 쪽 절차는 [edge.md](edge.md).

---

## 5. 설정 한눈에 — 무엇을 어디서 바꾸나

| 바꾸려는 것 | 파일 |
|---|---|
| 비밀번호·토큰·노출 주소·포트·보존 기간 | `deploy/.env` (템플릿 `deploy/.env.example`) |
| 서비스 구성·이미지 버전 | `deploy/docker-compose.yml` |
| DB 스키마 (정본) | `server/infra/sql/*.sql` — **사본을 두지 않는다**. compose 가 이 파일을 직접 읽는다 |
| Prometheus 수집 대상 · 알림 규칙 | `deploy/server/config/prometheus.yml` · `prometheus-rules.yml` |
| Collector 파이프라인 | `deploy/server/config/otel-collector.yaml` |
| Loki · Tempo 보존 | `deploy/server/config/loki.yaml` · `tempo.yaml` |
| Grafana 대시보드 | `deploy/server/grafana/dashboards/*.json` |
| 백엔드 동작 파라미터 | 환경변수 — 단일 출처 `server/backend/settings.py` 상단 표 |

**운영 서버와 저장소가 같은 파일을 본다.** 이전에는 서버의 compose·설정 파일이 비밀번호·내부 주소 때문에
저장소 밖(gitignore)에 있어서, 서버를 다시 세우거나 다른 기관에 넘길 방법이 없었다. 이제 비밀값은 `.env` 하나로
분리됐고 나머지는 전부 커밋된다.

---

## 6. 문제 해결

| 증상 | 원인 · 조치 |
|---|---|
| `Bind for 0.0.0.0:7862 failed: port is already allocated` | 같은 서버에 다른 서비스가 그 포트를 쓴다. `deploy/.env` 의 `MK2_PORT_*` 로 운영자 포트를 옮긴다(엣지 입구 포트는 장치 설정과 짝이라 고정) |
| `mysql`/`timescaledb` 가 `unhealthy` 에 머문다 | `docker compose logs mysql \| grep mk2-init` — 초기화 스크립트가 어느 단계에서 멈췄는지 본다. 셸 스크립트가 CRLF 로 체크아웃되면 `bad interpreter` 로 죽는다 → `git config core.autocrlf false` 후 다시 체크아웃(저장소 `.gitattributes` 가 LF 를 강제한다) |
| `.env` 를 다시 만들었더니 백엔드가 DB 에 못 붙는다 | DB 비밀번호는 **볼륨 최초 초기화 때** 박힌다. 새 `.env` 와 기존 볼륨이 어긋난 것. 시험 서버면 `docker compose down -v` 로 볼륨까지 지우고 다시, 운영 서버면 [database.md §5](database.md#5-비밀번호-교체) |
| be-gateway 가 `exit 2` | loopback 밖 바인딩인데 토큰이 비었다. `MK2_WS_TOKEN`·`MK2_EDGE_TOKEN` 확인 |
| Tempo `/ready` 가 503 | 기동 뒤 15초 워밍업. 그 뒤에도 503 이면 `tempo.yaml` 의 `ingester.lifecycler` 확인 |
| 엣지가 Kafka 9095 에 붙는데 데이터가 안 간다 | `MK2_KAFKA_EDGE_ADVERTISED` 가 `localhost` 다 — 브로커가 "localhost 로 오라"고 답한다 |
| Grafana 에 백엔드 지표가 없다 | 백엔드 export 주기 15초 + scrape 5초. 1분 기다린 뒤 `./scripts/healthcheck.sh` 의 4번 절 |

그래도 안 되면 [이슈](../../.github/ISSUE_TEMPLATE/deployment.yml)에 `./scripts/healthcheck.sh` 출력과
`docker compose ps -a` · 해당 서비스 로그를 붙여 올린다.

---

## 7. 이 절차의 검증 기록

| 날짜 | 환경 | 결과 |
|---|---|---|
| 2026-10-26 | Windows 11 · Docker Desktop 29.5 (볼륨 전부 삭제 후 이 문서 §3 그대로) | 13개 서비스 healthy · `healthcheck.sh` **32/32** · 백엔드 회귀 `pytest` **351 passed, 2 skipped, 0 failed** · 백업 → 복구 왕복 후 32/32. (앞선 회차에서 타이밍 의존 시험 1건이 한 번 실패 — [operations.md](operations.md#알려진-사항)) |
| 2026-10-26 | 같은 환경 · `deploy/edge` | 엣지 Collector 로 보낸 log 가 중앙 Loki 에 `zone_id`·`agg_layer=edge` 로 도착 |
| 매 PR | GitHub Actions `ubuntu-latest` | [`deploy-smoke`](../../.github/workflows/deploy-smoke.yml) — 빈 러너에서 `up --wait` → `healthcheck.sh` → `e2e-sim.sh` |

**"우리 개발 환경에서는 되는데 새 환경에서는 안 된다"를 사람이 아니라 CI 가 매번 확인한다.**
