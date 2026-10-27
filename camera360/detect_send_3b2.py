"""
detect_send_3b2.py — 3b-② 360 사각지대 장애물 → JSON → UDP 송출
슬라이스 검출 → 필터(HARD_OBSTACLE/AGENT + 바닥접지) → NMS → 바닥평면 pos3d + size
→ JSON(frame:"anchor360", 스냅샷 전체) → UDP 송출 + JSON 파일 저장

사용:
  python3 detect_send_3b2.py <슬라이스> <config.yaml> [imgsz] [cam_h] [pitch] [unity_ip] [port] [json_out]
예:
  python3 detect_send_3b2.py ~/capstone-db/image_server/pano_captures/sliced_test/360cam_u-60_v-35.jpg \
      ~/capstone-db/image_server/unidepth_dual_yolo_config.yaml 640 1.85 -35 192.168.50.246 5010 obstacles_360.json

좌표 규약(anchor360, Unity 전달용):
  +x=오른쪽, +z=카메라 정면(=맵 GO1 주행방향, u-60 슬라이스 정면), y=0(바닥). 단위 m.
  원점 = 카메라를 바닥에 수직 투영한 점. (높이는 Unity가 바닥으로 강제하므로 여기선 y=0)
  좌우/각도 미세보정은 Unity(invertX / yawOffsetDeg)에서. 서버는 원본 좌표만 보냄.
"""
import os, sys, math, json, time, socket, datetime, yaml, cv2
from detectors import backend_of, make_detector   # 검출기 교체점 (config models.zeroshot_detector.backend)

img_path = sys.argv[1]
cfg_path = sys.argv[2]
imgsz    = int(sys.argv[3])   if len(sys.argv) > 3 else 640
CAM_H    = float(sys.argv[4]) if len(sys.argv) > 4 else 1.85
PITCH    = float(sys.argv[5]) if len(sys.argv) > 5 else -35.0
UNITY_IP = sys.argv[6]        if len(sys.argv) > 6 else "192.168.50.246"
PORT     = int(sys.argv[7])   if len(sys.argv) > 7 else 5010
JSON_OUT = sys.argv[8]        if len(sys.argv) > 8 else "obstacles_360.json"

KEEP_GROUPS = {"HARD_OBSTACLE", "AGENT"}

CFG = yaml.safe_load(open(cfg_path, encoding="utf-8"))
# 상대 경로는 yaml 폴더 기준 (unidepth_dual_yolo._resolve_model_path 와 같은 규칙) — 없으면 문자열 그대로(모델 이름)
_w = os.path.expanduser(str(CFG["models"]["zeroshot_detector"]["weight"]))
_cand = os.path.join(os.path.dirname(os.path.abspath(cfg_path)), _w)
ZS_W    = _cand if (not os.path.isabs(_w) and os.path.exists(_cand)) else _w
ZS_CLS  = CFG["classes"]["zeroshot"]
ZS_CONF = float(CFG["models"]["zeroshot_detector"]["conf"])
GROUP   = CFG["group_mapping"]
CC      = CFG.get("class_conf", {}).get("zeroshot", {})
IOU     = float(CFG.get("fusion", {}).get("iou", 0.45))

def min_conf(name):
    return float(CC.get(name, CC.get("default", 0.0)))

img = cv2.imread(img_path)
if img is None:
    sys.exit(f"이미지 못 읽음: {img_path}")
H, W = img.shape[:2]
fx = fy = W / (2.0 * math.tan(math.radians(90) / 2.0))   # 720 → 360
cx, cy = W / 2.0, H / 2.0
th = math.radians(PITCH)
cos_t, sin_t = math.cos(th), math.sin(th)

def pixel_to_ground(px, py):
    dx = (px - cx) / fx
    dy = -(py - cy) / fy
    dz = 1.0
    wy = cos_t * dy + sin_t * dz
    wz = -sin_t * dy + cos_t * dz
    wx = dx
    if wy >= -1e-6:
        return None
    t = -CAM_H / wy
    return wx * t, wz * t     # (X, Z) 바닥좌표(m)

