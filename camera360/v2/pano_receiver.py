"""
pano_receiver.py — Insta360 Pro2 파노라마 재료 수신 서버

[목적]
  노트북에서 Pro2 촬영 파일(thumbnail / origin_1~6 / pro.prj 등)을 받아
  서버의 폴더에 '세트 단위'로 저장한다.
  - 기존 server_stream_depth_v2(포트 7864, GO1 스트리밍용)와 완전히 분리됨.
  - 이 파일은 Pro2 전용 별도 경로. 포트 7866 사용.

[엔드포인트]
  POST /upload_pano
    - Form: capture_id (예: "PIC_20260626_163847")  ← 촬영 폴더명
    - Form: camera_id  (기본 "cam360-001_main" — 2026-10-14 통합데이터규약 v2, 예전 "pro2_anchor")
    - Form: meta       (선택, JSON 글자 — 프레임 헤더. stream_to_server.py 가 보낸다)
    - File: file       (여러 파일을 반복 전송하거나, 한 번에 하나씩 전송)
    → 저장 위치: PANO_ROOT/{camera_id}/{capture_id}/{원본파일명}
       meta 가 오면 같은 폴더에 {원본파일 이름}.json (equirect.jpg → equirect.json) 으로
       {"meta": <프레임 헤더>, "sha1": <사진 바이트 SHA-1 앞 16자>} 를 남긴다 (CAM360-02).
       anchor360_live 가 이것으로 원본 프레임(frame_ref)을 가리킨다 — 사진과 sha1 이 같을 때만 쓴다.

  GET /pano_health
    - 서버 살아있는지 확인용

[설계 메모]
  - Pro2 파일은 'stitching 재료'라서 휘발성 Redis가 아니라 디스크 폴더에 보존.
  - capture_id(촬영 폴더명) 기준으로 같은 세트를 한 폴더에 모은다.
  - 지금은 thumbnail 1장만 보내며 검증하지만,
    origin_1~6.jpg + pro.prj 를 추가로 보내도 같은 폴더에 쌓이도록 설계.

[실행]
  서버에서:  python3 pano_receiver.py
  (uvicorn이 0.0.0.0:7865 로 listen)
"""

import os
import json
import time
import hashlib
from typing import Optional
from fastapi import FastAPI, UploadFile, File, Form
import uvicorn

# =========================================================
# 저장 루트 경로
#   - 서버의 적절한 작업 폴더로 바꿔도 됨.
#   - 상대경로면 이 파일을 실행한 위치 기준으로 생성됨.
# =========================================================
PANO_ROOT = "pano_captures"

app = FastAPI()
from fastapi.responses import FileResponse
# pano_receiver.py 46~47줄 교체
CAPSTONE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # .../capstone-db
LATEST_JSON = os.path.join(CAPSTONE_ROOT, "docx2026", "live_out", "anchor360_latest.json")

@app.get("/anchor360_latest")
async def anchor360_latest():
    """360° 검출 결과 JSON. 랩실 PC가 당겨가서 유니티로 중계한다."""
    if not os.path.exists(LATEST_JSON):
        return {"status": "empty"}
    return FileResponse(LATEST_JSON, media_type="application/json")


def _safe_name(name: str) -> str:
    """경로 조작 방지: 파일명에서 디렉터리 구분자 제거."""
    return os.path.basename(name).replace("\\", "_").replace("/", "_")


@app.post("/upload_pano")
async def upload_pano(
    file: UploadFile = File(...),
    capture_id: str = Form("unknown_capture"),
    camera_id: str = Form("cam360-001_main"),
    meta: Optional[str] = Form(None),
):
    """
    Pro2 촬영 파일 1개를 받아 capture_id 폴더에 저장.
    여러 파일은 같은 capture_id로 반복 호출하면 한 폴더에 모인다.
    """
    try:
        capture_id = _safe_name(capture_id)
        camera_id = _safe_name(camera_id)          # 저장 경로에 들어가므로 capture_id 와 같이 거른다
        filename = _safe_name(file.filename or "nofilename.bin")

        save_dir = os.path.join(PANO_ROOT, camera_id, capture_id)
        os.makedirs(save_dir, exist_ok=True)
        save_path = os.path.join(save_dir, filename)

        data = await file.read()
        tmp_path = save_path + ".part"
        with open(tmp_path, "wb") as f:
            f.write(data)
        os.replace(tmp_path, save_path)

        meta_saved = False
        if meta:                                   # 프레임 헤더 (CAM360-02) — 사진을 바꾼 뒤에 쓴다
            try:
                meta_obj = json.loads(meta)
            except ValueError:
                meta_obj = None
                print(f"[pano][Warn] meta 가 JSON 이 아니라 남기지 않음: {meta[:80]!r}")
            if isinstance(meta_obj, dict):
                json_path = os.path.splitext(save_path)[0] + ".json"
                with open(json_path + ".part", "w", encoding="utf-8") as f:
                    json.dump({"meta": meta_obj, "sha1": hashlib.sha1(data).hexdigest()[:16]}, f, ensure_ascii=False)
                os.replace(json_path + ".part", json_path)
                meta_saved = True

        size_kb = len(data) / 1024
        print(f"[pano] saved: {save_path} ({size_kb:.0f}KB){' + meta' if meta_saved else ''}")

        return {
            "status": "saved",
            "camera_id": camera_id,
            "capture_id": capture_id,
            "filename": filename,
            "size_kb": round(size_kb, 1),
            "path": save_path,
            "meta_saved": meta_saved,
        }

    except Exception as e:
        print(f"[pano][Error] upload failed: {e}")
        return {"status": "error", "detail": str(e)}
    finally:
        await file.close()


@app.get("/pano_health")
async def pano_health():
    """서버 동작 확인용."""
    return {"status": "ok", "time": time.time(), "root": os.path.abspath(PANO_ROOT)}


if __name__ == "__main__":
    os.makedirs(PANO_ROOT, exist_ok=True)
    print(f"✅ pano_receiver starting on 0.0.0.0:7866")
    print(f"   save root: {os.path.abspath(PANO_ROOT)}")
    uvicorn.run(app, host="0.0.0.0", port=7866, workers=1)
