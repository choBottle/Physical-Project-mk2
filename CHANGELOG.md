# 변경 기록

형식은 [Keep a Changelog](https://keepachangelog.com/ko/1.1.0/), 버전은 [Semantic Versioning](https://semver.org/lang/ko/)
— 무엇이 "공개 API" 인지는 [docs/RELEASE.md](docs/RELEASE.md#1-버전-규칙--semantic-versioning).
각 판에 **배포 변경**(새 환경변수 · 포트 · DB 마이그레이션 · 이미지 버전) 절을 따로 둔다.

## [Unreleased] — v1.0.0 후보

### 추가
- **모노레포 통합** — 팀 브랜치 7개(`ldg_BE` · `HW` · `jny_AI` · `khw_VZ` · `Junho_drone` · `360camera_work` · `osmo-nano-stream`)를
  `server/` · `hardware/` · `ai/` · `visualization/` · `drone/` · `camera360/` · `osmocam/` 로 히스토리 보존 통합
- **재현 가능한 배포** `deploy/`
  - 중앙 서버 스택 13개 서비스(Mosquitto · Kafka · MySQL · TimescaleDB · 백엔드 4 · OTel Collector · Prometheus · Loki · Tempo · Grafana)
  - 백엔드 컨테이너 이미지 `server/Dockerfile`
  - DB 최초 초기화(스키마 · 앱 계정 · 테이블별 권한 · `pg_hba` 한정) — 정본 `server/infra/sql/` 을 직접 사용
  - Prometheus 알림 규칙 6종 · Grafana 데이터소스/대시보드 프로비저닝
  - 구역 엣지 스택 `deploy/edge/` (Mosquitto · OTel Agent · 엣지 Prometheus)
  - 스크립트: `init-env.sh` · `healthcheck.sh`(32항목) · `seed-demo.sh` · `backup.sh` · `restore.sh`
- **문서** — 배포 가이드 · DB · 관측 · 엣지 · 보안 · 운영 런북 · 포트 레지스트리 · 릴리스 정책 · 공개 준비 점검표
- **오픈소스 기본** — MIT `LICENSE` · `THIRD_PARTY_NOTICES` · `CONTRIBUTING` · `CODE_OF_CONDUCT` · `SECURITY` · `GOVERNANCE` · CODEOWNERS · 이슈/PR 템플릿
- **CI** — `ci`(배포 설정 검증 · 규격 예제 · AI 시험 · 비밀값 스캔) · `deploy-smoke`(빈 러너에서 스택 기동 → 헬스체크 → 백엔드 회귀 → 백업/복구) · `release`(GHCR 이미지 · Release 초안)

### 변경
- `server/backend/settings.py` — 발행자 기본 브로커 주소를 특정 서버의 공인 IP 에서 `localhost` 로(`MK2_BROKER_HOST` 로 지정)
- 드론 CI 워크플로를 `drone/.github/` → 루트 `.github/workflows/drone.yml` 로 이동(하위 폴더 워크플로는 실행되지 않는다)

### 제거
- 추적되던 산출물: `visualization/web-dashboard/.vite/deps`(빌드 캐시) · `camera360/360camera_work_260921.zip`(폴더 스냅샷) · `hardware/pi/robot/go1_sdk_pc.cpp.bak3`

### 배포 변경
- 연구실 서버(수동 운영)와의 차이: 도커 대역을 `172.28.0.0/16` 으로 **고정**(`MK2_NET_SUBNET`), MySQL 앱 계정 host 가
  `'172.18.%'` → `MK2_DB_APP_HOST`(기본 `172.28.%`). 백엔드는 systemd 대신 컨테이너. 호스트 포트 번호는 동일.
- OTel Collector 가 4316 과 4317 을 **둘 다** 받는다(HW · AI 노드의 기본값 4317 과 정합).
- Tempo 의 호스트 OTLP 입구(4317)는 열지 않는다(Collector 우회 금지).
