#!/usr/bin/env python3
"""
twin_gateway.py — 엔진 중립 트윈 게이트웨이 (1.0.3)
================================================================
지금 송신기(로봇 상태 중계 · 360 장애물 · Go1 탐지)는 Unity 가 받는 UDP 패킷을 보낸다.
이 게이트웨이는 같은 패킷을 받아 엔진 중립 모델(건물 기준 ENU)로 바꾼 뒤, 고른 트윈으로
내보낸다. 송신기는 받는 곳을 쉼표로 하나 더 주기만 하면 되고 코드는 그대로다.

    송신기 --UDP--> Unity                       (지금 그대로)
           \\--UDP--> twin_gateway --> Gazebo     (gz sim, 서비스 호출)
                                  \\--> 중립 JSON (UDP — 웹 3D · ROS 2 브리지 등)
                                  \\--> 모듈:클래스 (직접 만든 트윈)

받는 것 (형식: hardware/HW-interface/bridge-contract.md · multi-robot-contract.md)
  robots    15201  "ROBOT <node> <type> <id> <seq> <tms> <x> <z> <yaw> <vx> <vy> <wz> <estop> <mode>"
  anchor360 5010   360 장애물 JSON (v2 label·position·size_m, v1 name·pos3d·size 도 읽는다)
  go1       5009   Go1 탐지 JSON (detections · has_near_obstacle) 또는 모션 JSON (state_change · motion_active)
  Unity 와 같은 기기에서 돌리면 포트가 겹치므로 다른 포트로 받는다 (--listen, 송신기는 주소:포트).

좌표 (coordinate-contract.md §1 과 부록)
  Unity 월드 (x, z 수평, yaw = +Z 기준 시계 +, rad)  →  ENU (x 동, y 북, z 위, yaw = +x 기준 반시계 +, rad)
      enu_x = x,  enu_y = z,  enu_yaw = pi/2 - yaw
  360 장애물은 카메라 슬라이스 기준이다 (x 오른쪽, z 앞, m). 설정의 anchors 에 카메라 자리
  (x, y, z, heading_deg = 슬라이스 정면의 ENU 방위, +x 기준 반시계)를 주면 월드 좌표가 된다.
  기본값 heading_deg 90 은 Unity 수신기의 기본(yawOffsetDeg 0)과 같은 배치다.

중립 엔티티 (hardware/HW-interface/twin-entity.schema.json)
  {"op": "upsert"|"remove", "id", "kind": "robot"|"obstacle", "label", "source",
   "pose": {"x","y","z","yaw"}, "size": {"x","y","z"}, "attrs": {...}, "ts"}
  Go1 탐지·모션은 위치가 없으므로 그 로봇의 attrs 로 붙인다 (op "attrs").

  python twin_gateway.py --config twin.example.json
  python twin_gateway.py --sink gazebo:empty --sink udp:127.0.0.1:25500 --listen robots=25201 anchor360=25010
"""
import argparse
import importlib
import json
import math
import selectors
import socket
import subprocess
import sys
import threading
import time

DEFAULT_LISTEN = {"robots": 15201, "anchor360": 5010, "go1": 5009}
DEFAULT_ANCHOR = {"x": 0.0, "y": 0.0, "heading_deg": 90.0}
STATE_FIELDS = ("tag", "node", "type", "robot_id", "seq", "tms", "x", "z", "yaw",
                "vx", "vy", "wz", "estop", "mode")


def unity_to_enu(x, z, yaw):
    """Unity 월드 (x, z, 시계+ yaw) → ENU (x, y, 반시계+ yaw). coordinate-contract.md 부록의 식을 거꾸로."""
    return x, z, math.atan2(math.sin(math.pi / 2 - yaw), math.cos(math.pi / 2 - yaw))


def slice_to_enu(px, pz, anchor):
    """360 슬라이스 기준 (x 오른쪽, z 앞) → ENU. 앞 = heading, 오른쪽 = heading - 90도."""
    h = math.radians(float(anchor.get("heading_deg", 90.0)))
    fx, fy = math.cos(h), math.sin(h)
    rx, ry = math.sin(h), -math.cos(h)
    return (float(anchor.get("x", 0.0)) + px * rx + pz * fx,
            float(anchor.get("y", 0.0)) + px * ry + pz * fy)


