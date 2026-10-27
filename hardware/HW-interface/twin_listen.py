"""
twin_listen.py — Unity 대신 트윈 패킷을 받아 보는 참조 수신기
================================================================
Unity 디지털 트윈이 받는 UDP 패킷을 그대로 받아 풀어서 찍는다. Unity 가 아닌 다른
뷰어(웹 3D, Unreal, ROS 2 브리지 등)를 붙이려는 쪽은 이 파일을 출발점으로 쓴다.
보내는 쪽은 바꿀 필요가 없다 — 받는 곳을 쉼표로 하나 더 주면 Unity 와 이 수신기가
같은 패킷을 받는다.

  anchor360_live.py   --unity-ip <unity-pc>,<this-pc>         (또는 MK2_TWIN_HOSTS)
  go1_detect_forward  HW_UNITY_IP=<unity-pc>,<this-pc>        (/etc/hw-robot.env)
  robot_state_relay   --unity_ip <unity-pc>,<this-pc>

받는 것 (형식은 bridge-contract.md · multi-robot-contract.md · coordinate-contract.md)
  5010   360 장애물      JSON, 통합데이터규약 v2 (server/contracts/common/detections.schema.json)
  5009   Go1 장애물      JSON, 인지 서버 /control 응답 그대로 (detections 가 있다)
         Go1 모션        JSON, state_change 와 motion_active 가 둘 다 있으면 모션
  15201  로봇 상태       텍스트 한 줄 "ROBOT <node> <type> <id> <seq> <tms> <x> <z> <yaw> <vx> <vy> <wz> <estop> <mode>"

좌표: 지금 패킷은 Unity 월드 좌표다 (coordinate-contract.md §1 — x, z 수평 m, y 위,
로봇 yaw 는 +Z 기준 시계 방향 +, rad). 다른 엔진은 받는 쪽에서 자기 좌표로 바꾼다.
같은 문서 부록의 식을 거꾸로 쓰면 건물 기준 ENU 가 된다:
    enu_x = x,  enu_y = z,  enu_yaw = pi/2 - yaw     (반시계 +, +x 기준, rad)

  python twin_listen.py                       # 세 포트 모두
  python twin_listen.py --ports 5010 --raw    # 원문 그대로
"""
import argparse
import json
import selectors
import socket

STATE_FIELDS = ("tag", "node", "type", "robot_id", "seq", "tms", "x", "z", "yaw",
                "vx", "vy", "wz", "estop", "mode")


def describe(port, data):
    text = data.decode("utf-8", "replace").strip()
    if port == 15201 or text.startswith("ROBOT "):
        parts = text.split()
        if len(parts) != len(STATE_FIELDS):
            return "state ?  %s" % text
        d = dict(zip(STATE_FIELDS, parts))
        return "state  %s/%s#%s  x=%s z=%s yaw=%s mode=%s" % (
            d["node"], d["type"], d["robot_id"], d["x"], d["z"], d["yaw"], d["mode"])
    try:
        obj = json.loads(text)
    except ValueError:
        return "text   %s" % text[:120]
    if "state_change" in obj and "motion_active" in obj:
        return "motion %s" % {k: obj[k] for k in ("state_change", "motion_active") if k in obj}
    dets = obj.get("detections") or []
    names = []
    for d in dets:
        name = d.get("label") or d.get("name") or "?"
        pos = d.get("position") or d.get("pos3d") or {}
        if isinstance(pos, dict) and "x" in pos:
            names.append("%s(%.2f,%.2f)" % (name, float(pos.get("x", 0)), float(pos.get("z", 0))))
        else:
            names.append(name)
    head = obj.get("schema_version", "v1")
    return "detect v%s %s %d개 %s" % (head, obj.get("source_id") or obj.get("camera_id") or "",
                                     len(dets), " ".join(names[:8]))


def main():
    ap = argparse.ArgumentParser(description="트윈 UDP 패킷 참조 수신기")
    ap.add_argument("--bind", default="0.0.0.0")
    ap.add_argument("--ports", type=int, nargs="+", default=[5010, 5009, 15201])
    ap.add_argument("--raw", action="store_true", help="원문 그대로 찍는다")
    a = ap.parse_args()

    sel = selectors.DefaultSelector()
    for p in a.ports:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.bind((a.bind, p))
        sel.register(s, selectors.EVENT_READ, p)
    print("받는 중: %s" % ", ".join("udp %s:%d" % (a.bind, p) for p in a.ports), flush=True)
    try:
        while True:
            for key, _ in sel.select():
                data, src = key.fileobj.recvfrom(65535)
                line = data.decode("utf-8", "replace") if a.raw else describe(key.data, data)
                print("[%d ← %s] %s" % (key.data, src[0], line), flush=True)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
