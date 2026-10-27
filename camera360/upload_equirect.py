"""
upload_equirect.py — 어느 360 카메라든 equirect 이미지를 서버로 올린다
================================================================
stream_to_server.py 는 Insta360 Pro2 를 제어(연결·프리뷰 시작)하는 송신기다. 다른 360 카메라
(Ricoh Theta, GoPro Max, Insta360 X 시리즈, 직접 이어 붙인 리그 등)는 이 스크립트로 올린다.
서버 쪽(pano_receiver.py 7866, server_stream_multi_source.py 10001, anchor360_live.py)은
equirect JPEG 만 받으므로 카메라 종류를 모른다.

입력 (셋 중 하나)
  파일·글롭       upload_equirect.py pano1.jpg pano2.jpg            한 장씩 올리고 끝낸다
  폴더 감시       upload_equirect.py --watch ./out                   새로 생긴 *.jpg 를 올린다
  스트림          upload_equirect.py --stream rtsp://<camera>/live   RTSP·RTMP·HTTP·장치 번호(0, 1…)

올리는 꼴 (stream_to_server.py 와 같다)
  POST multipart/form-data
    file        equirect.jpg (image/jpeg)
    capture_id  저장 폴더 이름 (--capture-id, 기본 LIVE_STREAM)
    camera_id   (--camera-id, 기본 cam360-001_main)
    meta        JSON: schema_version "2.0", source_id, node_id, zone_id, camera_id,
                sequence_id, session_id, timestamp(ISO 밀리초 +09:00), encoding, width, height

주소 (stream_to_server.py 와 같은 환경변수)
  MK2_UPLOAD_URL         기본 http://$MK2_SERVER_HOST:7866/upload_pano     (anchor360 줄)
  MK2_UPLOAD_STREAM_URL  기본 http://$MK2_SERVER_HOST:10001/upload_pano    (데이터 스트림 줄)
  --url 을 여러 번 주면 그 주소들로 보낸다. 안 주면 위 두 곳 모두.

카메라 조건
  - 가로 = 세로 × 2 인 equirect (2:1). 아니면 경고만 하고 올린다.
  - 수평 보정(horizon leveling)을 켠다. anchor360_live.py 는 카메라가 수평이라고 가정한다.
  - 설치 높이·하향각이 Pro2 와 다르면 anchor360_live.py --cam-h --pitch 로 맞춘다.
"""
import argparse
import glob
import json
import os
import socket
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone

import requests

SERVER_HOST = os.environ.get("MK2_SERVER_HOST", "127.0.0.1")
DEF_URLS = [os.environ.get("MK2_UPLOAD_URL", f"http://{SERVER_HOST}:7866/upload_pano"),
            os.environ.get("MK2_UPLOAD_STREAM_URL", f"http://{SERVER_HOST}:10001/upload_pano")]
KST = timezone(timedelta(hours=9))
SESSION_ID = uuid.uuid4().hex[:12]
NODE_ID = socket.gethostname()


def iso_ms(t):
    return datetime.fromtimestamp(t, KST).isoformat(timespec="milliseconds")


def jpeg_size(data):
    """JPEG 머리에서 (가로, 세로). 못 읽으면 (0, 0)."""
    i = 2
    while i + 9 < len(data):
        if data[i] != 0xFF:
            return 0, 0
        marker = data[i + 1]
        seg = int.from_bytes(data[i + 2:i + 4], "big")
        if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
            return int.from_bytes(data[i + 7:i + 9], "big"), int.from_bytes(data[i + 5:i + 7], "big")
        i += 2 + seg
    return 0, 0


