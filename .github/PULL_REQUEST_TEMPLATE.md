## 무엇을 · 왜

<!-- 관련 이슈: #123 -->

## 파트

- [ ] server  - [ ] hardware  - [ ] ai  - [ ] visualization  - [ ] drone  - [ ] camera360  - [ ] osmocam  - [ ] deploy/docs

## 배포 영향 — 하나라도 해당하면 같은 PR 에서 문서까지 고친다

- [ ] 새/바뀐 **환경변수** → `deploy/.env.example` (+ 파트별 `.env.example`)
- [ ] 새/바뀐 **포트** → `docs/PORTS.md` · compose
- [ ] **DB 스키마** 변경 → `server/infra/sql/` 정본 + `migrations/` 파일 + GRANT · `docs/deployment/database.md`
- [ ] **공통 규격**(contracts) · MQTT/Kafka 토픽 변경 → `rfc` 이슈 합의 링크: 
- [ ] **이미지 버전** 변경 → compose 고정 버전 · CI `validate` 통과
- [ ] 새 데이터 경로 → `deploy/scripts/healthcheck.sh` 에 "흐른다" 검사 추가
- [ ] 해당 없음

## 확인

- [ ] `CHANGELOG.md` `[Unreleased]` 갱신 (배포 변경은 「배포 변경」 절)
- [ ] 비밀값 · 실제 IP · tailnet 호스트명 · `/home/<사용자>` 경로가 diff 에 없다
- [ ] 사진·영상에 개인정보·정밀 위치가 없다
- [ ] 로컬에서 시험: <!-- 예: ./deploy/scripts/healthcheck.sh 32/32, pytest … -->