# ---------------------------------------------------------------- 패킷 → 중립 엔티티
class Normalizer:
    def __init__(self, anchors):
        self.anchors = anchors or {}
        self.last_obstacles = {}          # 출처 → 지난번 장애물 id 들 (스냅샷이므로 사라진 것은 지운다)

    def robots(self, text):
        parts = text.split()
        if len(parts) != len(STATE_FIELDS) or parts[0] != "ROBOT":
            return []
        d = dict(zip(STATE_FIELDS, parts))
        try:
            x, y, yaw = unity_to_enu(float(d["x"]), float(d["z"]), float(d["yaw"]))
            attrs = {"vx": float(d["vx"]), "vy": float(d["vy"]), "wz": -float(d["wz"]),
                     "estop": d["estop"] == "1", "mode": int(d["mode"]), "seq": int(d["seq"])}
        except ValueError:
            return []
        rid = "robot_%s_%s_%s" % (d["node"], d["type"], d["robot_id"])
        return [{"op": "upsert", "id": rid, "kind": "robot", "label": d["type"], "source": d["node"],
                 "pose": {"x": x, "y": y, "z": 0.0, "yaw": yaw},
                 "size": {"x": 0.65, "y": 0.3, "z": 0.4}, "attrs": attrs, "ts": time.time()}]

    def anchor360(self, obj):
        src = str(obj.get("camera_id") or obj.get("source_id") or "anchor360")
        anchor = self.anchors.get(src) or self.anchors.get("default") or DEFAULT_ANCHOR
        out, seen = [], set()
        for i, d in enumerate(obj.get("detections") or [], 1):
            pos = d.get("position") if isinstance(d.get("position"), dict) and d.get("label") else d.get("pos3d")
            if not isinstance(pos, dict):
                continue
            size = d.get("size_m") if d.get("label") else d.get("size")
            size = size if isinstance(size, dict) else {}
            ex, ey = slice_to_enu(float(pos.get("x", 0)), float(pos.get("z", 0)), anchor)
            eid = "obs_%s_%d" % (src, int(d.get("id", i)))
            seen.add(eid)
            w = float(size.get("w", 0.3) or 0.3)
            h = float(size.get("h", 0.3) or 0.3)
            out.append({"op": "upsert", "id": eid, "kind": "obstacle",
                        "label": str(d.get("label") or d.get("name") or "?"), "source": src,
                        "pose": {"x": ex, "y": ey, "z": h / 2, "yaw": 0.0},          # 바닥 위에 놓는다
                        "size": {"x": w, "y": float(size.get("d", w) or w), "z": h},
                        "attrs": {"confidence": d.get("confidence", d.get("conf")),
                                  "group": d.get("group")}, "ts": time.time()})
        for gone in self.last_obstacles.get(src, set()) - seen:
            out.append({"op": "remove", "id": gone})
        self.last_obstacles[src] = seen
        return out

    def go1(self, obj):
        if "state_change" in obj and "motion_active" in obj and "detections" not in obj:
            attrs = {"moving": bool(obj.get("state_change")), "motion_source": obj.get("source")}
        else:
            attrs = {"near_obstacle": bool(obj.get("has_near_obstacle")),
                     "detections": [{k: d.get(k) for k in ("name", "distance_cm", "risk_level")}
                                    for d in obj.get("detections") or []]}
        return [{"op": "attrs", "source": str(obj.get("camera_id") or obj.get("source") or "go1"),
                 "attrs": attrs, "ts": time.time()}]


# ---------------------------------------------------------------- 내보내기 (sink)
class UdpSink:
    """중립 엔티티를 JSON 한 줄씩 UDP 로. 웹 3D 뷰어, ROS 2 브리지 등이 받는다."""

    def __init__(self, dest):
        host, _, port = dest.rpartition(":")
        self.dest = (host or "127.0.0.1", int(port))
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    def handle(self, ent):
        self.sock.sendto(json.dumps(ent, ensure_ascii=False).encode("utf-8"), self.dest)


