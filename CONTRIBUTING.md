# 기여 가이드

이 프로젝트에 관심을 가져 주어 고맙다. 버그 신고 · 문서 고치기 · 새 장치 어댑터 · **"우리 기관에서 이렇게 배포했다" 기록** 까지
모두 기여다. (English contributions are welcome — 이슈·PR 을 영어로 써도 된다.)

## 1. 시작하기

1. [배포 가이드](docs/deployment/README.md) 대로 로컬에 중앙 스택을 띄운다 — 개발 환경과 배포 환경이 같아야 "내 PC 에서는 되는데" 가 안 생긴다.
2. 고치려는 파트 폴더의 README / CLAUDE.md 를 읽는다. 파트마다 규칙(요구사항 ID 표기, 보고서 형식 등)이 있다.
3. 큰 변경이면 먼저 이슈를 연다. 특히 아래는 **반드시 이슈에서 합의 후** 진행한다(여러 파트·외부 사용자가 기대는 약속이다):
   - 공통 데이터 규격(`server/contracts/common/`) · MQTT/Kafka 토픽 · DB 스키마 · 배포 환경변수 · 포트

## 2. 브랜치와 PR

- `main` 은 항상 배포 가능한 상태다. 작업은 `<파트>/<주제>` 브랜치(예: `server/availability-judge`, `deploy/alertmanager`)에서.
- 커밋 메시지는 [Conventional Commits](https://www.conventionalcommits.org/ko/) 형식을 권장한다: `feat(server): …`, `fix(deploy): …`, `docs: …`
- PR 템플릿의 체크리스트를 채운다. 특히:
  - **배포에 영향이 있나?** (새 환경변수·포트·DB 변경·이미지 버전) → `deploy/` · `docs/` · `CHANGELOG.md` 를 같은 PR 에서 고친다.
  - 비밀값·실제 IP·`/home/<사용자>` 경로가 없는가.
- CI(`ci` · `deploy-smoke` · 파트별)가 초록이어야 머지한다. `deploy-smoke` 는 빈 러너에서 스택을 새로 세워 확인한다.
- 리뷰: 해당 폴더 담당자(`.github/CODEOWNERS`) 1명 이상 승인.

## 3. 원칙 — 배포를 염두에 두고 작업한다

| 하지 않는 것 | 대신 |
|---|---|
| 주소·경로·포트를 코드에 박는다 | 환경변수 + `.env.example` 에 자리표시자 |
| 서버에서 손으로 고치고 저장소에는 안 남긴다 | 설정 파일을 커밋하고(비밀값만 `.env`), 서버는 저장소를 따른다 |
| `:latest` 이미지 | 버전 고정 |
| "떠 있으니 됐다" | `healthcheck.sh` 로 "흐른다"까지 확인, 새 경로를 만들면 healthcheck 에도 추가 |
| 새 포트를 그냥 연다 | [PORTS.md](docs/PORTS.md) 확인·갱신 |
| DB 스키마를 서버에서 ALTER | 정본 SQL + `migrations/` 파일 ([database.md §4](docs/deployment/database.md#4-스키마-변경-절차-마이그레이션)) |

## 4. 시험

| 범위 | 명령 |
|---|---|
| 배포 전체 | `cd deploy && ./scripts/healthcheck.sh` |
| 백엔드 회귀 | `docker compose exec -e MK2_PROMETHEUS_URL=http://prometheus:9090 -e MK2_LOKI_URL=http://loki:3100 -e MK2_TEMPO_URL=http://tempo:3200 be-gateway python -m pytest -q` |
| AI | `cd ai/perception-framework && pip install -e ".[dev,mqtt,kafka,otel,sim]" && pytest -q` |
| 가시화 계약 | `cd visualization/contracts && python validate_examples.py` |
| 드론 | `cd drone && pip install -e ".[test,image,base]" && pytest -q` |
| 가시화 화면 (드론 화면 포함) | `cd visualization/viz-debugger && npm ci && npm run typecheck && npm run build && npm run verify:sar` |

## 5. 라이선스

기여한 내용은 [MIT 라이선스](LICENSE)로 배포되는 데 동의하는 것으로 본다. 다른 라이선스의 코드를 가져올 때는 출처와
라이선스를 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) 에 적는다 — 라이선스가 불분명한 코드는 받지 않는다.

## 6. 행동 강령

[CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) 를 따른다.
