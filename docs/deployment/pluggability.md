# 바꿔 끼우기 — 360 카메라, 검출 모델, 디지털 트윈

이 플랫폼은 특정 제품에 묶이지 않는 것을 목표로 한다. 이 문서는 외부 기관이 다른 카메라,
다른 모델, Unity가 아닌 트윈을 쓸 때 **어디까지 설정만으로 되고 어디부터 코드가 필요한지**를
적는다. 2026-10-27 기준 코드를 확인한 결과다.

| 바꾸려는 것 | 지금 | 방법 |
|-------------|------|------|
| 360 카메라 (Insta360 Pro2 → 다른 기종) | 설정만으로 된다 | `camera360/upload_equirect.py` |
| 360 검출 모델 (YOLO-World → 다른 모델) | 설정만으로 된다 | config의 `backend` 한 줄 |
| AI 프레임워크 provider | 설정 파일 + 함수 하나 | `ai/perception-framework` 의 `model_config` |
| 트윈 추가 (Unity와 함께 다른 뷰어) | 설정만으로 된다 | 받는 곳을 쉼표로 추가 |
| 트윈 교체 (Unity 없이) | 받는 쪽 코드 필요, 보내는 쪽은 그대로 | `hardware/HW-interface/twin_listen.py` 참고 |
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

아직 고정된 것: `server_stream_multi_source.py`의 소스 목록(cam360 10001, drone 10002,
robot1 10003, robot2 10004)은 코드에 있다. 다섯 번째 소스는 `SOURCES`와 끌어오는 방식을
코드에서 추가해야 한다. 360 카메라를 바꾸는 데는 영향이 없다(10001로 올리면 된다).

## 2. 검출 모델

### 2-1. camera360

검출기는 `camera360/detectors.py`의 `make_detector()`로 만든다. `anchor360_live.py`,
`detect_send_3b2.py`, `detect_send_3b2_timed.py`, `detect_ground_3b1.py`가 이 함수를 쓴다.
모델은 `unidepth_dual_yolo_config.yaml`에서 고른다.

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

아직 고정된 것: `unidepth_dual_yolo.py`(파인튜닝 YOLO + YOLO-World + UniDepth)와
`vision_infer.py`(YOLOE)는 이 교체점을 쓰지 않는다.

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

### 3-2. 패킷 형식과 좌표

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

### 3-3. 아직 Unity에 묶인 것 (1.x 로드맵)

- **좌표 규약.** 송신기가 Unity 월드 좌표로 보낸다. 트윈을 바꿔도 로봇 코드는 안 바뀌게
  건물 기준 ENU로 옮기는 계획이 `coordinate-contract.md` 부록에 있다. 지금 바꾸면 현재
  Unity 씬이 깨지므로 1.0에서는 하지 않는다.
- **로봇 명령 경로.** `unity_bridge.py`(UDP 15100, 15110 → 15101, 15102)의 명령 형식은
  Unity 코드에서 뽑아낸 것이고 `YAW_CALIB` 같은 Unity 전용 명령이 있다. 다른 트윈에서
  로봇을 움직이려면 이 형식을 그대로 보내야 한다. 장기적으로는 서버의 MQTT 명령 경로
  (`hardware/schema/physical_command.proto`, `ai/interface-spec`)로 옮긴다.
- **5009 한 포트에 두 종류.** 장애물과 모션을 필드 유무로 가른다. 새 수신기도 같은 규칙을
  따라야 한다.
- **JSON Schema가 없는 패킷.** 5009와 15201은 문서로만 정의돼 있다.

## 4. 라이선스

모델과 모델 라이브러리의 라이선스는 [THIRD_PARTY_NOTICES.md](../../THIRD_PARTY_NOTICES.md)에
있다. Ultralytics와 FastSAM은 AGPL-3.0, UniDepth는 비상업(CC BY-NC 4.0)이다. 상업 배포라면
`grounding_dino`나 직접 만든 검출기를 쓰고, UniDepth를 쓰는 스크립트는 빼거나 다른 깊이
모델로 바꾼다.
