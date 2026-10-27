# 바꿔 끼우기 — 360 카메라, 검출 모델, 디지털 트윈

이 플랫폼은 특정 제품에 묶이지 않는 것을 목표로 한다. 이 문서는 외부 기관이 다른 카메라,
다른 모델, Unity가 아닌 트윈을 쓸 때 **어디까지 설정만으로 되고 어디부터 코드가 필요한지**를
적는다. 2026-10-27 기준 코드를 확인한 결과다.

| 바꾸려는 것 | 지금 | 방법 |
|-------------|------|------|
| 360 카메라 (Insta360 Pro2 → 다른 기종) | 설정만으로 된다 | `camera360/upload_equirect.py` |
| 영상 스트림 서버에 소스 추가 | 설정만으로 된다 | `camera360/sources.json` (§1-1) |
| 검출 모델 (camera360 전체) | 설정만으로 된다 | config의 `backend` 한 줄 |
| AI 프레임워크 provider | 설정 파일 + 함수 하나 | `ai/perception-framework` 의 `model_config` |
| 트윈 추가 (Unity와 함께 다른 뷰어) | 설정만으로 된다 | 받는 곳을 쉼표로 추가 |
| 트윈 교체 (Gazebo 등, Unity 없이) | 설정만으로 된다 (1.0.3) | `hardware/twin/twin_gateway.py` (§3-2) |
| 로봇 명령을 Unity가 아닌 곳에서 | 아직 Unity 프로토콜 | §3-3 |

## 1. 360 카메라

서버 쪽(`pano_receiver.py` 7866, `server_stream_multi_source.py` 10001, `anchor360_live.py`)은
equirect JPEG만 받는다. 카메라 종류는 모른다. Insta360 Pro2 전용인 것은 카메라를
제어하는 송신기 `stream_to_server.py`(연결, 프리뷰 시작)와 `pro2_auto_bg.py`(ProStitcher)뿐이다.
Insta360 SDK는 쓰지 않는다.

다른 360 카메라(Ricoh Theta, GoPro Max, Insta360 X 시리즈 등)는 `upload_equirect.py`로 올린다.

```
# 카메라 앱이나 SDK가 equirect JPEG을 폴더에 쓰는 경우
python camera360/upload_equirect.py --watch <폴더>

# 카메라가 equirect 라이브 스트림(RTSP/RTMP/HTTP)이나 USB 장치로 나오는 경우
python camera360/upload_equirect.py --stream rtsp://<camera>/live --fps 2

# 파일 몇 장
python camera360/upload_equirect.py pano1.jpg pano2.jpg
```

보내는 곳은 `MK2_UPLOAD_URL`과 `MK2_UPLOAD_STREAM_URL`(또는 `MK2_SERVER_HOST`)로 정한다.
업로드 형식(필드 `file`, `capture_id`, `camera_id`, `meta`)은 `stream_to_server.py`와 같다.

카메라 조건:

- 출력이 2:1 equirect여야 한다. 아니면 경고를 낸다.
- 수평 보정(horizon leveling)을 켠다. `anchor360_live.py`는 카메라가 수평이라고 가정한다.
- 설치 높이와 하향각이 다르면 `anchor360_live.py --cam-h <m> --pitch <deg>`로 맞춘다.
- 카메라를 두 대 이상 쓰면 `--camera-id`를 다르게 주고 `anchor360_live.py --watch-dir`로
  각 폴더를 본다.

## 1-1. 영상 스트림 서버의 소스 (1.0.2)

`server_stream_multi_source.py`의 소스 목록은 `camera360/sources.json`에 있다. 소스를 더하거나
포트, 끌어오는 방식을 바꿀 때 코드를 고치지 않는다. 파일이 없으면 지금과 같은 기본 4개
(cam360 10001, drone 10002, robot1 10003, robot2 10004)로 돈다. `vision_infer.py`도 같은
파일에서 기기 목록을 읽는다.

| kind | 영상을 얻는 방식 | 필요한 칸 |
|------|------------------|-----------|
| `upload` | 그 포트로 올라오는 것만 받는다 (`POST /upload_pano`, `/upload`) | 없음 |
| `mjpeg` | `http://<주소>:<video_port><path>`의 MJPEG를 끌어온다 | `video_port`, `path`(`{cam}` 자리), `cam` |
| `drone_api` | 드론 agent의 `/api/frame` 롱폴 | `video_port`, `cam` |

`mqtt_port`가 있으면 그 주소의 MQTT 전체 토픽을 상태로 받고, `null`이면 받지 않는다. 주소는
이 파일에 쓰지 않는다. `hosts.local.json`, 환경변수 `PD_HOST_<소스>`, 또는 `--host 소스=주소`로
준다. 다른 목록 파일은 `--sources <파일>`이나 `PD_SOURCES`로 고른다.

예) 로봇 한 대와 두 번째 360 카메라를 더한다.

