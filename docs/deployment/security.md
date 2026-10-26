# 보안 · 노출 정책

> 현재 프로파일은 **"터널 안의 신뢰된 구성원"** 이다. 인증·인가(RBAC, BE-Q-04)와 전송 암호화(TLS/SASL)는 v1.x 로드맵이다.
> 이 문서는 그 전까지 **무엇이 지켜지고 무엇이 아직 아닌지**를 정직하게 적는다. 취약점 신고는 [SECURITY.md](../../SECURITY.md).

## 1. 노출 원칙 — 바인딩 주소가 곧 통제

| 묶음 | 포트 | 기본 바인딩 | 인증 |
|---|---|---|---|
| 엣지 입구 (`MK2_EDGE_BIND`) | MQTT 1883 · MQTT/WS 9001 · OTLP 4316/4317/4318 · Kafka EDGE 9095 | `127.0.0.1` | **없음** (익명 MQTT · 평문 OTLP · PLAINTEXT Kafka) |
| 백엔드 입구 (`MK2_EDGE_BIND`) | WS 8765 · 미디어 8766 · 촬영본 8767 | `127.0.0.1` | URL 쿼리 토큰 (`MK2_WS_TOKEN`·`MK2_EDGE_TOKEN`·`MK2_CAPTURE_TOKEN`) |
| 운영자 (`MK2_ADMIN_BIND`) | Grafana · Prometheus · Loki · Tempo · MySQL · TimescaleDB | `127.0.0.1` | Grafana 계정 · DB 계정 (Prometheus·Loki·Tempo 는 없음) |
| 내부 전용 | Kafka 9092 | `127.0.0.1` 고정 | 없음 |

- 도커가 발행한 포트는 호스트 방화벽(ufw)보다 **먼저** 처리된다. 그래서 ufw 규칙이 아니라 **compose 의 바인딩 주소**가 실질
  통제다. 엣지 입구는 반드시 **터널 주소**에 바인딩하고 `0.0.0.0` 을 쓰지 않는다.
- 운영자 화면은 서버 밖에 열지 않는다. 원격에서는 `ssh -L 7862:127.0.0.1:7862 <서버>`.
- 백엔드는 loopback 이 아닌 주소에 바인딩하면서 토큰이 비어 있으면 **기동을 거부**한다(exit 2).

## 2. 비밀값

- 전부 `deploy/.env` 한 곳(권한 600, gitignore). `scripts/init-env.sh` 가 영숫자 32자로 생성한다.
- 영숫자만 쓴다 — `.env` 를 읽는 파서(셸 · compose · systemd)마다 특수문자 해석이 다르다.
- 저장소·이슈·채팅에 실제 주소·토큰을 적지 않는다. 문서에는 `<중앙 터널 주소>` 같은 자리표시자를 쓴다.
- DB 앱 계정은 DDL 이 없고 감사·실행 기록에 UPDATE/DELETE 가 없다 — 앱이 탈취돼도 기록을 고칠 수 없다([database.md §3](database.md#3-권한--코드가-약속이-아니라-db-가-강제)).

## 3. 운영 전환 체크리스트 (터널 밖 · 다기관 · 공공 배치)

| # | 항목 | 현재 | 조치 |
|---|---|---|---|
| 1 | MQTT 인증 | 익명 | `mosquitto.conf` 의 「운영 프로파일」(password_file + ACL) |
| 2 | MQTT TLS | 없음 | 8883 리스너 + 인증서 |
| 3 | Kafka EDGE | PLAINTEXT | SASL_SSL (BE-Q-04 와 함께) |
| 4 | OTLP 수신 인증 | 없음 | Collector `bearertokenauth` 확장, 엣지 Collector 에 토큰 |
| 5 | WS 토큰 → 사용자 인증 | 공유 토큰 | RBAC(BE-Q-04) · WSS |
| 6 | Grafana | 로컬 관리자 | SSO/OIDC, 관리자 비밀번호 교체 |
| 7 | Prometheus/Loki/Tempo API | 인증 없음(로컬 바인딩) | 리버스 프록시 + 인증, 또는 로컬 유지 |
| 8 | 이미지 공급망 | 버전 태그 고정 | digest 고정(`image@sha256:…`) + 취약점 스캔(CI) |
| 9 | 백업 암호화 | 평문 덤프 | 백업 대상 저장소 암호화 · 접근 통제 |
| 10 | 개인정보 · 위치정보 | 영상·촬영본·SAR 데이터에 포함 가능 | 보존 기간·접근 권한 정책, 공개 저장소에 원본 데이터 금지 |

## 4. 공개 저장소 규칙

이 저장소는 Public 이다. 커밋 전에:
- `git diff --staged` 에 IP·토큰·`/home/<사용자>`·내부 호스트명이 없는지 본다(CI 의 비밀값 스캔이 2차 방어선).
- 사진·영상·스크린샷에 사람 얼굴 · 비공개 시설 · 정밀 위치가 없는지 본다.
- 실수로 올렸으면 지우는 커밋만으로는 부족하다 — **그 값을 즉시 교체(rotate)** 하고 메인테이너에게 알린다.