class GazeboSink:
    """gz sim (Harmonic 이상) 에 모델을 만들고 옮긴다. gz CLI 서비스 호출이라 별도 파이썬 바인딩이 필요 없다.
    틱(1/max_hz 초)마다 쌓인 것을 한꺼번에 보낸다 — 새 모델은 create_multiple 한 번, 옮길 것은 set_pose_vector
    한 번. 엔티티마다 gz 를 부르면 호출 하나(프로세스 하나, ~0.3 s)가 갱신을 못 따라가 시간 초과가 쌓인다
    (2026-10-27 실측: 10 Hz 로봇 + 360 장애물). 호출은 별도 스레드에서 한다 (UDP 받기를 막지 않는다)."""

    COLORS = {"robot": "0 0.4 1 1", "obstacle": "1 0.5 0 1"}

    def __init__(self, world="empty", gz="gz", max_hz=5.0, timeout_ms=2000):
        self.world, self.gz, self.gap, self.timeout = world, gz, 1.0 / max_hz, str(timeout_ms)
        self.created = set()
        self.pending = {}                           # id → 가장 최근 엔티티 (같은 엔티티는 마지막 것만 남는다)
        self.lock = threading.Lock()
        threading.Thread(target=self._run, daemon=True).start()

    def _call(self, service, reqtype, req):
        cmd = [self.gz, "service", "-s", "/world/%s/%s" % (self.world, service), "--reqtype", reqtype,
               "--reptype", "gz.msgs.Boolean", "--timeout", self.timeout, "--req", req]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True)
        except OSError as e:                        # gz 가 PATH 에 없음 등 — 스레드를 죽이지 않고 알린다
            print("[gazebo] %s 실패: gz 를 실행하지 못함 (%s)" % (service, e), flush=True)
            return False
        ok = r.returncode == 0 and "data: true" in r.stdout
        if not ok:
            print("[gazebo] %s 실패: %s %s" % (service, r.stdout.strip()[:120], r.stderr.strip()[:120]), flush=True)
        return ok

    @staticmethod
    def _pose(p):
        yaw = float(p.get("yaw", 0.0))
        return ("position {x: %.4f y: %.4f z: %.4f} orientation {x: 0 y: 0 z: %.6f w: %.6f}"
                % (p["x"], p["y"], p.get("z", 0.0), math.sin(yaw / 2), math.cos(yaw / 2)))

    def _sdf(self, ent):
        s = ent.get("size") or {}
        size = "%.3f %.3f %.3f" % (max(float(s.get("x", 0.3)), 0.05), max(float(s.get("y", 0.3)), 0.05),
                                   max(float(s.get("z", 0.3)), 0.05))
        color = self.COLORS.get(ent.get("kind"), "0.7 0.7 0.7 1")
        return ("<sdf version='1.9'><model name='%s'><static>true</static><link name='body'>"
                "<visual name='v'><geometry><box><size>%s</size></box></geometry>"
                "<material><ambient>%s</ambient><diffuse>%s</diffuse></material></visual>"
                "</link></model></sdf>" % (ent["id"], size, color, color))

    def handle(self, ent):
        if ent["op"] == "attrs":
            return
        with self.lock:
            self.pending[ent["id"]] = ent

    def _retry(self, ents):
        """실패한 것은 다음 틱에 다시 — 그사이 더 새 것이 왔으면 그것이 이긴다."""
        with self.lock:
            for e in ents:
                self.pending.setdefault(e["id"], e)

    def _run(self):
        while True:
            t0 = time.time()
            with self.lock:
                batch, self.pending = self.pending, {}
            for e in batch.values():
                if e["op"] == "remove" and e["id"] in self.created:
                    if self._call("remove", "gz.msgs.Entity", 'name: "%s" type: MODEL' % e["id"]):
                        self.created.discard(e["id"])
            ups = [e for e in batch.values() if e["op"] == "upsert"]
            new = [e for e in ups if e["id"] not in self.created]
            moved = [e for e in ups if e["id"] in self.created]
            if new:
                req = " ".join('data {sdf: "%s" name: "%s" pose {%s}}'
                               % (self._sdf(e).replace('"', '\\"'), e["id"], self._pose(e["pose"])) for e in new)
                if self._call("create_multiple", "gz.msgs.EntityFactory_V", req):
                    self.created.update(e["id"] for e in new)
                else:
                    self._retry(new)
            if moved:
                req = " ".join('pose {name: "%s" %s}' % (e["id"], self._pose(e["pose"])) for e in moved)
                if not self._call("set_pose_vector", "gz.msgs.Pose_V", req):
                    self._retry(moved)
            wait = self.gap - (time.time() - t0)
            if wait > 0:
                time.sleep(wait)


