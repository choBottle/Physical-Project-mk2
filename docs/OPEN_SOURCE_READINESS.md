# 오픈소스 공개 준비 점검표

2026-10-26, 7개 파트 브랜치를 통합하며 점검한 결과. **각 항목은 해당 파트 담당자가 결정·처리한다** — 통합 작업에서는
명백한 산출물(빌드 캐시 · 스냅샷 zip · 백업 파일)만 지웠고 나머지는 손대지 않았다(히스토리에는 전부 남아 있다).

> 원본 저장소는 이미 Public 이었으므로, 아래의 "노출" 항목은 새로 생긴 위험이 아니라 **이미 공개된 상태**다. 실제 비밀값
> (토큰·비밀번호)은 발견되지 않았다. 주소·경로류는 공격면 정보이므로 정리 대상이다.

## 1. 공통

| # | 항목 | 상태 | 조치 |
|---|---|---|---|
| C1 | 라이선스 동의 | ✅ | 기여자 전원(daegyu10 · choBottle · JNY03 · khw18033 · jhjeong)이 MIT 공개에 동의함 (2026-10-26) |
| C2 | 학교 서버 공인 IP 하드코딩 | 🟡 | `server/` 는 이번에 `localhost` 기본값으로 교체. hardware(k3s·업로드 7864) · visualization · camera360 에 남음 |
| C3 | Tailscale 주소(`100.x`) · tailnet 호스트명(`*.<tailnet>.ts.net`) | ❌ | visualization `viz-debugger/src` · ai `demo/test/mqtt_stream_receiver.py` · camera360 → 환경변수 |
| C4 | `/home/<사용자>` 절대 경로 | ❌ | hardware systemd 유닛(`/home/physical`) · drone env 예시 · camera360(75곳) · ai 문서 → `${HOME}`/설치 경로 변수 |
| C5 | 포트 충돌 8765 · 8766 · 8767 | ❌ | [PORTS.md](PORTS.md) |
| C6 | 사람이 읽는 파트 문서의 실명 | 🟢 | 팀원 본인 동의 하에 유지 가능 — 원치 않으면 GitHub 계정명으로 |

## 2. 파트별

### server (백엔드)
- 🟢 배포 자산 정비 완료(이번 통합). `infra/README.md` 의 운영 서버 고유 절차(13개 공용 컨테이너 · `capstone-db`)는 연구실 서버 기록으로 남기고,
  새 배포는 `deploy/` 를 따른다.

### hardware
- ❌ systemd 유닛 15개가 `User=physical` · `/home/physical` 고정 → 설치 스크립트에서 치환하거나 `%h` 사용
- ❌ `k3s/README.md` 에 서버 주소·CA 해시 실값 → 자리표시자로
- 🟡 `docs/*.docx` · `피지컬팀 프로젝트 mk2.xlsx` — 내부 문서인지 공개 문서인지 결정
- 🟢 의존성 명세 없음(`pi_base_setup.sh` 의 pip 목록) → `requirements.txt` 추가 권장

### ai
- ❌ `perception-framework/Dockerfile` 이 없는 `examples/` 를 복사해 **빌드가 안 된다**
- 🟡 `docs/obsidian/papers/` 논문 요약 약 70편 — 저작권(요약·인용 범위) 검토
- 🟡 `CLAUDE.md`(115KB) · `AGENTS.md` · `.claude/skills/` — 공개 유지 여부

### visualization
- ❌ 소스에 Tailscale IP 5개 · tailnet 호스트 하드코딩
- 🟡 `documents/` 의 docx/pdf/회의 사진(인물 가능) — 공개 여부 결정
- 🟡 `web-dashboard/.env.local` 이 커밋돼 있음(값은 localhost 뿐 — 비밀 아님). Vite 관례상 `.env` 로 옮기는 것을 권장
- 🟡 Vite dev/preview 미들웨어에만 있는 CORS 중계 — 정적 빌드(`dist/`)로 배포하면 사라진다

### drone
- ✅ `radar_team/cansar_pi.py` 등 레이더 팀 코드 — 원 저작자가 MIT 공개에 동의(2026-10-26) · [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md)
- 🟡 `screenshots/` 38장 — 위성 지도·현장 위치 노출 가능
- ❌ `viz-debugger/` 전체 사본이 `visualization/` 과 중복(약 183개 파일이 다름). `drone/` 은 드론 모듈(`viz-debugger/drone/`)만 정본으로 두고
  UI 는 `visualization/` 하나로 합치는 것을 제안 — `DRONE_MERGE_REVIEW.md` 의 2차 병합과 같은 일
- 🟢 CI 워크플로를 저장소 루트로 옮겼다(`.github/workflows/drone.yml` — 하위 폴더의 워크플로는 GitHub 가 실행하지 않는다)

### camera360
- ❌ 배포 자산 없음(Docker · systemd · env 없음), 의존성은 231줄 `pip freeze`
- 🟡 `image backup/` · `360도 카메라 반영범위/` — 실험실/현장 사진(인물 가능)
- 🟡 `구버전(참고금지)/` — 공개 판에서 제외하거나 `archive/` 로
- 🟢 이번에 스냅샷 zip(6.9MB, 폴더와 같은 내용)을 지웠다

### osmocam
- 🟢 원 저작물(MIT) 라이선스·NOTICE 유지 — [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md)
- 🟡 README 의 다운로드 링크가 원 저장소를 가리킴 · 개조 내용을 README 상단에 명시 권장
