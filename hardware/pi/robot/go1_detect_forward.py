# -*- coding: utf-8 -*-
"""
피지컬팀 mk2 — 인지 결과 → 디지털 트윈 포워더 (HW-R-07)
==========================================================
인지 서버의 탐지 결과를 Unity 디지털 트윈의 장애물 수신 포트로 밀어 넣는다.

    서버 GET /control/<camera_id>  ──폴링──►  pi1  ──UDP 5009──►  Unity

`robot/go1_front_upload.py` 가 올린 프레임을 서버가 인지해 내놓은 결과를 되받는 것이라
둘은 한 쌍이다. 업로더가 안 돌면 여기도 빈 detections 만 받는다.

## 왜 변환하지 않고 그대로 보내는가

Unity `Go1ObstacleJsonReceiver.Go1ObstaclePacket` 의 필드가 서버 응답과 이미 같다
(`timestamp`, `camera_id`, `detections[]`, `has_near_obstacle`, 그리고 detection 의
`id/name/group/rel_depth/distance_cm/distance_cm_raw/risk_level/bbox_xyxy`).
중간에서 모양을 바꾸면 한쪽이 필드를 늘릴 때 조용히 깨지므로 **바이트를 그대로 넘긴다.**

## 5009 에는 두 종류가 섞여 들어온다

같은 포트로 브리지(`go1_sdk_pc`)의 이동상태 JSON 도 들어온다. 수신기는 `state_change` 와
`motion_active` 가 **둘 다** 있을 때만 이동상태로 보고, 서버 응답에는 `motion_active` 가
없으므로 장애물로 처리된다. 그래서 서버 payload 를 손대지 않아도 충돌하지 않는다.

## 같은 프레임을 두 번 보내지 않는다

수신기가 `timestamp` 로 중복을 거르지만, 그 전에 무선 구간을 낭비할 이유가 없다.
timestamp 가 그대로면 보내지 않는다.

사용:
    cd ~/hw/pi && HW_DETECT_BASE=http://<server-ip>:7864 \\
        python3 -m robot.go1_detect_forward --unity-ip <unity-ip>
"""
import argparse
import json
import os
import socket
import sys
import time
import urllib.request

# 인지 서버 주소. 기관마다 다르므로 저장소에는 로컬 기본값만 둔다.
# 실제 주소는 HW_DETECT_BASE(또는 --base)로 준다 — systemd 는 /etc/hw-robot.env.
DEFAULT_BASE = "http://127.0.0.1:7864"
UNITY_OBSTACLE_PORT = 5009


def parse_dests(hosts, default_port):
    """"a,b:6000" → [("a", 기본포트), ("b", 6000)]. 트윈(Unity 등)을 여러 곳에 동시에 보낼 때 쉼표로 잇는다."""
    out = []
    for h in str(hosts).split(","):
        h = h.strip()
        if not h:
            continue
        host, _, port = h.rpartition(":") if h.count(":") == 1 else (h, "", "")
        out.append((host, int(port)) if port else (h, int(default_port)))
    return out


def run(base, camera_id, unity_ip, unity_port, hz, verbose):
    url = "%s/control/%s" % (base.rstrip("/"), camera_id)
    tx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    dests = parse_dests(unity_ip, unity_port)
    period = 1.0 / max(hz, 0.1)

    polled = sent = skipped = failed = 0
    last_ts = None
    last_log = time.time()
    last_error = ""
    last_dets = 0

    print("[init] %s -> udp %s  %.1fHz" % (url, ", ".join("%s:%d" % d for d in dests), hz), flush=True)

    while True:
        t0 = time.time()
        try:
            with urllib.request.urlopen(url, timeout=3) as r:
                raw = r.read()
            polled += 1

            try:
                obj = json.loads(raw.decode("utf-8"))
            except Exception:
                obj = {}

            ts = obj.get("timestamp")
            if ts is not None and ts == last_ts:
                skipped += 1
            else:
                last_ts = ts
                last_dets = len(obj.get("detections") or [])
                # 서버 payload 를 그대로 — 모양을 바꾸지 않는다.
                for dst in dests:
                    tx.sendto(raw, dst)
                sent += 1
        except Exception as e:
            failed += 1
            last_error = type(e).__name__ + ": " + str(e)[:60]

        if verbose and time.time() - last_log >= 5.0:
            last_log = time.time()
            print("[fwd] 폴링 %d  전송 %d  중복생략 %d  실패 %d  최근탐지 %d개  %s"
                  % (polled, sent, skipped, failed, last_dets, last_error), flush=True)

        wait = period - (time.time() - t0)
        if wait > 0:
            time.sleep(wait)


def main():
    ap = argparse.ArgumentParser(description="인지 서버 탐지 결과 -> Unity 5009")
    ap.add_argument("--base", default=os.environ.get("HW_DETECT_BASE") or DEFAULT_BASE)
    ap.add_argument("--camera-id", default=os.environ.get("HW_UPLOAD_CAMERA_ID", "go1_front"))
    ap.add_argument("--unity-ip", default=os.environ.get("HW_UNITY_IP", "192.168.50.244"),
                    help="받는 곳. 쉼표로 여러 곳, 곳마다 :포트 가능 (Unity 와 다른 뷰어를 같이)")
    ap.add_argument("--unity-port", type=int, default=UNITY_OBSTACLE_PORT)
    ap.add_argument("--hz", type=float, default=float(os.environ.get("HW_DETECT_HZ", "10")))
    ap.add_argument("-q", "--quiet", action="store_true")
    a = ap.parse_args()
    if a.base == DEFAULT_BASE and not os.environ.get("HW_DETECT_BASE"):
        print("[warn] HW_DETECT_BASE 미설정: %s 를 본다. 인지 서버가 다른 기기면 /etc/hw-robot.env 에 "
              "HW_DETECT_BASE=http://<server>:7864 를 넣는다 (없으면 Unity 5009 에 장애물이 안 간다)"
              % DEFAULT_BASE, flush=True)
    run(a.base, a.camera_id, a.unity_ip, a.unity_port, a.hz, not a.quiet)


if __name__ == "__main__":
    main()
