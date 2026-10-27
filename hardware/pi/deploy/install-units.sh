#!/usr/bin/env bash
# systemd 유닛 설치기 — 저장소의 유닛 템플릿을 이 장비의 계정·경로로 채워 설치한다
# ==================================================================================
# deploy/*.service 는 특정 계정·경로를 박지 않은 **템플릿**이다. 아래 자리표시자를
# 이 스크립트가 sed 로 치환해 /etc/systemd/system/ 에 쓴다. 그래서 `sudo cp` 로
# 직접 복사하면 안 된다(자리표시자가 그대로 남아 유닛이 뜨지 않는다).
#
#   @MK2_USER@     서비스 실행 계정        기본: 이 스크립트를 부른 사용자(sudo 면 SUDO_USER)
#   @MK2_HOME@     그 계정의 홈            기본: getent passwd 의 홈 디렉터리
#   @MK2_PI_DIR@   코드 위치(이 pi/ 폴더)  기본: 이 스크립트 기준 상위 폴더(= 저장소의 pi/)
#   @MK2_VENV@     파이썬 venv             기본: @MK2_HOME@/venv
#
# 사용:
#   pi/deploy/install-units.sh sensor-node                      # 하나 설치
#   pi/deploy/install-units.sh go1-watchdog go1-watchdog.timer  # .timer 도 같은 방식
#   pi/deploy/install-units.sh --enable robot-node              # 설치 + 부팅 등록
#   pi/deploy/install-units.sh --all                            # deploy/ 의 유닛 전부
#   pi/deploy/install-units.sh --print go1-sdk                  # 설치 없이 치환 결과만 출력
#
# 옵션 (환경변수로도 줄 수 있다: MK2_USER / MK2_HOME / MK2_PI_DIR / MK2_VENV / MK2_UNIT_DIR)
#   --user U      실행 계정
#   --home H      홈 디렉터리
#   --pi-dir D    코드 위치
#   --venv V      venv 위치
#   --dest D      설치 위치 (기본 /etc/systemd/system)
#   --enable      설치 후 systemctl enable (기동은 하지 않는다 — 로봇을 움직이는 유닛이 있다)
#   --print       설치하지 않고 치환 결과를 표준출력으로
#
# 팀 기존 구성(계정 physical, 코드 ~/hw/pi, venv ~/venv)은 physical 계정으로
# 그냥 실행하면 그대로 재현된다:  ~/hw/pi/deploy/install-units.sh <유닛...>
# (명시하려면 --user physical --pi-dir ~/hw/pi)
set -euo pipefail

DEPLOY_DIR="$(cd "$(dirname "$0")" && pwd)"
MK2_USER="${MK2_USER:-${SUDO_USER:-$(id -un)}}"
MK2_HOME="${MK2_HOME:-}"
MK2_PI_DIR="${MK2_PI_DIR:-$(cd "$DEPLOY_DIR/.." && pwd)}"
MK2_VENV="${MK2_VENV:-}"
MK2_UNIT_DIR="${MK2_UNIT_DIR:-/etc/systemd/system}"
DO_ENABLE=0; DO_PRINT=0; DO_ALL=0
UNITS=()

while [ $# -gt 0 ]; do
  case "$1" in
    --user)    MK2_USER="$2";     shift 2 ;;
    --home)    MK2_HOME="$2";     shift 2 ;;
    --pi-dir)  MK2_PI_DIR="$2";   shift 2 ;;
    --venv)    MK2_VENV="$2";     shift 2 ;;
    --dest)    MK2_UNIT_DIR="$2"; shift 2 ;;
    --enable)  DO_ENABLE=1; shift ;;
    --print)   DO_PRINT=1;  shift ;;
    --all)     DO_ALL=1;    shift ;;
    -h|--help) sed -n '2,33p' "$0"; exit 0 ;;
    -*) echo "알 수 없는 옵션: $1" >&2; exit 1 ;;
    *)  UNITS+=("$1"); shift ;;
  esac
done