class Uploader:
    def __init__(self, args):
        self.args = args
        self.urls = args.url or DEF_URLS
        self.sess = requests.Session()
        self.seq = 0
        self.warned_ratio = False

    def send(self, data, t_frame):
        a = self.args
        w, h = jpeg_size(data)
        if w and h and w != 2 * h and not self.warned_ratio:
            print("[warn] %dx%d: equirect(2:1)가 아니다. 카메라 출력 설정을 확인하세요" % (w, h))
            self.warned_ratio = True
        self.seq += 1
        meta = {"schema_version": "2.0", "source_id": a.source_id, "node_id": NODE_ID,
                "zone_id": a.zone_id, "camera_id": a.camera_id,
                "sequence_id": self.seq, "session_id": SESSION_ID,
                "timestamp": iso_ms(t_frame), "encoding": "jpeg", "width": w, "height": h}
        form = {"capture_id": a.capture_id, "camera_id": a.camera_id}
        files = {"file": ("equirect.jpg", data, "image/jpeg"),
                 "meta": (None, json.dumps(meta, ensure_ascii=False), "application/json")}
        result = []
        for url in self.urls:
            if a.dry_run:
                result.append("dry")
                continue
            try:
                r = self.sess.post(url, data=form, files=files, timeout=15)
                result.append("%d" % r.status_code)
            except requests.RequestException as e:
                result.append("ERR:%s" % type(e).__name__)
        print("#%d %dx%d %dKB → %s" % (self.seq, w, h, len(data) // 1024, " ".join(result)))


def run_files(up, paths):
    for p in paths:
        with open(p, "rb") as f:
            up.send(f.read(), os.path.getmtime(p))


def run_watch(up, folder, poll):
    """새로 생긴 *.jpg 만 올린다. 크기가 두 번 연속 같으면 다 쓴 것으로 본다."""
    seen = set(glob.glob(os.path.join(folder, "*.jpg")))
    pending = {}
    print("감시: %s (기존 %d장은 건너뜀)" % (folder, len(seen)))
    while True:
        for p in glob.glob(os.path.join(folder, "*.jpg")):
            if p in seen:
                continue
            size = os.path.getsize(p)
            if pending.get(p) == size and size > 0:
                seen.add(p)
                pending.pop(p)
                run_files(up, [p])
            else:
                pending[p] = size
        time.sleep(poll)


def run_stream(up, src, fps, quality):
    import cv2
    cap = cv2.VideoCapture(int(src) if src.isdigit() else src)
    if not cap.isOpened():
        sys.exit("스트림을 못 열었다: %s" % src)
    gap = 1.0 / fps
    last = 0.0
    while True:
        ok, frame = cap.read()
        if not ok:
            print("[warn] 프레임 없음, 다시 연결")
            cap.release()
            time.sleep(2)
            cap = cv2.VideoCapture(int(src) if src.isdigit() else src)
            continue
        now = time.time()
        if now - last < gap:
            continue
        last = now
        ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
        if ok:
            up.send(buf.tobytes(), now)


def main():
    ap = argparse.ArgumentParser(description="equirect 이미지를 MK2 360 입구로 올린다 (카메라 무관)")
    ap.add_argument("files", nargs="*", help="올릴 JPEG 파일 (글롭 가능)")
    ap.add_argument("--watch", metavar="DIR", help="이 폴더에 새로 생기는 *.jpg 를 올린다")
    ap.add_argument("--stream", metavar="URL", help="RTSP/RTMP/HTTP 주소 또는 장치 번호")
    ap.add_argument("--fps", type=float, default=2.0, help="--stream 에서 올리는 장 수/초 (기본 2)")
    ap.add_argument("--quality", type=int, default=90, help="--stream JPEG 품질 (기본 90)")
    ap.add_argument("--poll", type=float, default=0.5, help="--watch 감시 주기(초)")
    ap.add_argument("--url", action="append", help="업로드 주소. 여러 번 줄 수 있다")
    ap.add_argument("--capture-id", default="LIVE_STREAM")
    ap.add_argument("--camera-id", default=os.environ.get("MK2_CAMERA_ID", "cam360-001_main"))
    ap.add_argument("--source-id", default=os.environ.get("MK2_SOURCE_ID", "cam360-001"))
    ap.add_argument("--zone-id", default=os.environ.get("MK2_ZONE_ID", "zoneA"))
    ap.add_argument("--dry-run", action="store_true", help="보내지 않고 출력만")
    args = ap.parse_args()

    modes = sum(bool(x) for x in (args.files, args.watch, args.stream))
    if modes != 1:
        ap.error("파일, --watch, --stream 중 하나만 준다")
    up = Uploader(args)
    print("보낼 곳: %s" % ", ".join(up.urls))
    try:
        if args.files:
            paths = [p for pat in args.files for p in (sorted(glob.glob(pat)) or [pat])]
            run_files(up, paths)
        elif args.watch:
            run_watch(up, args.watch, args.poll)
        else:
            run_stream(up, args.stream, args.fps, args.quality)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
