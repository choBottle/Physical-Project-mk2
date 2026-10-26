# MK2 백엔드 이미지 — ingest · storage · gateway · capture 넷이 같은 이미지를 쓰고 command 만 다르다.
#
# 빌드:  docker build -t mk2-backend server/
# 실행:  deploy/docker-compose.yml 이 서비스 넷으로 띄운다(직접 띄울 일은 거의 없다).
#
# systemd(infra/systemd/) 운영과의 관계: 같은 코드·같은 환경변수(backend/settings.py)를 쓴다.
# 달라지는 것은 접속 주소뿐이다 — 컨테이너 안에서는 localhost 대신 compose 서비스 이름
# (mosquitto · kafka:9094 · mysql:3306 · timescaledb:5432 · otel-collector:4317)으로 붙는다.

FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# 의존성 층을 먼저 — 코드만 바뀌면 이 층은 캐시에서 온다.
COPY pyproject.toml ./
RUN mkdir -p backend && touch backend/__init__.py \
 && pip install ".[dev]" \
 && pip uninstall -y mk2-backend \
 && rm -rf backend build *.egg-info

COPY backend ./backend
COPY contracts ./contracts
COPY tests ./tests
# 저장 축 조회 SQL(갭 검출·레지스트리 대조) — 테스트와 운영 조회가 읽는 실행 자산
COPY docs/be/queries ./docs/be/queries

# 루트로 돌지 않는다. 런타임 산출물(격리·sink·촬영본)은 /data 볼륨에 쓴다.
RUN useradd --create-home --uid 10001 mk2 \
 && mkdir -p /data/media_capture \
 && chown -R mk2:mk2 /data
USER mk2

ENV MK2_QUARANTINE_PATH=/data/quarantine.jsonl \
    MK2_SINK_PATH=/data/telemetry_sink.jsonl \
    MK2_CAPTURE_DIR=/data/media_capture

VOLUME ["/data"]

# 기본은 ingest. compose 가 서비스마다 덮어쓴다.
CMD ["python", "-m", "backend.ingest.bridge"]