```json
{"name": "robot3", "port": 10005, "kind": "mjpeg", "video_port": 8090, "path": "/stream/{cam}", "cam": 1, "mqtt_port": 1883},
{"name": "theta",  "port": 10006, "kind": "upload"}
```

새 포트는 방화벽에서 열고 [docs/PORTS.md](../PORTS.md)에 적는다. 콘솔의 객체 탐지 추론 스트림
카드는 포트 줄을 더해 본다.

## 2. 검출 모델

### 2-1. camera360

검출기는 `camera360/detectors.py`의 `make_detector()`로 만든다. camera360의 검출 스크립트는
모두 이 함수를 쓴다(1.0.1). 모델은 각 스크립트의 config에서 고른다.

| 스크립트 | config | 자리 |
|----------|--------|------|
| `anchor360_live.py`, `detect_send_3b2.py`, `detect_send_3b2_timed.py`, `detect_ground_3b1.py` | `unidepth_dual_yolo_config.yaml` | `models.zeroshot_detector` |
| `unidepth_dual_yolo.py` | 같은 파일 | `models.finetune_detector`, `models.zeroshot_detector` |
| `vision_infer.py` (스트림 서버의 실시간 추론) | `vision_config.yaml` | `models.yoloe` (아래) |

```yaml
models:
  zeroshot_detector:
    backend: yolo_world      # yolo_world | grounding_dino | 모듈:클래스
    weight: yolov8s-world.pt
    conf: 0.12
```

| backend | 라이선스 | 설치 | weight |
|---------|----------|------|--------|
| `yolo_world` (기본) | AGPL-3.0 (Ultralytics) | `pip install ultralytics` | `.pt` 경로나 모델 이름. 없으면 첫 실행 때 받는다 |
| `grounding_dino` | Apache-2.0 | `pip install transformers` | HF 모델 ID. 기본 `IDEA-Research/grounding-dino-tiny` |
| `패키지.모듈:클래스` | 직접 정함 | 직접 | 생성자에 그대로 넘긴다 |

직접 만든 검출기는 생성자 `(weight, classes)`와 메서드
`detect(bgr, conf, imgsz) -> [(cls_idx, conf, (x1, y1, x2, y2)), ...]` 하나만 있으면 된다.
`classes`는 config `classes.zeroshot`의 목록이고 `cls_idx`는 그 번호다. 닫힌 어휘
모델(RT-DETR, YOLOX 등)은 자기 클래스 이름을 이 목록 번호로 바꿔 돌려주면 된다.

`yolo_world`와 `grounding_dino`는 같은 사진에서 다른 결과를 낸다. 모델을 바꾸면 `conf`와
`class_conf`를 그 모델에 맞게 다시 정해야 한다. 2026-10-27에 같은 슬라이스 사진으로
두 backend 모두 끝까지(검출 → 바닥 투영 → v2 패킷) 도는 것을 확인했다.

`vision_infer.py`는 기본으로 YOLOE(검출+분할)를 쓴다. `models.yoloe`에 `backend`를 주면
그 자리를 다른 검출기가 맡는다. 자리 이름 `yoloe`는 저장 폴더와 Redis 스트림
(`vision_stream:<기기>:yoloe`)을 받는 쪽이 그대로 쓰도록 남긴 호환용이고, 실제 모델은 결과의
`backend`와 `model_file`에 적힌다. 다른 검출기는 분할(polygon)을 내지 않는다.

```yaml
models:
  yoloe:
    backend: grounding_dino          # 없으면 YOLOE
    backend_weight: null             # backend 에 넘길 가중치나 모델 ID (없으면 기본값)
    classes: [person, chair, door]
    conf: 0.3
```

아직 고정된 것: 깊이 모델. `unidepth_dual_yolo.py`는 UniDepth를 직접 쓴다. `vision_infer.py`는
`unidepth`와 `moge2_aerial` 중에서 고를 수 있지만 다른 깊이 모델을 넣으려면 러너를 코드로 더한다.

### 2-2. ai/perception-framework

프레임워크는 처음부터 교체를 전제로 만들어졌다. 검출기는 `PerceptionProvider` 꼴
(`perception/detection.py`)을 따르고, 모델은 `config/model_config.example.json`에서 고른다.
Ultralytics는 쓰는 순간에만 불러오므로 설치하지 않아도 프레임워크는 돈다
(`pip install -e ".[ultralytics]"`로 따로 설치). 새 provider를 넣을 때는
`edge/model_config.py`에 `build_x_provider` 함수 하나와 `build_all_providers`에 한 줄을 더한다.

## 3. 디지털 트윈 (Unity)

### 3-1. Unity와 함께 다른 뷰어를 붙이기 — 설정만으로 된다

트윈으로 가는 UDP 송신기 셋은 받는 곳을 쉼표로 여러 개 받는다. 곳마다 `:포트`를 붙일 수 있다.
주소가 하나면 예전과 똑같이 동작한다.

