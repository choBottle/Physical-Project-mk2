# 오픈소스 공개 준비 점검표

2026-10-26, 7개 파트 브랜치를 통합하며 점검한 결과. **각 항목은 해당 파트 담당자가 결정·처리한다** — 통합 작업에서는
명백한 산출물(빌드 캐시 · 스냅샷 zip · 백업 파일)만 지웠고 나머지는 손대지 않았다(히스토리에는 전부 남아 있다).

> 원본 저장소는 이미 Public 이었으므로, 아래의 "노출" 항목은 새로 생긴 위험이 아니라 **이미 공개된 상태**다. 실제 비밀값
> (토큰·비밀번호)은 발견되지 않았다. 주소·경로류는 공격면 정보이므로 정리 대상이다.

## 1. 공통

| # | 항목 | 상태 | 조치 |
|---|---|---|---|
| C1 | 라이선스 동의 | ✅ | 기여자 전원(daegyu10 · choBottle · JNY03 · khw18033 · jhjeong)이 MIT 공개에 동의함 (2026-10-26) |
| C2 | 학교 서버 공인 IP 하드코딩 | ✅ | 코드 기본값은 전부 `localhost`, 실제 주소는 환경변수(#3 · #4 · #7). 연구실 운영 기록(`server/infra/systemd` · `server/reports/`)에는 남아 있다 — 새 배포는 `deploy/` |
| C3 | Tailscale 주소(`100.x`) · tailnet 호스트명(`*.<tailnet>.ts.net`) | ✅ | UI 프리셋은 Vite 환경변수(`.env.local`), 스크립트는 `MK2_*` 환경변수. 남은 것은 레이더 팀 원본 · 시험 원본 사본뿐 |
| C4 | `/home/<사용자>` 절대 경로 | ✅ | hardware 유닛은 `install-units.sh` 가 치환, drone 은 `install.sh` 의 `@SAR_HOME@`, 코드는 실행 계정 홈 · 스크립트 폴더 기준 |
| C5 | 포트 충돌 8765 · 8766 · 8767 | ✅ | 8765 는 AI status UI 를 8775 로 옮겨 해결, 8766 · 8767 은 기기가 달라 실제 충돌 없음 — [PORTS.md](PORTS.md) |
| C6 | 사람이 읽는 파트 문서의 실명 | 🟢 | 팀원 본인 동의 하에 유지 가능 — 원치 않으면 GitHub 계정명으로 |
| C7 | 사진 메타데이터(EXIF GPS) | ✅ | 이미지 152장 전수 검사 — GPS 가 있던 1장(회의 사진)에서 EXIF 를 재인코딩 없이 제거(2026-10-26) |

## 2. 파트별

### server (백엔드)
- 🟢 배포 자산 정비 완료(이번 통합). `infra/README.md` 의 운영 서버 고유 절차(13개 공용 컨테이너 · `capstone-db`)는 연구실 서버 기록으로 남기고,
  새 배포는 `deploy/` 를 따른다.

### hardware
- ✅ systemd 유닛 15개 템플릿화 — `pi/deploy/install-units.sh --user <사용자>` 로 설치
- ✅ `k3s/README.md` 의 서버 주소 · CA 해시 → 자리표시자 + 각자 값 얻는 법
- 🟡 `docs/*.docx` · `피지컬팀 프로젝트 mk2.xlsx` — 내부 문서인지 공개 문서인지 결정
- 🟢 의존성 명세 없음(`pi_base_setup.sh` 의 pip 목록) → `requirements.txt` 추가 권장

### ai
- ✅ `perception-framework/Dockerfile` 빌드 복구(없는 `examples/` 대신 status UI 를 기본 명령으로) · CI 에서 이미지 빌드까지 확인
- 🟡 `docs/obsidian/papers/` 논문 요약 약 70편 — 저작권(요약·인용 범위) 검토
- 🟡 `CLAUDE.md`(115KB) · `AGENTS.md` · `.claude/skills/` — 공개 유지 여부

### visualization
- ✅ 연결 프리셋 · 기본 주소를 Vite 환경변수로(`viz-debugger/.env.example`)
- 🟡 `documents/` 의 docx/pdf — 공개 여부 결정. 이미지 44장은 확인 결과 다이어그램·UI 캡처와 칠판 사진 1장(인물 없음)
- ❗ `door_example/test/{door,pedestal}/` 프레임 이미지 — **얼굴이 식별되는 인물**(실내 시험 참가자)이 찍혀 있다. 본인 동의를 받거나,
  인물이 없는 프레임으로 바꾸거나, 흐림 처리 후 공개
- 🟡 `web-dashboard/.env.local` 이 커밋돼 있음(값은 localhost 뿐 — 비밀 아님). Vite 관례상 `.env` 로 옮기는 것을 권장
- 🟡 Vite dev/preview 미들웨어에만 있는 CORS 중계 — 정적 빌드(`dist/`)로 배포하면 사라진다

### drone
- ✅ `radar_team/cansar_pi.py` 등 레이더 팀 코드 — 원 저작자가 MIT 공개에 동의(2026-10-26) · [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md)
- 🟡 `screenshots/` 38장 — 확인 결과 UI·SAR 결과 캡처. 일부에 시험 장소의 위성 지도가 보인다(인물 없음) — 시험 장소 공개 여부 결정
- ❌ `viz-debugger/` 전체 사본이 `visualization/` 과 중복(약 183개 파일이 다름). `drone/` 은 드론 모듈(`viz-debugger/drone/`)만 정본으로 두고
  UI 는 `visualization/` 하나로 합치는 것을 제안 — `DRONE_MERGE_REVIEW.md` 의 2차 병합과 같은 일
- 🟢 CI 워크플로를 저장소 루트로 옮겼다(`.github/workflows/drone.yml` — 하위 폴더의 워크플로는 GitHub 가 실행하지 않는다)

### camera360
- 🟡 의존성 명세 추가(`requirements.txt` 촬영·전송·수신 / `requirements-vision.txt` GPU 추론). Docker · systemd 는 아직 없음
- 🟡 `image backup/` · `360도 카메라 반영범위/` — 연구실 내부 사진. 책상에 앉은 사람이 작게(주로 뒷모습) 보인다 — 동의 또는 흐림 처리 검토
- 🟡 `구버전(참고금지)/` — 공개 판에서 제외하거나 `archive/` 로
- 🟢 이번에 스냅샷 zip(6.9MB, 폴더와 같은 내용)을 지웠다

### osmocam
- 🟢 원 저작물(MIT) 라이선스·NOTICE 유지 — [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md)
- 🟡 README 의 다운로드 링크가 원 저장소를 가리킴 · 개조 내용을 README 상단에 명시 권장
