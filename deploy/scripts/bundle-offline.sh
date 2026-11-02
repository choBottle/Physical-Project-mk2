#!/usr/bin/env bash
# 폐쇄망(air-gapped) 설치 묶음 만들기 — **인터넷이 되는 기계**에서 돌린다.
#
#   ./deploy/scripts/bundle-offline.sh v1.0.0 /media/usb/mk2-v1.0.0
#
# 만드는 것(<outdir>):
#   repo.bundle            저장소(git bundle — 태그 하나). 대상에서 `git clone -b <tag> repo.bundle` 로 푼다
#   images-central.tar.gz  중앙 스택 이미지 전부 + 게시된 백엔드 이미지 + e2e 노드 이미지(python:*-slim)
#   images-edge.tar.gz     구역 엣지 스택 이미지(기본 linux/arm64 — 라즈베리파이 5)
#   images-*.txt           각 묶음에 든 이미지 목록
#   wheels/e2e/            e2e-sim.sh 노드 컨테이너용 파이썬 휠(MK2_WHEELHOUSE 로 넘긴다)
#   wheels/pi/             말단 장치(hardware/pi) venv 용 파이썬 휠(pi_base_setup.sh --wheelhouse)
#   load-offline.sh        대상에서 검증·적재하는 스크립트(저장소를 풀기 전에 쓸 수 있게 사본을 둔다)
#   MANIFEST.txt           태그 · 커밋 · 플랫폼 · 만든 시각
#   SHA256SUMS             위 파일 전부의 sha256 — 대상에서 load-offline.sh 가 먼저 검사한다
#
# 이미지 목록은 손으로 적지 않는다 — 그 태그의 compose 파일을 `docker compose config --images` 로 읽는다
# (데몬 없이도 된다). 중앙은 docker-compose.override.yml.example 까지 합쳐 Alertmanager 도 넣는다.
#
# 환경변수(선택)
#   MK2_IMAGE_OWNER     GHCR 소유자(소문자)            기본 chobottle
#   CENTRAL_PLATFORM    중앙 서버 플랫폼               기본 linux/amd64
#   EDGE_PLATFORM       엣지 노드 플랫폼               기본 linux/arm64 (소형 x86 엣지면 linux/amd64)
#   PI_PYTHON           말단 장치의 파이썬 버전        기본 3.13 (Raspberry Pi OS / Debian 13)
#   PI_ARCH             말단 장치의 CPU                기본 aarch64
#   PYTHON              pip 를 돌릴 파이썬             기본 python3
#   BACKEND_SOURCE      pull = GHCR 게시 이미지(기본) | build = 그 태그의 server/ 를 여기서 빌드해 같은 이름을 붙인다
#                       (게시 이미지가 없는 태그·포크용. 빌드에는 인터넷이 필요하다 — 이 기계에서 하므로 괜찮다)
#
# 상세: docs/deployment/offline.md
set -euo pipefail

usage() { sed -n '2,30p' "$0"; exit "${1:-0}"; }
[[ "${1:-}" == "-h" || "${1:-}" == "--help" ]] && usage 0
[[ $# -eq 2 ]] || usage 1

TAG="$1"
OUT="$2"
OWNER="${MK2_IMAGE_OWNER:-chobottle}"
CENTRAL_PLATFORM="${CENTRAL_PLATFORM:-linux/amd64}"
EDGE_PLATFORM="${EDGE_PLATFORM:-linux/arm64}"
PI_PYTHON="${PI_PYTHON:-3.13}"
PI_ARCH="${PI_ARCH:-aarch64}"
PYTHON="${PYTHON:-python3}"
BACKEND_SOURCE="${BACKEND_SOURCE:-pull}"
[[ "${BACKEND_SOURCE}" == "pull" || "${BACKEND_SOURCE}" == "build" ]] || { echo "BACKEND_SOURCE 는 pull | build" >&2; exit 1; }
BACKEND_IMAGE="ghcr.io/${OWNER}/mk2-backend:${TAG}"
REPO="$(cd "$(dirname "$0")/../.." && pwd)"

# 말단 노드가 쓰는 라이브러리 — pi_base_setup.sh(4. 파이썬 환경) · e2e-sim.sh(노드 컨테이너)와 같은 목록이어야 한다
NODE_PKGS=(paho-mqtt opentelemetry-sdk opentelemetry-exporter-otlp psutil protobuf)

say() { printf '\n▶ %s\n' "$*"; }
die() { echo "✗ $*" >&2; exit 1; }

for c in git docker gzip sha256sum "${PYTHON}"; do
  command -v "${c}" >/dev/null 2>&1 || die "필요한 명령이 없다: ${c}"
done
docker compose version >/dev/null 2>&1 || die "docker compose v2 가 필요하다"
git -C "${REPO}" rev-parse -q --verify "refs/tags/${TAG}" >/dev/null \
  || die "태그 ${TAG} 가 없다 — git fetch --tags 후 다시"
COMMIT="$(git -C "${REPO}" rev-parse "${TAG}^{commit}")"

mkdir -p "${OUT}"
OUT="$(cd "${OUT}" && pwd)"
[[ -z "$(ls -A "${OUT}")" ]] || die "${OUT} 가 비어 있지 않다 — 빈 디렉터리를 준다"
WORK="$(mktemp -d)"
trap 'rm -rf "${WORK}"' EXIT

# linux/amd64 → x86_64 (pip 플랫폼 태그용)
pip_arch() {
  case "$1" in
    linux/amd64) echo x86_64 ;;
    linux/arm64|linux/arm64/v8) echo aarch64 ;;
    *) die "지원하지 않는 플랫폼: $1" ;;
  esac
}