def make_sink(spec):
    """'gazebo[:world]' | 'udp:host:port' | 'stdout' | '모듈:클래스[=인자]' 또는 설정의 사전."""
    if isinstance(spec, dict):
        t = spec.get("type")
        if t == "gazebo":
            return GazeboSink(spec.get("world", "empty"), spec.get("gz", "gz"), float(spec.get("max_hz", 5.0)))
        if t == "udp":
            return UdpSink(spec["dest"])
        if t == "stdout":
            return StdoutSink()
        if t == "class":
            mod, name = spec["class"].split(":", 1)
            return getattr(importlib.import_module(mod), name)(**(spec.get("args") or {}))
        raise SystemExit("모르는 sink: %r" % spec)
    kind, _, rest = spec.partition(":")
    if kind == "gazebo":
        return GazeboSink(rest or "empty")
    if kind == "udp":
        return UdpSink(rest)
    if kind == "stdout":
        return StdoutSink()
    if ":" in spec:
        mod, name = spec.split(":", 1)
        return getattr(importlib.import_module(mod), name)()
    raise SystemExit("모르는 sink: %s (gazebo[:월드] | udp:주소:포트 | stdout | 모듈:클래스)" % spec)


class StdoutSink:
    def handle(self, ent):
        print(json.dumps(ent, ensure_ascii=False), flush=True)


# ---------------------------------------------------------------- 실행
def main():
    ap = argparse.ArgumentParser(description="트윈 패킷 → 엔진 중립 모델 → Gazebo · UDP JSON · 직접 만든 트윈")
    ap.add_argument("--config", help="JSON 설정 (listen · anchors · sinks). 명령행이 더해진다")
    ap.add_argument("--listen", nargs="+", default=[], metavar="종류=포트",
                    help="받을 포트: robots=15201 anchor360=5010 go1=5009 (기본 이 셋)")
    ap.add_argument("--bind", default="0.0.0.0")
    ap.add_argument("--sink", action="append", default=[],
                    help="gazebo[:월드] | udp:주소:포트 | stdout | 모듈:클래스. 여러 번")
    a = ap.parse_args()

    cfg = {}
    if a.config:
        with open(a.config, encoding="utf-8") as f:
            cfg = json.load(f)
    listen = dict(DEFAULT_LISTEN, **(cfg.get("listen") or {}))
    for item in a.listen:
        k, _, v = item.partition("=")
        if k not in DEFAULT_LISTEN:
            raise SystemExit("모르는 종류: %s (robots · anchor360 · go1)" % k)
        listen[k] = int(v)
    sinks = [make_sink(s) for s in (cfg.get("sinks") or [])] + [make_sink(s) for s in a.sink]
    if not sinks:
        sinks = [StdoutSink()]
    norm = Normalizer(cfg.get("anchors"))

    sel = selectors.DefaultSelector()
    for kind, port in listen.items():
        if not port:
            continue
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.bind((a.bind, int(port)))
        sel.register(s, selectors.EVENT_READ, kind)
    print("[twin] 받기 %s → %s" % (", ".join("%s:%s" % kv for kv in listen.items() if kv[1]),
                                   ", ".join(type(x).__name__ for x in sinks)), flush=True)
    while True:
        for key, _ in sel.select():
            data, _src = key.fileobj.recvfrom(65535)
            text = data.decode("utf-8", "replace").strip()
            try:
                if key.data == "robots":
                    ents = norm.robots(text)
                else:
                    obj = json.loads(text)
                    ents = norm.anchor360(obj) if key.data == "anchor360" else norm.go1(obj)
            except (ValueError, TypeError, AttributeError) as e:
                print("[twin] %s 패킷을 못 읽음: %s" % (key.data, e), flush=True)
                continue
            for ent in ents:
                for sk in sinks:
                    try:
                        sk.handle(ent)
                    except Exception as e:          # 한 트윈이 실패해도 다른 트윈은 계속 받는다
                        print("[twin] %s 실패: %s" % (type(sk).__name__, e), flush=True)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
