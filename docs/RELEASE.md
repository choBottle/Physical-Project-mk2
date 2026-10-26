# 릴리스 · 버전 정책 · 1.0 로드맵

## 1. 버전 규칙 — Semantic Versioning

`MAJOR.MINOR.PATCH` ([semver.org](https://semver.org/lang/ko/)). 이 프로젝트에서 **"공개 API"** 는 코드 함수가 아니라
**다른 기관·다른 파트가 기대고 있는 약속**이다:

| 약속 | 정본 | 깨지면 |
|---|---|---|
| 공통 데이터 규격 (공통 헤더 · 채널 본문 · 프레임 헤더 · `frame_ref`) | `server/contracts/common/*.schema.json` · 통합데이터규약 | **MAJOR** |
| MQTT 토픽 구조 `{zone}/{etype}/{eid}/{channel}` · Kafka 토픽 | 규격 문서 · `deploy/docker-compose.yml` | **MAJOR** |
| DB 스키마 | `server/infra/sql/` | 마이그레이션 없이 못 올리면 **MAJOR**, 추가만이면 MINOR |
| 배포 환경변수 · 포트 | `deploy/.env.example` · `docs/PORTS.md` | 이름 변경·삭제 **MAJOR**, 추가 MINOR |
| WS 게이트웨이 경로·메시지 | `/state` · `/media` · `/ingest` · `/capture` | **MAJOR** |

데이터 규격 자체의 판(`schema_version`, 현재 데이터 판 2.0)은 소프트웨어 버전과 별개로 매긴다. 규격이 MAJOR 로 바뀌면
과도기 동안 옛 판도 받는다(현재 v1 프레임 헤더를 받는 것처럼) — 그 기간을 릴리스 노트에 적는다.

## 2. 릴리스 절차

1. `CHANGELOG.md` 의 `[Unreleased]` 를 정리한다 — **배포 변경**(새 환경변수·포트·DB 마이그레이션)을 별도 절로.
2. 후보 태그: `git tag -a v1.0.0-rc.1 -m "…" && git push origin v1.0.0-rc.1`
   → [`release.yml`](../.github/workflows/release.yml) 이 백엔드 이미지를 `ghcr.io/<owner>/mk2-backend:<버전>` 으로 게시하고 GitHub Release 초안을 만든다.
3. **후보 검증**: 빈 서버에서 [배포 가이드](deployment/README.md) 를 그대로 따라 `healthcheck.sh` 통과 + 엣지 1개 연결.
   가능하면 **프로젝트 밖의 사람**이 문서만 보고 해 본다(문서가 실제로 충분한지의 유일한 검증).
4. 정식 태그 `v1.0.0` → Release 공개.
5. 운영 서버 반영은 [operations.md 「업그레이드」](deployment/operations.md#업그레이드-새-릴리스로).

## 3. v1.0.0 출시 기준

"우리 연구실에서 돈다"가 아니라 **"모르는 기관이 받아서 세울 수 있다"** 가 1.0 의 정의다.

### 플랫폼 · 배포 (이번 통합에서 완료)

- [x] 7개 파트를 하나의 저장소로 통합(히스토리 보존) — 원본 브랜치는 무변경
- [x] 중앙 서버 스택을 clone 한 번으로 재현 — `deploy/docker-compose.yml` (13개 서비스, 버전 고정)
- [x] 비밀값을 `.env` 하나로 분리 — 그 외 설정은 전부 커밋(운영 서버 compose 가 저장소 밖에 있던 문제 해소)
- [x] DB 스키마·권한 자동 초기화 — 정본 SQL 을 직접 읽음(사본 없음)
- [x] 관측 스택(Prometheus · Loki · Tempo · Grafana) 설정 · 알림 규칙 · 대시보드 커밋
- [x] 자동 검증 `healthcheck.sh` — 업무 관통 · 관측 3종 · 권한 음성 대조 (32항목)
- [x] 백업 · 복구 스크립트 (왕복 검증)
- [x] 엣지 노드 스택 (`deploy/edge/`) — 엣지 → 중앙 전달 검증
- [x] 배포 문서 7종 (가이드 · DB · 관측 · 엣지 · 보안 · 운영 · 포트)
- [x] 오픈소스 기본 파일 (LICENSE · CONTRIBUTING · CODE_OF_CONDUCT · SECURITY · GOVERNANCE · 이슈/PR 템플릿)
- [x] CI — 빈 러너에서 매 PR 배포 스모크 테스트

### 팀 결정 · 파트별 작업 (1.0 전에 남은 것 — [OPEN_SOURCE_READINESS.md](OPEN_SOURCE_READINESS.md))

- [x] **전 기여자의 MIT 라이선스 동의** (2026-10-26 완료)
- [ ] 하드코딩 제거: 공인 IP · Tailscale 주소 · `/home/<사용자>` 경로 → 환경변수
- [ ] 포트 충돌 3건 해소 ([PORTS.md](PORTS.md))
- [ ] 사진·스크린샷·영상의 개인정보/정밀 위치 검토
- [ ] 레이더 팀 제공 코드 라이선스 확인
- [ ] `drone/` ↔ `visualization/` 의 `viz-debugger` 중복 정리
- [ ] AI `perception-framework` Dockerfile 수정(없는 `examples/` 참조) · 360 카메라 의존성 명세
- [ ] 실 하드웨어(센서 1 · 로봇 1)로 엣지 → 중앙 → 관제 화면 E2E 1회 기록

## 4. 1.x 로드맵

| 항목 | 근거 |
|---|---|
| 인증·인가(RBAC) · TLS/SASL · OTLP 토큰 | BE-Q-04 · [security.md §3](deployment/security.md#3-운영-전환-체크리스트-터널-밖--다기관--공공-배치) |
| 가용성 판정기(MQTT 세션 우선) · 명령 4단계 승격 · 감사 기록 | BE Phase 5~6 |
| 디지털 트윈 (위치·클래스 융합, 커버리지) | BE Phase 7 |
| 엣지 compose 에 업무 브릿지(엣지 ingest → 중앙 Kafka 9095) 포함 | [edge.md §4](deployment/edge.md#4-현재-한계-v10-범위-밖) |
| 가시화(viz-debugger) · AI 프레임워크 컨테이너 이미지 · compose 프로필 | 한 번에 전 파트 시연 |
| Alertmanager · 알림 채널 | [observability.md §4](deployment/observability.md#4-알림-규칙) |
| DB 마이그레이션 도구 | [database.md §4](deployment/database.md#4-스키마-변경-절차-마이그레이션) |
| Helm 차트 / k3s 매니페스트 (다구역 운영) | 기관 단위 배포 |
| 이미지 digest 고정 · 취약점 스캔 · SBOM | 공급망 보안(공공기관 도입 요건) |
