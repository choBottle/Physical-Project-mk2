# 외부 서버 주소가 바뀔 때 — 객체 탐지·가시화·Unity 연결 갱신

중앙 스택(`deploy/`) 밖에서 도는 서버, 예를 들어 객체 탐지 추론 서버나 Unity PC를 다른
기기로 옮기면 그 서버를 **부르는 쪽**의 설정을 바꿔야 한다. 주소는 코드에 넣지 않고 각
장비의 환경변수나 설정 파일에 둔다. 그래서 서버를 옮겨도 코드를 고치거나 다시 배포할
필요는 없고, 아래 표의 값만 바꾸면 된다.

이 문서의 `<new-host>`는 새 서버의 주소다(같은 tailnet이면 `tailscale ip -4` 값). 실제
주소는 저장소에 커밋하지 않는다. 팀 공지나 각 장비의 `.env`에만 적는다.

## 1. 객체 탐지 스트림 서버를 옮겼을 때

`camera360/server_stream_multi_source.py`(영상 수신·보기)와 `vision_infer.py`(실시간 추론)가
도는 기기다.

| 포트 | 용도 |
|------|------|
| 10001 | cam360 업로드(`/upload_pano`)와 영상 보기 |
| 10002 | drone 영상 보기 |
| 10003 | robot1 영상 보기 |
| 10004 | robot2 영상 보기 |
| 6380 | 전용 Redis (`camera_stream:*`, `vision_stream:*`) |

### 바꿔야 하는 곳

| 부르는 쪽 | 설정 | 바꾸는 법 |
|-----------|------|-----------|
| 360 카메라 노트북 | `MK2_UPLOAD_STREAM_URL` (`stream_to_server.py`) | `http://<new-host>:10001/upload_pano` 로 바꾸고 `stream_to_server.py`를 다시 시작한다. 모든 업로드가 같은 기기로 간다면 `MK2_SERVER_HOST=<new-host>` 하나로 충분하다. |
| 가시화 콘솔 (`viz-debugger`) | 연결 관리자 → **객체 탐지 추론 스트림** → 서버 IP | 서버 IP 칸 하나만 바꾼다. 10001~10004 포트 줄은 모두 이 IP를 쓴다. |
| Redis 구독자 (AI 서버 등) | 각 프로그램의 Redis URL | `redis://<new-host>:6380/0` |
| 같은 기기의 `vision_infer.py` | `vision_config.yaml`의 `live.redis` | 기본값 `redis://127.0.0.1:6380/0`. 같은 기기에서 돌면 바꿀 필요가 없다. |

### 새 서버에서 할 일

1. Redis를 새 기기의 tailscale 주소에도 묶어서 띄운다. 비밀번호가 없으므로 6380은
   tailscale 인터페이스에만 연다.

   ```
   redis-server --port 6380 --bind "127.0.0.1 $(tailscale ip -4)" --protected-mode no \
     --save "" --appendonly no --daemonize yes
   ```

2. 스트림 서버가 영상을 끌어올 로봇·드론 Pi 주소를 준다. 우선순위는 명령행
   `--host <소스>=<주소>`(예전 `--robot1/--robot2/--drone`도 된다) > 환경변수 `PD_HOST_<소스>`
   (`PD_HOST_ROBOT1` 등) > `camera360/hosts.local.json`(커밋하지 않는다) 순이다. 소스 목록 자체는
   `camera360/sources.json`이다. 옛 기기의
   `hosts.local.json`을 그대로 복사해 와도 된다.
3. 방화벽에서 10001~10004, 6380을 tailnet 쪽에만 연다.
4. WSL에서 돌린다면 WSL을 재시작할 때마다 Redis를 다시 띄워야 한다.

## 2. 인지 서버(7864)를 옮겼을 때 — Go1 카메라 업로드와 탐지 전달

| 부르는 쪽 | 설정 | 바꾸는 법 |
|-----------|------|-----------|
| Go1 Pi `go1-front-upload` | `/etc/hw-robot.env`의 `HW_UPLOAD_URL` | `http://<new-host>:7864/upload` |
| Go1 Pi `go1-detect-forward` | `/etc/hw-robot.env`의 `HW_DETECT_BASE` | `http://<new-host>:7864` |
| `unidepth_dual_yolo.py` | `CONTROL_URL` | `http://<new-host>:7864/command/go1` |