if [ "$DO_ALL" = "1" ]; then
  for f in "$DEPLOY_DIR"/*.service "$DEPLOY_DIR"/*.timer; do
    [ -f "$f" ] && UNITS+=("$(basename "$f")")
  done
fi
if [ "${#UNITS[@]}" -eq 0 ]; then
  echo "설치할 유닛을 지정한다 (예: sensor-node, --all). 도움말: $0 --help" >&2
  exit 1
fi

# 홈은 계정에서 구한다. sudo 로 부르면 $HOME 이 /root 가 되는 함정을 피한다.
if [ -z "$MK2_HOME" ]; then
  MK2_HOME="$(getent passwd "$MK2_USER" 2>/dev/null | cut -d: -f6 || true)"
  if [ -z "$MK2_HOME" ]; then
    echo "  ✗ 계정 '$MK2_USER' 를 찾을 수 없다. --user 또는 --home 을 준다" >&2
    exit 1
  fi
fi
MK2_VENV="${MK2_VENV:-$MK2_HOME/venv}"

# sed 치환 구분자로 '|' 를 쓰므로 값에 '|' 가 들어가면 안 된다.
for v in "$MK2_USER" "$MK2_HOME" "$MK2_PI_DIR" "$MK2_VENV"; do
  case "$v" in *'|'*) echo "  ✗ 값에 '|' 를 쓸 수 없다: $v" >&2; exit 1 ;; esac
done

render() {
  sed -e "s|@MK2_USER@|$MK2_USER|g" \
      -e "s|@MK2_HOME@|$MK2_HOME|g" \
      -e "s|@MK2_PI_DIR@|$MK2_PI_DIR|g" \
      -e "s|@MK2_VENV@|$MK2_VENV|g" "$1"
}

SUDO=""
if [ "$DO_PRINT" = "0" ] && [ "$(id -u)" != "0" ]; then
  SUDO="sudo"
fi

if [ "$DO_PRINT" = "0" ]; then
  printf '[유닛 설치] user=%s home=%s pi_dir=%s venv=%s -> %s\n' \
    "$MK2_USER" "$MK2_HOME" "$MK2_PI_DIR" "$MK2_VENV" "$MK2_UNIT_DIR"
fi

INSTALLED=()
for u in "${UNITS[@]}"; do
  case "$u" in *.service|*.timer) ;; *) u="$u.service" ;; esac
  src="$DEPLOY_DIR/$u"
  if [ ! -f "$src" ]; then
    echo "  ✗ $src 없음" >&2; exit 1
  fi
  out="$(render "$src")"
  # 모르는 자리표시자가 남아 있으면 설치하지 않는다 — 반쯤 채운 유닛은 200/CHDIR 크래시루프가 된다.
  if printf '%s\n' "$out" | grep -q '@MK2_[A-Z_]*@'; then
    echo "  ✗ $u 에 치환되지 않은 자리표시자가 있다:" >&2
    printf '%s\n' "$out" | grep -n '@MK2_[A-Z_]*@' >&2
    exit 1
  fi
  if [ "$DO_PRINT" = "1" ]; then
    printf '# ---- %s\n%s\n' "$u" "$out"
    continue
  fi
  printf '%s\n' "$out" | $SUDO tee "$MK2_UNIT_DIR/$u" > /dev/null
  INSTALLED+=("$u")
  printf '  ✓ %s\n' "$u"
done

# 인지 서버 주소가 없으면 go1-front-upload / go1-detect-forward 는 127.0.0.1:7864 를 보고
# Unity(5009 장애물 · 5001 영상)에는 아무것도 가지 않는다. 조용히 실패하므로 여기서 알린다.
for u in "${UNITS[@]}"; do
  case "$u" in
    go1-front-upload*|go1-detect-forward*)
      for v in HW_UPLOAD_URL HW_DETECT_BASE; do
        grep -q "^$v=." /etc/hw-robot.env 2>/dev/null || \
          echo "  ⚠ /etc/hw-robot.env 에 $v 가 없다 — $u 는 127.0.0.1:7864 를 본다 (hw-robot.env.example 참고)" >&2
      done ;;
  esac
done

if [ "$DO_PRINT" = "1" ]; then
  exit 0
fi

$SUDO systemctl daemon-reload
if [ "$DO_ENABLE" = "1" ]; then
  for u in "${INSTALLED[@]}"; do
    $SUDO systemctl enable "$u" > /dev/null 2>&1 && printf '  ✓ enable %s\n' "$u"
  done
fi
printf '완료. 기동은 수동: sudo systemctl start <유닛>\n'