# ---------------------------------------------------------------- 1. 저장소
say "1. 저장소 — ${TAG} (${COMMIT:0:12})"
git -C "${REPO}" bundle create "${OUT}/repo.bundle" "refs/tags/${TAG}"
git -C "${REPO}" archive "${TAG}" deploy server | tar -x -C "${WORK}"

# ---------------------------------------------------------------- 2. 이미지 목록
say "2. 이미지 목록 — 그 태그의 compose 파일에서"
# 필수 비밀값(:?)은 목록을 뽑는 데만 쓰는 자리값이다. 실제 .env 는 읽지 않는다(--env-file /dev/null).
central_env=(MK2_MYSQL_PASSWORD=x MK2_TSDB_PASSWORD=x MK2_TSDB_ROOT_PASSWORD=x MYSQL_ROOT_PASSWORD=x
             MK2_WS_TOKEN=x MK2_EDGE_TOKEN=x MK2_CAPTURE_TOKEN=x GRAFANA_ADMIN_PASSWORD=x
             "MK2_BACKEND_IMAGE=${BACKEND_IMAGE}")
edge_env=(MK2_ZONE_ID=x MK2_CENTRAL_MQTT_HOST=x MK2_CENTRAL_OTLP=x:4317)

central_files=(-f docker-compose.yml)
[[ -f "${WORK}/deploy/docker-compose.override.yml.example" ]] \
  && central_files+=(-f docker-compose.override.yml.example)
(cd "${WORK}/deploy" && env "${central_env[@]}" docker compose --env-file /dev/null "${central_files[@]}" config --images) \
  | sort -u > "${WORK}/central.txt"
# e2e-sim.sh 의 노드 컨테이너 이미지(python:3.12-slim 등)
E2E_IMAGE="$(grep -oE 'python:[0-9.]+-slim' "${WORK}/deploy/scripts/e2e-sim.sh" | head -1 || true)"
[[ -n "${E2E_IMAGE}" ]] || die "e2e-sim.sh 에서 노드 이미지(python:*-slim)를 찾지 못했다"
echo "${E2E_IMAGE}" >> "${WORK}/central.txt"
sort -u -o "${OUT}/images-central.txt" "${WORK}/central.txt"
(cd "${WORK}/deploy/edge" && env "${edge_env[@]}" docker compose --env-file /dev/null config --images) \
  | sort -u > "${OUT}/images-edge.txt"
grep -q 'mk2-backend:local' "${OUT}/images-central.txt" && die "백엔드 이미지가 로컬 빌드명이다 — MK2_BACKEND_IMAGE 치환 실패"
echo "  중앙(${CENTRAL_PLATFORM}):"; sed 's/^/    /' "${OUT}/images-central.txt"
echo "  엣지(${EDGE_PLATFORM}):";    sed 's/^/    /' "${OUT}/images-edge.txt"

