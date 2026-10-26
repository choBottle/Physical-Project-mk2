#!/usr/bin/env bash
# deploy/.env 생성 — .env.example 을 복사하고 change_me* 자리의 비밀값을 무작위 영숫자 32자로 채운다.
#
#   ./deploy/scripts/init-env.sh            # .env 가 없을 때만 만든다
#   ./deploy/scripts/init-env.sh --force    # 덮어쓴다(⚠ DB 볼륨이 이미 있으면 옛 비밀번호와 어긋난다)
#
# 영숫자만 쓰는 이유: .env 를 읽는 파서가 셋(셸 · compose dotenv · systemd)이고 특수문자 해석이 서로 다르다.
set -euo pipefail

DEPLOY_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SRC="${DEPLOY_DIR}/.env.example"
DST="${DEPLOY_DIR}/.env"

if [[ -f "${DST}" && "${1:-}" != "--force" ]]; then
  echo "이미 있다: ${DST} (덮어쓰려면 --force)"
  exit 0
fi

rand() { LC_ALL=C tr -dc 'A-Za-z0-9' < /dev/urandom | head -c 32; }

umask 077
tmp="$(mktemp)"
while IFS= read -r line || [[ -n "${line}" ]]; do
  if [[ "${line}" =~ ^([A-Z0-9_]+)=change_me ]]; then
    echo "${BASH_REMATCH[1]}=$(rand)"
  else
    echo "${line}"
  fi
done < "${SRC}" > "${tmp}"
mv "${tmp}" "${DST}"
chmod 600 "${DST}" 2>/dev/null || true

echo "생성: ${DST} (권한 600, 비밀값 $(grep -c '=change_me' "${SRC}")개 무작위 생성)"
echo "다음: 엣지를 붙일 서버라면 MK2_EDGE_BIND · MK2_KAFKA_EDGE_ADVERTISED 를 서버 터널 주소로 바꾼다."
