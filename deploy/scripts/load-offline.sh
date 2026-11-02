#!/usr/bin/env bash
# 폐쇄망 설치 묶음 적재 — **대상 서버(인터넷 없음)**에서 돌린다. 묶음은 bundle-offline.sh 가 만든다.
#
#   ./load-offline.sh /media/usb/mk2-v1.0.0            # 중앙 서버: 체크섬 검사 → 중앙 이미지 적재
#   ./load-offline.sh /media/usb/mk2-v1.0.0 edge       # 구역 엣지 노드: 체크섬 검사 → 엣지 이미지 적재
#
# 체크섬이 하나라도 어긋나면 아무것도 적재하지 않고 종료 코드 1 로 끝난다(복사 중 손상·바꿔치기).
# 저장소를 풀고 기동하는 절차는 마지막에 출력한다 — 상세: docs/deployment/offline.md
set -euo pipefail

usage() { sed -n '2,8p' "$0"; exit "${1:-0}"; }
[[ "${1:-}" == "-h" || "${1:-}" == "--help" ]] && usage 0
[[ $# -ge 1 && $# -le 2 ]] || usage 1

BUNDLE="$(cd "$1" && pwd)"
ROLE="${2:-central}"
[[ "${ROLE}" == "central" || "${ROLE}" == "edge" ]] || { echo "역할은 central | edge: ${ROLE}" >&2; exit 1; }

for c in docker sha256sum; do
  command -v "${c}" >/dev/null 2>&1 || { echo "필요한 명령이 없다: ${c}" >&2; exit 1; }
done
[[ -f "${BUNDLE}/SHA256SUMS" && -f "${BUNDLE}/MANIFEST.txt" ]] \
  || { echo "묶음이 아니다(SHA256SUMS·MANIFEST.txt 없음): ${BUNDLE}" >&2; exit 1; }

echo "▶ 1. 체크섬 검사 — ${BUNDLE}"
if ! (cd "${BUNDLE}" && sha256sum --quiet -c SHA256SUMS); then
  echo "✗ 체크섬 불일치 — 묶음을 다시 복사한다. 아무것도 적재하지 않았다." >&2
  exit 1
fi
echo "  ✅ $(wc -l < "${BUNDLE}/SHA256SUMS" | tr -d ' ')개 파일 일치"
sed 's/^/  /' "${BUNDLE}/MANIFEST.txt"

echo "▶ 2. 이미지 적재 — ${ROLE}"
docker load -i "${BUNDLE}/images-${ROLE}.tar.gz"

echo "▶ 3. 적재 확인"
missing=0
while IFS= read -r img; do
  [[ -n "${img}" ]] || continue
  if docker image inspect "${img}" >/dev/null 2>&1; then
    echo "  ✅ ${img}"
  else
    echo "  ❌ ${img}"; missing=$((missing+1))
  fi
done < "${BUNDLE}/images-${ROLE}.txt"
[[ ${missing} -eq 0 ]] || { echo "✗ 이미지 ${missing}개가 없다" >&2; exit 1; }

TAG="$(sed -n 's/^tag=//p' "${BUNDLE}/MANIFEST.txt")"
IMG="$(sed -n 's/^backend_image=//p' "${BUNDLE}/MANIFEST.txt")"
echo
echo "다음(docs/deployment/offline.md):"
echo "  git clone -b ${TAG} ${BUNDLE}/repo.bundle Physical-Project-mk2"
if [[ "${ROLE}" == "central" ]]; then
  echo "  cd Physical-Project-mk2/deploy && ./scripts/init-env.sh"
  echo "  sed -i 's|^MK2_BACKEND_IMAGE=.*|MK2_BACKEND_IMAGE=${IMG}|' .env"
  echo "  docker compose up -d --wait        # --build 를 붙이지 않는다"
  echo "  ./scripts/healthcheck.sh"
else
  echo "  cd Physical-Project-mk2/deploy/edge && cp .env.example .env   # MK2_ZONE_ID · MK2_CENTRAL_* 를 채운다"
  echo "  docker compose up -d --wait"
fi
