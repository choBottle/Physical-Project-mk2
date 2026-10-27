# 변경 기록

형식은 [Keep a Changelog](https://keepachangelog.com/ko/1.1.0/), 버전은 [Semantic Versioning](https://semver.org/lang/ko/)
— 무엇이 "공개 API" 인지는 [docs/RELEASE.md](docs/RELEASE.md#1-버전-규칙--semantic-versioning).
각 판에 **배포 변경**(새 환경변수 · 포트 · DB 마이그레이션 · 이미지 버전) 절을 따로 둔다.

## [Unreleased]

### 바뀜
- **드론 화면 사본 정리(2차 병합)** — 화면의 정본은 `visualization/viz-debugger` 하나다. `drone/viz-debugger` 사본을 지우고
  드론 파트만 가진 화면 변경(레이더 상태 · SAR 간단 모드 · cansar quick-look 카드 · 알림/소리 · 리플렉터 측량 · Pi 상태 칩 ·
  패스 지오펜스 · 지도 미리 받기 · 재처리 조건 저장)을 `visualization/viz-debugger` 로 옮겼다.
- 드론 파이썬(`sar_pass` · `rtk_relay` · `fc_watch` · `sar_data` · `sar_image` · `deploy/` · `radar_team/` · `tests/`)은
  `drone/viz-debugger/drone/` → `drone/` 로 옮겼다. `visualization/viz-debugger/drone/` 의 옛 사본(1차 병합분)도 지웠다 —
  그쪽에만 있던 `fc_watch` NaN → null 고침은 `drone/` 에 합쳤다.

### 바뀜 — 360 → Unity 줄을 통합데이터규약 v2 로 (2026-10-27)
- `camera360/v2/` 의 `anchor360_live.py` · `pano_receiver.py` 를 정본(`camera360/`)으로 올리고 `v2/` 폴더를 없앴다
  (`stream_to_server.py` · 수신 C# 은 두 곳이 같았다). 팀 문서(261014 v2 적용 매뉴얼)의 「넷을 한 날에 바꾼다」를 실행한 것.
- `detect_send_3b2(_timed).py` 도 v2 패킷(`label` · `position` · `ground_dist_m` · `size_m` · `bbox` · `confidence` + 공통 머리)을 보낸다.
- `Anchor360ObstacleReceiver.cs` 는 v2 를 읽고 **옛 v1 패킷도 받는다**(서버를 바꾸는 동안 큐브가 끊기지 않게). Unity 프로젝트의
  같은 스크립트도 같은 판으로 바꿨다(파일 불러오기 · 사례 기록 훅은 각 프로젝트에 그대로).

### 고침 (가시화 · 객체탐지 · Unity 회귀 시험 — 통합 직후 `6dcd1fb` 와 같은 입력으로 비교, 2026-10-27)
- camera360: 설정 yaml 의 상대 가중치 경로를 **yaml 폴더 기준**으로 푼다(`anchor360_live.py` · `v2/` · `detect_send_3b2*.py` ·
  `detect_ground_3b1.py`). 전에는 실행 폴더 기준이라 모델을 못 찾고 ultralytics 가 기본 모델을 새로 받았다. yaml 을 UTF-8 로 연다(한글 Windows).
- hardware: `HW_UPLOAD_URL=` · `HW_DETECT_BASE=` 처럼 **빈 값이면 기본값**으로(전에는 빈 주소로 매번 실패). 값이 없으면 기동 때
  경고를 찍고, `install-units.sh` 도 `/etc/hw-robot.env` 에 두 값이 없으면 알린다 — 없으면 Unity(5009 장애물 · 5001 영상)로 아무것도 가지 않는다.
- 얼굴 흐림 이미지를 **원본과 같은 양자화 표로 다시 저장**했다 — 흐림 영역 밖은 원본과 사실상 같다. (낮은 화질 재저장 때문에
  `ai/demo` 시료의 박스·위치 추정이 흔들리던 것. 흐림 영역 안의 사람 검출이 줄어드는 것은 의도된 결과다.)
- viz-debugger: `test:drone` 이 옮긴 `drone/` 을 가리키게, `verify:fake-device` 의 착륙 직후 disarm 판정 경합을 고쳤다.

### 배포 변경
- Pi 설치 경로: `pip install -e <저장소>/drone` · `sudo <저장소>/drone/deploy/pi/install.sh` (예전 `…/viz-debugger/drone`).
  `install.sh` 는 제 위치 기준으로 코드를 찾으므로 옵션은 그대로다. 이미 설치한 Pi 는 `install.sh` 를 새 자리에서 한 번 다시 돌리면 된다.
- **Go1 Pi 를 이 판으로 올릴 때:** `/etc/hw-robot.env` 에 `HW_UPLOAD_URL` · `HW_DETECT_BASE`(인지 서버 주소)를 넣고
  `hardware/pi/deploy/install-units.sh --user <사용자>` 로 유닛을 다시 깐다. `git pull` 만 하면 옛 유닛은 이 파일을 읽지 않는다.
- 360 서버: `anchor360_live.py` · `pano_receiver.py` 를 새 판으로 바꾸면 패킷이 v2 가 된다 — Unity 쪽 수신 스크립트를 먼저(또는 같이) 바꾼다.
  수신 스크립트는 v1 도 받으므로 Unity 를 먼저 바꾸는 순서가 안전하다.
- camera360 GPU 서버: Redis 비밀번호가 yaml 에서 빠졌다 — `MK2_REDIS_PASSWORD` 를 설정한다.

## [1.0.0-rc.1] — 2026-10-26

첫 공개 후보판. 정식 1.0 전에 남은 것은 [docs/RELEASE.md §3](docs/RELEASE.md#3-v100-출시-기준) (실 하드웨어 E2E · 인물 사진 처리 · viz-debugger 중복 정리).

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

### 변경 — 공개 준비 (#1 ~ #8)
- **환경 고유 값 제거** — 학교 서버 공인 IP · Tailscale 주소 · tailnet 이름 · `/home/<사용자>` 경로를 코드 기본값에서 뺐다.
  기본값은 `localhost` · 실행 계정 홈 · 스크립트 폴더 기준이고 실제 값은 환경변수로 준다(파트별 `.env.example`)
- **hardware** — systemd 유닛 15개를 템플릿으로, `pi/deploy/install-units.sh` 가 사용자·경로를 채워 설치
- **visualization · drone UI** — 연결 프리셋을 Vite 환경변수로. 부수 수정: 환경변수가 `vite build` 결과물에 들어가지 않던 문제
- **ai** — `perception-framework` Docker 이미지 빌드 복구(기본 명령: 기능 상태 패널), CI 에서 이미지 빌드까지 확인
- **camera360** — 역할별 의존성 명세 `requirements.txt` · `requirements-vision.txt`, Redis 비밀번호를 설정 파일에서 환경변수로
- **라이선스** — 전 기여자 · 레이더 팀의 MIT 동의 기록
- **사진** — 152장 전수 검사, EXIF GPS 가 있던 1장에서 메타데이터 제거
- `server/backend/settings.py` — 발행자 기본 브로커 주소를 특정 서버의 공인 IP 에서 `localhost` 로(`MK2_BROKER_HOST` 로 지정)
- 드론 CI 워크플로를 `drone/.github/` → 루트 `.github/workflows/drone.yml` 로 이동(하위 폴더 워크플로는 실행되지 않는다)

### 제거
- 추적되던 산출물: `visualization/web-dashboard/.vite/deps`(빌드 캐시) · `camera360/360camera_work_260921.zip`(폴더 스냅샷) · `hardware/pi/robot/go1_sdk_pc.cpp.bak3`

### 배포 변경
- **AI 기능 상태 패널 기본 포트 8765 → 8775** (8765 는 중앙 WS 게이트웨이). `--port` 로 계속 바꿀 수 있다
- **hardware 유닛은 `install-units.sh` 로만 설치** — `.service` 를 직접 복사하면 자리표시자 때문에 기동 실패.
  Go1 카메라 유닛 2개는 `/etc/hw-robot.env` 의 `HW_UPLOAD_URL` · `HW_DETECT_BASE` 가 필요
- 새 환경변수: camera360 `MK2_SERVER_HOST` · `MK2_UPLOAD_URL` · `MK2_UPLOAD_STREAM_URL` · `MK2_ANCHOR360_URL` · `MK2_REDIS_PASSWORD` ·
  `MK2_CAPSTONE_DB`, ai 데모 `MK2_MQTT_BROKER_URL`, viz-debugger `VITE_PHYSICAL_PRESET_*` · `VITE_DETECT_PRESET_*` · `VITE_AUTODRIVE_AI_*`
- 연구실 서버(수동 운영)와의 차이: 도커 대역을 `172.28.0.0/16` 으로 **고정**(`MK2_NET_SUBNET`), MySQL 앱 계정 host 가
  `'172.18.%'` → `MK2_DB_APP_HOST`(기본 `172.28.%`). 백엔드는 systemd 대신 컨테이너. 호스트 포트 번호는 동일.
- OTel Collector 가 4316 과 4317 을 **둘 다** 받는다(HW · AI 노드의 기본값 4317 과 정합).
- Tempo 의 호스트 OTLP 입구(4317)는 열지 않는다(Collector 우회 금지).