| 송신기 | 설정 | 포트 |
|--------|------|------|
| `camera360/anchor360_live.py` | `--unity-ip` 또는 `MK2_TWIN_HOSTS` | 5010 |
| `hardware/pi/robot/go1_detect_forward.py` | `HW_UNITY_IP` (`/etc/hw-robot.env`) | 5009 |
| `hardware/pi/robot/robot_state_relay.py` | `--unity_ip` | 15201 |

```
HW_UNITY_IP=<unity-pc>,<viewer-pc>
```

`hardware/HW-interface/twin_listen.py`는 이 세 포트를 받아 풀어 찍는 참조 수신기다.
Unity가 아닌 뷰어를 만들 때 출발점으로 쓴다.

### 3-2. Gazebo 등 다른 트윈 — 트윈 게이트웨이 (1.0.3)

`hardware/twin/twin_gateway.py`가 위 세 패킷을 받아 엔진 중립 모델(건물 기준 ENU)로 바꾸고,
고른 트윈으로 내보낸다. 송신기는 받는 곳을 하나 더 줄 뿐 그대로다.

| sink | 하는 일 |
|------|---------|
| `gazebo[:월드]` | gz sim(Harmonic 이상)에 모델을 만들고(`create`) 옮기고(`set_pose`) 지운다(`remove`) |
| `udp:주소:포트` | 중립 엔티티 JSON을 한 줄씩 보낸다 — 웹 3D 뷰어, ROS 2 브리지 등 |
| `모듈:클래스` | `handle(entity)` 하나를 가진 직접 만든 트윈 |

중립 엔티티 형식은 `hardware/HW-interface/twin-entity.schema.json`, 실행과 확인 기록은
[hardware/twin/README.md](../../hardware/twin/README.md). 2026-10-27에 Gazebo Harmonic(gz sim 8.11)
에서 로봇 생성·이동, 360 장애물 생성·삭제를 확인했다.

### 3-3. 패킷 형식과 좌표

| 포트 | 내용 | 형식 정의 |
|------|------|-----------|
| 5010 | 360 장애물 | JSON, 통합데이터규약 v2 — `server/contracts/common/detections.schema.json` |
| 5009 | Go1 장애물 / Go1 모션 | JSON. `state_change`와 `motion_active`가 둘 다 있으면 모션 — `hardware/HW-interface/bridge-contract.md` |
| 15201 | 로봇 상태 | 텍스트 14필드 — `hardware/HW-interface/multi-robot-contract.md` §3 |

좌표는 **Unity 월드 좌표**다(x, z 수평 m, yaw는 +Z 기준 시계 방향 +).
`hardware/HW-interface/coordinate-contract.md`가 정본이다. 다른 엔진은 받는 쪽에서 바꾼다.
건물 기준 ENU로는 `enu_x = x`, `enu_y = z`, `enu_yaw = π/2 − yaw`(rad)다. 360 장애물의
`position`은 카메라 슬라이스 기준 상대 좌표라서, 월드에 놓으려면 받는 쪽이 카메라 위치와
방위를 더해야 한다(Unity에서는 `Anchor360ObstacleReceiver`의 `yawOffsetDeg`).

### 3-4. 아직 Unity에 묶인 것 (1.x 로드맵)

- **좌표 규약.** 송신기가 Unity 월드 좌표로 보낸다. 다른 트윈은 게이트웨이(§3-2)가 ENU로
  바꿔 주므로 영향이 없다. 송신기 자체를 ENU로 옮기는 계획은 `coordinate-contract.md` 부록에
  있고, Unity 씬과 함께 바꿔야 해서 1.x에서 한다.
- **트윈 → 로봇 명령.** 게이트웨이는 트윈으로 보내기만 한다. `unity_bridge.py`(UDP 15100,
  15110 → 15101, 15102)의 명령 형식은 Unity 코드에서 뽑아낸 것이고 `YAW_CALIB` 같은 Unity 전용
  명령이 있다. Gazebo에서 로봇을 움직이려면 이 형식을 그대로 보내야 한다. 장기적으로는 서버의
  MQTT 명령 경로(`hardware/schema/physical_command.proto`, `ai/interface-spec`)로 옮긴다.
- **5009 한 포트에 두 종류.** 장애물과 모션을 필드 유무로 가른다. 새 수신기도 같은 규칙을
  따라야 한다.
- **JSON Schema가 없는 송신 패킷.** 5009와 15201은 문서로만 정의돼 있다. 게이트웨이가
  내보내는 중립 엔티티에는 스키마가 있다.

## 4. 라이선스

모델과 모델 라이브러리의 라이선스는 [THIRD_PARTY_NOTICES.md](../../THIRD_PARTY_NOTICES.md)에
있다. Ultralytics와 FastSAM은 AGPL-3.0, UniDepth는 비상업(CC BY-NC 4.0)이다. 상업 배포라면
`grounding_dino`나 직접 만든 검출기를 쓰고, UniDepth를 쓰는 스크립트는 빼거나 다른 깊이
모델로 바꾼다.