# ---------------------------------------------------------------- 3. pull + save
# 같은 이미지 이름이 중앙·엣지에 다른 플랫폼으로 들어간다(mosquitto 등). 한 묶음씩 pull 직후 save 해서
# 로컬 태그가 그 묶음의 플랫폼을 가리킬 때 저장한다. save --platform 을 아는 도커면 그것도 건다.
save_platform=()
docker save --help 2>/dev/null | grep -q -- '--platform' && save_platform=(--platform)
save_group() {   # <이름> <플랫폼>
  local name="$1" platform="$2" img
  local -a imgs=()
  mapfile -t imgs < "${OUT}/images-${name}.txt"
  for img in "${imgs[@]}"; do
    if [[ "${img}" == "${BACKEND_IMAGE}" && "${BACKEND_SOURCE}" == "build" ]]; then
      docker build -q --platform "${platform}" -t "${img}" "${WORK}/server" >/dev/null || die "빌드 실패: ${img}"
      echo "  built  ${img} (${platform})"
      continue
    fi
    docker pull -q --platform "${platform}" "${img}" >/dev/null || die "pull 실패: ${img} (${platform})"
    echo "  pulled ${img} (${platform})"
  done
  # save --platform 은 containerd 이미지 저장소에서 필요하고, 옛 저장소(graphdriver)에서는 거부될 수 있다 — 그때는 없이 다시
  if ! { [[ ${#save_platform[@]} -gt 0 ]] \
         && docker save "${save_platform[@]}" "${platform}" "${imgs[@]}" | gzip -1 > "${OUT}/images-${name}.tar.gz"; }; then
    docker save "${imgs[@]}" | gzip -1 > "${OUT}/images-${name}.tar.gz" || die "save 실패: images-${name}"
  fi
  echo "  saved images-${name}.tar.gz ($(du -h "${OUT}/images-${name}.tar.gz" | cut -f1))"
}
say "3. 이미지 받기·저장"
save_group central "${CENTRAL_PLATFORM}"
save_group edge "${EDGE_PLATFORM}"

# ---------------------------------------------------------------- 4. 파이썬 휠
# --only-binary 로 받는다 — 대상에는 컴파일러도 인터넷도 없다.
wheels() {   # <디렉터리> <파이썬 버전> <arch>
  local dir="$1" pyver="$2" arch="$3"
  mkdir -p "${dir}"
  "${PYTHON}" -m pip download -q --disable-pip-version-check --only-binary=:all: \
    --implementation cp --python-version "${pyver}" \
    --platform "manylinux_2_28_${arch}" --platform "manylinux_2_17_${arch}" --platform "manylinux2014_${arch}" \
    -d "${dir}" "${NODE_PKGS[@]}"
  echo "  ${dir#"${OUT}"/}: $(find "${dir}" -name '*.whl' | wc -l | tr -d ' ')개 (cp${pyver/./} ${arch})"
}
say "4. 파이썬 휠"
E2E_PY="${E2E_IMAGE#python:}"; E2E_PY="${E2E_PY%-slim}"
wheels "${OUT}/wheels/e2e" "${E2E_PY}" "$(pip_arch "${CENTRAL_PLATFORM}")"
wheels "${OUT}/wheels/pi" "${PI_PYTHON}" "${PI_ARCH}"

# ---------------------------------------------------------------- 5. 목록·체크섬
cp "${REPO}/deploy/scripts/load-offline.sh" "${OUT}/load-offline.sh"
say "5. MANIFEST · SHA256SUMS"
{
  echo "tag=${TAG}"
  echo "commit=${COMMIT}"
  echo "backend_image=${BACKEND_IMAGE}"
  echo "backend_source=${BACKEND_SOURCE}"
  echo "central_platform=${CENTRAL_PLATFORM}"
  echo "edge_platform=${EDGE_PLATFORM}"
  echo "e2e_python=${E2E_PY}"
  echo "pi_python=${PI_PYTHON} (${PI_ARCH})"
  echo "created=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
} > "${OUT}/MANIFEST.txt"
(cd "${OUT}" && find . -type f | sed 's|^\./||' | LC_ALL=C sort | xargs sha256sum > "${WORK}/sums")
mv "${WORK}/sums" "${OUT}/SHA256SUMS"
echo "  $(wc -l < "${OUT}/SHA256SUMS" | tr -d ' ')개 파일"

say "완료: ${OUT} ($(du -sh "${OUT}" | cut -f1))"
echo "  대상 서버에서: ./load-offline.sh <이 디렉터리>  (deploy/scripts/load-offline.sh — docs/deployment/offline.md)"
