# 폐쇄망 설치 — 인터넷 없는 서버에 MK2 세우기

> 재난 현장·공공기관 서버는 인터넷에 붙지 않는 경우가 많다. 이 문서는 **인터넷이 되는 기계에서 필요한 것을 전부 한
> 묶음으로 만들고, 그 묶음만으로 폐쇄망 서버·엣지·장치 노드를 세우는 절차**다. 일반 설치는 [README.md §3](README.md#3-설치--다섯-단계).

## 1. 일반 설치에서 인터넷을 쓰는 자리

| 자리 | 무엇을 받나 | 폐쇄망에서는 |
|---|---|---|
| `git clone` | 저장소 | `repo.bundle`(git bundle) 에서 clone |
| `docker compose up` | 중앙 13개 서비스의 이미지 10종(고정 버전) · Alertmanager(override 예시) | `images-central.tar.gz` 를 `docker load` |
| `docker compose up --build` | 백엔드 빌드 — 베이스 이미지 + PyPI | **빌드하지 않는다.** 게시 이미지 `ghcr.io/chobottle/mk2-backend:<태그>` 를 묶음에 넣는다 |
| `deploy/edge` 의 `up` | 엣지 이미지 3개(Mosquitto · Collector · Prometheus) | `images-edge.tar.gz` (기본 linux/arm64) |
| `e2e-sim.sh` | 노드 컨테이너 `python:3.12-slim` + `pip install` | 이미지는 중앙 묶음에, 휠은 `wheels/e2e/` → `MK2_WHEELHOUSE` |
| `hardware/pi/pi_base_setup.sh` | venv 의 `pip install`(paho-mqtt · opentelemetry · psutil) · apt(chrony · python3-venv) | 휠은 `wheels/pi/` → `--wheelhouse`. apt 는 §6 |

---

## 2. 묶음 만들기 — 인터넷이 되는 기계

필요: 리눅스(또는 WSL) bash · Docker Engine 24+ · Compose v2.24+ · git · python3 + pip · `sha256sum`.
디스크는 이미지 압축본과 저장소를 합쳐 수 GB 를 잡는다.

```bash
git clone https://github.com/choBottle/Physical-Project-mk2.git
cd Physical-Project-mk2
git fetch --tags
./deploy/scripts/bundle-offline.sh v1.1.0 /media/usb/mk2-v1.1.0     # <태그> <빈 디렉터리>
```

스크립트가 하는 일(손으로 할 때도 이 순서다):

| 단계 | 내용 |
|---|---|
| ① 저장소 | `git bundle create repo.bundle refs/tags/<태그>` — 대상에서 `git checkout <태그>` 로 업그레이드할 수 있게 git 이력째 담는다 |
| ② 이미지 목록 | **그 태그의** `deploy/docker-compose.yml`(+`docker-compose.override.yml.example`) · `deploy/edge/docker-compose.yml` 을 `docker compose config --images` 로 읽는다. 손으로 적은 목록이 아니라 compose 가 정본이다. 데몬 없이 돈다 |
| ③ 백엔드 | `MK2_BACKEND_IMAGE=ghcr.io/chobottle/mk2-backend:<태그>` 로 목록을 뽑아 게시 이미지를 pull 한다 |
| ④ pull · save | 중앙 묶음은 `CENTRAL_PLATFORM`(기본 `linux/amd64`), 엣지 묶음은 `EDGE_PLATFORM`(기본 `linux/arm64`)으로 pull 해 `docker save \| gzip` |
| ⑤ 휠 | `pip download --only-binary=:all:` — e2e 용(`python:3.12-slim` 과 같은 cp312 · 중앙 CPU), 장치 노드 용(`PI_PYTHON` 기본 3.13 · aarch64) |
| ⑥ 검증값 | `MANIFEST.txt`(태그 · 커밋 · 플랫폼) · `SHA256SUMS`(모든 파일) · 대상에서 쓸 `load-offline.sh` 사본 |

손으로 이미지 목록만 볼 때(필수 비밀값은 자리값이면 된다 — 목록을 뽑는 데만 쓴다):

```bash
cd deploy
env MK2_MYSQL_PASSWORD=x MK2_TSDB_PASSWORD=x MK2_TSDB_ROOT_PASSWORD=x MYSQL_ROOT_PASSWORD=x \
    MK2_WS_TOKEN=x MK2_EDGE_TOKEN=x MK2_CAPTURE_TOKEN=x GRAFANA_ADMIN_PASSWORD=x \
    MK2_BACKEND_IMAGE=ghcr.io/chobottle/mk2-backend:v1.1.0 \
  docker compose --env-file /dev/null config --images | sort -u
(cd edge && env MK2_ZONE_ID=x MK2_CENTRAL_MQTT_HOST=x MK2_CENTRAL_OTLP=x:4317 \
  docker compose --env-file /dev/null config --images | sort -u)
```

### 바꿀 수 있는 것 (환경변수)

| 변수 | 기본 | 언제 바꾸나 |
|---|---|---|
| `CENTRAL_PLATFORM` | `linux/amd64` | 중앙 서버가 arm64 일 때 — 게시 백엔드 이미지에 그 플랫폼이 있어야 한다(`docker buildx imagetools inspect ghcr.io/chobottle/mk2-backend:<태그>`) |
| `EDGE_PLATFORM` | `linux/arm64` | 엣지가 소형 x86 이면 `linux/amd64` |
| `PI_PYTHON` · `PI_ARCH` | `3.13` · `aarch64` | 장치 노드의 `python3 --version` 이 다를 때(Raspberry Pi OS bookworm 은 3.11) |
| `MK2_IMAGE_OWNER` | `chobottle` | 포크가 자기 GHCR 에 게시할 때(소문자) |
| `BACKEND_SOURCE` | `pull` | `build` — 게시 이미지가 없는 태그. 그 태그의 `server/` 를 이 기계에서 빌드해 같은 이름을 붙인다 |

### 묶음 구성

```text
mk2-v1.1.0/
├── repo.bundle             저장소(태그 하나 + 이력)
├── images-central.tar.gz   중앙 이미지 + 백엔드 + python:3.12-slim (+ Alertmanager)
├── images-central.txt      ↑ 목록
├── images-edge.tar.gz      엣지 이미지
├── images-edge.txt
├── wheels/e2e/             e2e-sim.sh 노드 컨테이너용 휠
├── wheels/pi/              장치 노드 venv 용 휠
├── load-offline.sh         대상에서 검증·적재
├── MANIFEST.txt
└── SHA256SUMS
```

---

## 3. 반입

USB·외장 디스크 등 기관이 허용한 매체로 디렉터리째 옮긴다. **`SHA256SUMS` 는 묶음과 다른 경로로도 전달해 두면**(메일·문서
대장) 매체 안에서 묶음과 체크섬이 함께 바뀌는 경우까지 가린다. 대상에서 확인:

```bash
cd /media/usb/mk2-v1.1.0 && sha256sum -c SHA256SUMS
```

---

## 4. 중앙 서버 — 폐쇄망

요구 사양은 [README.md §2](README.md#2-요구-사양) 그대로다(Docker Engine 24+ · Compose v2.24+ · git · bash 는 미리 설치돼 있어야 한다).

```bash
# ① 검증 + 적재 — 체크섬이 하나라도 어긋나면 아무것도 적재하지 않는다
/media/usb/mk2-v1.1.0/load-offline.sh /media/usb/mk2-v1.1.0

# ② 저장소
git clone -b v1.1.0 /media/usb/mk2-v1.1.0/repo.bundle /opt/Physical-Project-mk2
cd /opt/Physical-Project-mk2/deploy

# ③ 환경변수 + 백엔드 이미지를 적재한 게시 이미지로
./scripts/init-env.sh
sed -i 's|^MK2_BACKEND_IMAGE=.*|MK2_BACKEND_IMAGE=ghcr.io/chobottle/mk2-backend:v1.1.0|' .env

# ④ 기동 — --build 를 붙이지 않는다. --pull never 로 네트워크를 찾지 않게 한다
docker compose up -d --wait --pull never

# ⑤ 검증
./scripts/healthcheck.sh
MK2_WHEELHOUSE=/media/usb/mk2-v1.1.0/wheels/e2e ./scripts/e2e-sim.sh    # 말단 노드 코드까지(선택)
```

- `--build` 를 붙이면 compose 가 PyPI 에서 백엔드를 빌드하려다 실패한다. 빌드가 되더라도 같은 이름의 로컬 이미지가 게시
  이미지를 가린다([operations.md 업그레이드](operations.md#업그레이드-새-릴리스로)).
- `MK2_BACKEND_IMAGE` 를 바꾸지 않으면 기본값 `mk2-backend:local` 을 찾다가 빌드로 넘어간다 — ③ 을 빠뜨리지 않는다.
- Alertmanager 는 묶음에 들어 있으니 [operations.md 「현장 설정」](operations.md#현장-설정--추적-파일을-고치지-않는다) 대로
  override 를 켜면 그대로 뜬다.

---

## 5. 구역 엣지 노드 — 폐쇄망

```bash
/media/usb/mk2-v1.1.0/load-offline.sh /media/usb/mk2-v1.1.0 edge
git clone -b v1.1.0 /media/usb/mk2-v1.1.0/repo.bundle ~/Physical-Project-mk2
cd ~/Physical-Project-mk2/deploy/edge
cp .env.example .env        # MK2_ZONE_ID · MK2_CENTRAL_OTLP · MK2_CENTRAL_MQTT_HOST — edge.md §2 ③
docker compose up -d --wait --pull never
```

터널(Tailscale)도 인터넷의 조정 서버가 필요하다. 폐쇄망에서는 자체 조정 서버(Headscale)나 WireGuard 직접 구성, 또는 같은
사설망 안 배치로 대신한다 — 바인딩 원칙은 [security.md §1](security.md#1-노출-원칙--바인딩-주소가-곧-통제) 그대로다.
나머지 순서·검증은 [edge.md](edge.md).

---

## 6. 장치 노드(라즈베리파이) — 폐쇄망

저장소와 `wheels/pi/` 를 파이로 옮긴 뒤:

```bash
git clone -b v1.1.0 /media/usb/mk2-v1.1.0/repo.bundle ~/Physical-Project-mk2
cd ~/Physical-Project-mk2/hardware/pi
python3 --version            # 묶음의 pi_python(MANIFEST.txt)과 같아야 한다
./pi_base_setup.sh --entity wl-001 --zone zoneA --role sensor \
    --ntp <엣지 주소> --broker <엣지 주소> \
    --wheelhouse /media/usb/mk2-v1.1.0/wheels/pi
```

`--wheelhouse` 는 PyPI 대신 그 디렉터리에서만 설치하고(`pip --no-index --find-links`), pip 자체 업그레이드를 건너뛴다.

**apt 패키지는 묶음에 없다.** `pi_base_setup.sh` 는 `chrony`(없을 때) · `python3-venv`(venv 가 없을 때)를 apt 로 설치한다.
두 패키지가 이미 깔린 OS 이미지를 쓰거나, 같은 OS 판의 인터넷 되는 파이에서 받아 옮긴다:

```bash
# 인터넷 되는 파이 — 대상과 **같은 OS 이미지를 새로 구운 것**(이미 깔린 의존성은 받지 않으므로)
sudo apt-get clean && sudo apt-get install --download-only -y chrony python3-venv
mkdir -p debs && cp /var/cache/apt/archives/*.deb debs/
# 대상 파이
sudo apt-get install -y ./debs/*.deb
```

로봇 노드 컨테이너(`hw-robot`, [`hardware/pi/robot/Dockerfile`](../../hardware/pi/robot/Dockerfile))는 빌드 때 GitHub·PyPI 를
쓰므로 이 스크립트가 담지 않는다. 인터넷 되는 arm64 파이에서 빌드해 `docker save hw-robot:latest | gzip > hw-robot.tar.gz`
로 옮기고 대상에서 `docker load -i hw-robot.tar.gz`.

---

## 7. 폐쇄망 업그레이드

새 태그로 묶음을 다시 만든 뒤([§2](#2-묶음-만들기--인터넷이-되는-기계)), 대상에서:

```bash
/media/usb/mk2-v1.2.0/load-offline.sh /media/usb/mk2-v1.2.0
cd /opt/Physical-Project-mk2
git fetch /media/usb/mk2-v1.2.0/repo.bundle 'refs/tags/*:refs/tags/*'
```

이후는 [operations.md 업그레이드](operations.md#업그레이드-새-릴리스로) 절차 그대로 하되, `docker compose pull` 대신 위의
`load-offline.sh` 가 이미지를 들여왔으므로 `docker compose up -d --wait --pull never` 로 기동한다.

---

## 8. 문제 해결

| 증상 | 원인 · 조치 |
|---|---|
| `up` 이 `pull access denied` · DNS 오류로 멈춘다 | 적재되지 않은 이미지를 찾는다. `MK2_BACKEND_IMAGE` 가 묶음의 `backend_image`(MANIFEST.txt)와 같은지, `docker image ls` 에 `images-central.txt` 의 이미지가 다 있는지 본다 |
| 컨테이너가 `exec format error` 로 죽는다 | 플랫폼이 다르다(예: arm64 엣지에 amd64 이미지). 묶음을 `EDGE_PLATFORM`/`CENTRAL_PLATFORM` 을 맞춰 다시 만든다 |
| 묶음을 만들 때 백엔드 pull 이 `manifest unknown` | 그 태그의 게시 이미지가 없거나 그 플랫폼이 없다. `BACKEND_SOURCE=build` 로 다시 |
| `pip ... No matching distribution` (장치 노드 · e2e) | 휠의 파이썬 판 · CPU 가 대상과 다르다. `PI_PYTHON`·`PI_ARCH` 를 맞춰 다시 만든다 |
| `load-offline.sh` 가 체크섬 불일치로 끝난다 | 복사 중 손상 또는 변조. 다시 복사한다 — 적재된 것은 없다 |
| `e2e-sim.sh` 가 노드 기동에서 멈춘다 | `MK2_WHEELHOUSE` 를 주지 않아 PyPI 를 찾는다. `docker logs mk2-e2e-sensor` 확인 |

## 9. 검증 기록

| 날짜 | 환경 | 결과 |
|---|---|---|
| 2026-11-02 | Windows 11 · Git Bash · Docker CLI(데몬 없음) | `config --images` 가 데몬 없이 중앙 10개(+ e2e 노드 `python:3.12-slim`) · 엣지 3개 목록을 냄(`v1.0.0-rc.2` 태그 기준). pull·save·load 를 대역 스크립트로 바꿔 `bundle-offline.sh` → `load-offline.sh` 왕복, 파일 하나를 고치면 체크섬에서 멈추는 것 확인. 휠 두 벌이 `pip install --no-index` 로 대상 플랫폼(cp312 x86_64 · cp313 aarch64)에서 풀리는 것 확인(`--dry-run`) |
| — | 실제 폐쇄망 서버 | **아직 하지 않았다.** 실제 pull·save·load 와 `up --pull never` → `healthcheck.sh` 는 다음 실기 회차에서 이 표에 적는다 |
