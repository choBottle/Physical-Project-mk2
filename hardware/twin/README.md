# 트윈 게이트웨이 — Unity 밖의 디지털 트윈 (Gazebo 등)

`twin_gateway.py`는 Unity가 받는 트윈 패킷을 그대로 받아 엔진 중립 모델(건물 기준 ENU)로
바꾼 뒤 다른 트윈으로 내보낸다. 송신기 코드는 바꾸지 않는다. 받는 곳을 쉼표로 하나 더 준다.

```
송신기 ──UDP──> Unity                          (지금 그대로)
       └─UDP──> twin_gateway ──> Gazebo        (gz sim 서비스: create · set_pose · remove)
                             ├─> 중립 JSON UDP (웹 3D 뷰어, ROS 2 브리지 등)
                             └─> 모듈:클래스   (직접 만든 트윈)
```

## 실행

Gazebo Harmonic(gz sim 8) 이상이 같은 기기에 있어야 한다. 파이썬 패키지는 표준 라이브러리만 쓴다.

```
gz sim -r empty.sdf                       # 또는 쓰는 월드. 월드 이름을 --sink gazebo:<월드> 로
python3 hardware/twin/twin_gateway.py --config hardware/twin/twin.example.json
```

송신기 쪽 (Unity와 게이트웨이에 같이 보낸다):

```
robot_state_relay.py --unity_ip <unity-pc>,<gateway-pc>:25201
anchor360_live.py   --unity-ip <unity-pc>,<gateway-pc>:25010
HW_UNITY_IP=<unity-pc>,<gateway-pc>:25009          # go1_detect_forward, /etc/hw-robot.env
```

Unity가 없으면 게이트웨이 주소만 준다. 게이트웨이를 기본 포트(15201, 5010, 5009)로 띄우면
송신기 기본 포트를 그대로 쓸 수 있다.

## 무엇이 어떻게 바뀌나

| 받는 것 | 트윈에 나타나는 것 |
|---------|-------------------|
| 로봇 상태 15201 | `robot_<node>_<type>_<id>` 모델, ENU 위치와 방향 |
| 360 장애물 5010 | `obs_<source>_<id>` 상자 (크기 = `size_m`). 다음 패킷에 없으면 지운다 |
| Go1 탐지·모션 5009 | 위치가 없어 모델은 만들지 않는다. 중립 JSON의 `op: attrs`로 내보낸다 |

좌표: Unity 월드 `(x, z, yaw 시계+)` → ENU `(x, z, π/2 − yaw)`. 360 장애물은 카메라 슬라이스
기준이라 설정의 `anchors`에 카메라 자리(`x`, `y`, `heading_deg`)를 준다. 기본값
`heading_deg: 90`은 Unity 수신기의 기본 배치와 같다. 중립 엔티티 형식은
[`../HW-interface/twin-entity.schema.json`](../HW-interface/twin-entity.schema.json).

## 다른 트윈 붙이기

`handle(entity)` 메서드 하나를 가진 클래스를 만들고 `--sink 모듈:클래스`로 준다. 엔티티는
위 스키마를 따른다. ROS 2는 중립 JSON UDP를 받아 `tf2`나 `visualization_msgs/MarkerArray`로
내보내는 노드를 두면 된다.

## 확인 (2026-10-27)

`ros:jazzy` + Gazebo Harmonic(gz sim 8.11) 컨테이너에서 headless `gz sim -s empty.sdf`에 붙였다.

- 로봇 상태 한 줄 → `robot_pi7_go1_0`이 ENU (1, 2), yaw π/2(Unity yaw 0 = 북)에 생긴다.
- 360 장애물 두 개 → `obs_anchor360-live_1`, `_2`가 생기고 의자가 (1, 3, 0.4)에 놓인다.
- 로봇 상태 10줄을 30 ms 간격으로 → 마지막 자세 (4, 2), yaw 0(Unity yaw π/2 = 동)으로 옮겨진다.
- 상자가 빠진 360 스냅샷 → `obs_anchor360-live_2`가 지워진다.

## 아직 안 되는 것

- **트윈 → 로봇 명령.** Gazebo에서 로봇을 움직이는 경로는 없다. 명령은 지금도 Unity의
  `unity_bridge.py` 형식(UDP 15100·15110)이다. 서버의 MQTT 명령 경로로 옮기는 것이 1.x 로드맵이다.
- **송신기는 아직 Unity 좌표로 보낸다.** 게이트웨이가 바꿔 주므로 트윈 쪽은 ENU만 보면 된다.
  송신기를 ENU로 바꾸는 것은 Unity 씬과 함께 바꿔야 해서 1.x에서 한다.
