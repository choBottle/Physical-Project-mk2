#!/usr/bin/env bash
# deploy/.env 생성 — .env.example 을 복사하고 change_me* 자리의 비밀값을 무작위 영숫자 32자로 채운다.
#
#   ./deploy/scripts/init-env.sh            # .env 가 없을 때만 만든다
#   ./deploy/scripts/init-env.sh --force    # 덮어쓴다(⚠ DB 볼륨이 이미 있으면 옛 비밀번호와 어긋난다)
#
# .env 를 쓴 뒤 같은 COMPOSE_PROJECT_NAME 의 DB 볼륨(<이름>_mysql_data · <이름>_timescale_data)이 이미 있으면 경고한다
# (docker CLI 가 있을 때만 — 지우지도, 실패하지도 않는다).
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

# 같은 프로젝트 이름의 DB 볼륨이 이미 있으면 경고만 한다(지우지 않는다, 실패하지 않는다).
# 볼륨 이름은 <COMPOSE_PROJECT_NAME>_mysql_data 처럼 프로젝트 이름이 앞에 붙는다 — 이름이 같으면 옛 데이터(와 옛 비밀번호)를 그대로 쓴다.
if command -v docker >/dev/null 2>&1; then
  project="${COMPOSE_PROJECT_NAME:-$(grep -m1 '^COMPOSE_PROJECT_NAME=' "${DST}" | cut -d= -f2- || true)}"
  project="$(printf '%s' "${project:-mk2}" | tr '[:upper:]' '[:lower:]')"
  existing=()
  for v in "${project}_mysql_data" "${project}_timescale_data"; do
    if docker volume inspect "${v}" >/dev/null 2>&1; then existing+=("${v}"); fi
  done
  if [[ ${#existing[@]} -gt 0 ]]; then
    echo
    echo "⚠ 경고: 데이터 볼륨이 이미 있다 — ${existing[*]}"
    echo "  COMPOSE_PROJECT_NAME=${project} 로 기동하면 이 볼륨을 그대로 다시 쓴다. DB 비밀번호는 볼륨을 처음 초기화할 때"
    echo "  박히므로 볼륨 안의 비밀번호는 옛 .env 의 값이고, 방금 만든 .env 의 새 비밀번호와 어긋나 백엔드가 DB 에 못 붙는다."
    echo "  셋 중 하나를 고른다:"
    echo "    1) 옛 데이터를 이어 쓴다 — 옛 deploy/.env 를 되살린다(따로 보관해 둔 사본)"
    echo "    2) 같은 호스트에 별도 배포를 새로 세운다 — deploy/.env 의 COMPOSE_PROJECT_NAME 을 다른 이름으로 바꾸고,"
    echo "       옛 배포의 네트워크가 남아 있으면 MK2_NET_SUBNET · MK2_DB_APP_HOST 도 함께 바꾼다(아래 대역 경고 참고)"
    echo "    3) 옛 데이터를 버린다(되돌릴 수 없다) — 의도했을 때만: docker volume rm ${existing[*]}"
    echo "  자세히: docs/deployment/README.md §3 · §6"
    echo
  fi
fi
# 네트워크 대역 — compose 는 대역을 고정하므로(MK2_NET_SUBNET) 같은 대역의 도커 네트워크가 이미 있으면
# "Pool overlaps with other one on this address space" 로 기동이 실패한다. 옛 배포(다른 프로젝트 이름 포함)나
# 다른 도구가 만든 네트워크일 수 있다. 우리 프로젝트의 네트워크(<이름>_mk2)는 재사용이므로 빼고 본다.
if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
  subnet="$(grep -m1 '^MK2_NET_SUBNET=' "${DST}" | cut -d= -f2- || true)"
  subnet="${subnet:-172.28.0.0/16}"
  used="$(docker network ls -q | xargs docker network inspect -f '{{.Name}} {{range .IPAM.Config}}{{.Subnet}} {{end}}' 2>/dev/null || true)"
  clash="$(printf '%s
' "${used}" | awk -v s="${subnet}" -v own="${project:-mk2}_mk2" '$1 != own { for (i = 2; i <= NF; i++) if ($i == s) print $1 }')"
  if [[ -n "${clash}" ]]; then
    free=""
    for n in 29 30 31 27 26 25; do
      if ! printf '%s
' "${used}" | grep -q " 172\.${n}\.0\.0/16"; then free="${n}"; break; fi
    done
    echo
    echo "⚠ 경고: 도커 네트워크 대역 ${subnet} 을 이미 쓰는 네트워크가 있다 — $(echo ${clash})"
    echo "  그대로 기동하면 \"Pool overlaps with other one on this address space\" 로 실패한다."
    if [[ -n "${free}" ]]; then
      echo "  deploy/.env 에서 두 값을 짝으로 바꾼다(MySQL 앱 계정 host 제한이 대역과 짝이다):"
      echo "    MK2_NET_SUBNET=172.${free}.0.0/16"
      echo "    MK2_DB_APP_HOST=172.${free}.%"
    else
      echo "  deploy/.env 의 MK2_NET_SUBNET 과 MK2_DB_APP_HOST 를 비어 있는 대역으로 짝지어 바꾼다."
    fi
    echo "  자세히: docs/deployment/README.md §3"
    echo
  fi
fi
echo "다음: 엣지를 붙일 서버라면 MK2_EDGE_BIND 를 서버 터널 주소로 바꾼다(Kafka EDGE 9095 는 1.0 에서 쓰지 않으니 그대로 둔다 — docs/deployment/edge.md)."