# --- 검출 + 필터 ---
model = make_detector(ZS_W, ZS_CLS, backend_of(CFG))
res = model.detect(img, ZS_CONF, imgsz)
raw = []
for cid, conf, (x1, y1, x2, y2) in res:
    name = ZS_CLS[cid] if cid < len(ZS_CLS) else f"cls{cid}"
    if conf < min_conf(name):
        continue
    grp = GROUP.get(name, "UNKNOWN_OBSTACLE")
    if grp not in KEEP_GROUPS:
        continue
    raw.append({"name": name, "group": grp, "conf": conf, "bbox": [x1, y1, x2, y2]})

# --- NMS ---
def iou(a, b):
    ax1, ay1, ax2, ay2 = a; bx1, by1, bx2, by2 = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0, ix2 - ix1), max(0, iy2 - iy1)
    inter = iw * ih
    ua = (ax2-ax1)*(ay2-ay1) + (bx2-bx1)*(by2-by1) - inter
    return inter / ua if ua > 0 else 0.0
raw.sort(key=lambda d: -d["conf"])
kept = []
for d in raw:
    if all(iou(d["bbox"], k["bbox"]) < IOU for k in kept):
        kept.append(d)

# --- pos3d + size → JSON ---
detections = []
for i, d in enumerate(kept, 1):
    x1, y1, x2, y2 = d["bbox"]
    bcx, bcy = (x1 + x2) / 2.0, y2
    g = pixel_to_ground(bcx, bcy)
    if g is None:
        continue
    X, Z = g; D = math.hypot(X, Z)
    # 대략 크기(m): bbox 픽셀폭/높이를 거리로 환산 (rough, Unity에서 clamp)
    w_m = (x2 - x1) / fx * D
    h_m = (y2 - y1) / fy * D
    detections.append({
        # 통합데이터규약 v2 이름 (anchor360_live.py 와 같은 모양 — 옛 v1: name · pos3d · dist_m · size · bbox_xyxy · conf)
        "id": i, "label": d["name"], "group": d["group"],
        "confidence": round(d["conf"], 3),
        "bbox": [int(x1), int(y1), int(x2), int(y2)],
        "position": {"x": round(X, 3), "y": 0.0, "z": round(Z, 3)},
        "ground_dist_m": round(D, 3),
        "size_m": {"w": round(w_m, 3), "h": round(h_m, 3), "d": round(w_m, 3)},
        "ground_clipped": bool(y2 >= H - 2),
    })

_now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))).isoformat(timespec="milliseconds")
packet = {
    "schema_version": "2.0", "source_id": "detect-send-3b2", "node_id": socket.gethostname(),
    "zone_id": "zoneA", "timestamp": _now, "emitted_at": _now,
    "width": W, "height": H,                   # 박스 좌표의 기준 = 슬라이스 크기
    "view": {"u_deg": -60, "v_deg": PITCH, "roll_deg": 0},
    "coordinate_frame": "anchor360",
    "detections": detections,
}
payload = json.dumps(packet, ensure_ascii=False)

# 파일 저장(팀원 전달용 예시)
with open(JSON_OUT, "w", encoding="utf-8") as f:
    f.write(json.dumps(packet, ensure_ascii=False, indent=2))

# UDP 송출
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.sendto(payload.encode("utf-8"), (UNITY_IP, PORT))
sock.close()

print(f"검출/필터 통과 {len(detections)}개 → UDP {UNITY_IP}:{PORT} 송출, JSON 저장: {JSON_OUT}")
for d in detections:
    print(f'  {d["label"]:14}{d["group"]:14} position=({d["position"]["x"]:+.2f},0,{d["position"]["z"]:+.2f}) '
          f'D={d["ground_dist_m"]:.2f} size=({d["size_m"]["w"]:.2f},{d["size_m"]["h"]:.2f}) clip={d["ground_clipped"]}')