Go1 유닛은 `EnvironmentFile=-/etc/hw-robot.env`로 값을 읽는다. 파일을 고친 뒤 다시 시작한다.

```
sudo systemctl restart go1-front-upload go1-detect-forward
journalctl -u go1-front-upload -n 20
```

값이 비어 있으면 시작할 때 `[warn] ... 미설정:` 줄이 찍히고 `127.0.0.1`로 보낸다. 이
경고가 보이면 값이 들어가지 않은 것이다. 이 버전 이전의 유닛 파일을 쓰는 Pi라면
한 번은 `hardware/pi/deploy/install-units.sh go1-front-upload go1-detect-forward`로
유닛을 다시 설치한다.

## 3. 360 앵커 서버(7866)를 옮겼을 때

| 부르는 쪽 | 설정 | 바꾸는 법 |
|-----------|------|-----------|
| 360 카메라 노트북 `stream_to_server.py`, `pro2_auto_bg.py` | `MK2_UPLOAD_URL` | `http://<new-host>:7866/upload_pano` |
| `anchor360_bridge.py` | `MK2_ANCHOR360_URL` | `http://<new-host>:7866/anchor360_latest` |

세 값이 모두 같은 기기를 가리키면 `MK2_SERVER_HOST=<new-host>` 하나로 대신할 수 있다.
변수 목록은 [`camera360/README.md`](../../camera360/README.md)와
[`camera360/.env.example`](../../camera360/.env.example)에 있다.

## 4. Unity PC를 옮겼을 때

Unity는 UDP로 받기만 하므로 Unity 쪽에는 바꿀 것이 없다. 보내는 쪽의 대상 주소를 바꾼다.

| 보내는 쪽 | 설정 | 포트 |
|-----------|------|------|
| `camera360/anchor360_live.py` | `--unity-ip <unity-pc>` | 5010 |
| Go1 Pi `go1-detect-forward` | `/etc/hw-robot.env`의 `HW_UNITY_IP` | 5009 |
| 로봇 상태 중계 (`twin_relay_out.py`) | `HW_TWIN_RELAY_HOST` | 15200 (`HW_TWIN_RELAY_PORT`) |

Unity PC의 Windows 방화벽에서 해당 UDP 포트의 수신을 허용해야 한다. 포트 전체 목록은
[docs/PORTS.md](../PORTS.md)에 있다.

## 5. 중앙 서버를 옮겼을 때

MQTT, OTLP, WebSocket 게이트웨이 주소는 엣지와 장치 노드의 `.env`에 있다. 절차는
[edge.md](edge.md)를 따른다. 콘솔의 게이트웨이 주소는 연결 관리자에서 바꾼다
(`ws://<new-host>:8765/state?token=<MK2_WS_TOKEN>`).

## 6. 옮긴 뒤 확인

| 확인 | 명령 | 기대 결과 |
|------|------|-----------|
| 스트림 서버 | 브라우저로 `http://<new-host>:10001/` | cam360 영상 페이지 |
| Redis | `redis-cli -h <new-host> -p 6380 ping` | `PONG` |
| Redis에 프레임이 들어오는지 | `redis-cli -h <new-host> -p 6380 xlen camera_stream:cam360` | 늘어나는 숫자 |
| Go1 업로드 | `journalctl -u go1-front-upload -n 20` | `미설정` 경고 없음, 업로드 성공 로그 |
| 콘솔 | 객체 탐지 추론 스트림 카드 | 4개 포트 영상이 보임 |
| Unity | Console 창 | `Anchor360ObstacleReceiver` 수신 로그 |

## 7. 팀에 알릴 때

서버를 옮긴 사람은 아래 형식으로 알린다. 실제 주소는 팀 채널에만 쓰고 저장소, 이슈,
PR에는 쓰지 않는다.

```
객체 탐지 추론 서버 이전: <기기 이름>
주소 <new-host>

360 카메라 노트북 업로드   http://<new-host>:10001/upload_pano
Redis 구독 (AI 서버 등)    redis://<new-host>:6380/0
영상 보기: cam360          http://<new-host>:10001/
영상 보기: drone           http://<new-host>:10002/
영상 보기: robot1          http://<new-host>:10003/
영상 보기: robot2          http://<new-host>:10004/

바꿔야 하는 곳: 360 노트북 MK2_UPLOAD_STREAM_URL, 콘솔 연결 관리자 서버 IP,
Redis 구독 프로그램 URL
```
