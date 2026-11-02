"""pano_receiver.py — 업로드 수신 서버의 토큰 · 이름 거르기 · 크기 상한 · 저장 · 기동 거부.

pano_receiver 는 환경변수를 import 할 때 읽는다. 그래서 시험마다 monkeypatch 로 환경을 바꾼 뒤
importlib.reload 로 다시 읽힌다(fixture `load`).
"""
import hashlib
import importlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

CAM360 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CAM360))

ENV_KEYS = ("MK2_PANO_BIND", "MK2_PANO_PORT", "MK2_PANO_TOKEN", "MK2_PANO_ROOT", "MK2_PANO_MAX_BYTES")
JPEG = b"\xff\xd8\xff\xe0" + bytes(range(256)) * 4


@pytest.fixture
def root(tmp_path):
    return tmp_path / "pano_root"


@pytest.fixture
def load(monkeypatch, root):
    """환경을 정하고 pano_receiver 를 다시 읽어 (모듈, TestClient) 를 돌려준다."""

    def _load(**env):
        for k in ENV_KEYS:
            monkeypatch.delenv(k, raising=False)
        monkeypatch.setenv("MK2_PANO_ROOT", str(root))
        for k, v in env.items():
            monkeypatch.setenv(k, v)
        import pano_receiver
        mod = importlib.reload(pano_receiver)
        return mod, TestClient(mod.app)

    return _load


def _upload(client, data=JPEG, filename="equirect.jpg", headers=None, params=None, **form):
    form.setdefault("capture_id", "PIC_20260626_163847")
    return client.post("/upload_pano", files={"file": (filename, data, "image/jpeg")},
                       data=form, headers=headers or {}, params=params or {})


def _files(root):
    return sorted(p.relative_to(root).as_posix() for p in Path(root).rglob("*") if p.is_file())


# ── 토큰 ──────────────────────────────────────────────────────────────────
def test_no_token_is_401_when_token_configured(load, root):
    _, client = load(MK2_PANO_TOKEN="s3cret")
    r = _upload(client)
    assert r.status_code == 401
    assert r.json()["detail"] == "unauthorized"
    assert _files(root) == []


def test_wrong_token_is_401(load, root):
    _, client = load(MK2_PANO_TOKEN="s3cret")
    assert _upload(client, headers={"X-MK2-Token": "nope"}).status_code == 401
    assert _upload(client, params={"token": "nope"}).status_code == 401
    assert _files(root) == []


def test_token_accepted_by_header_or_query(load):
    _, client = load(MK2_PANO_TOKEN="s3cret")
    assert _upload(client, headers={"X-MK2-Token": "s3cret"}).status_code == 200
    assert _upload(client, params={"token": "s3cret"}).status_code == 200


def test_no_token_configured_allows_upload(load):
    _, client = load()
    assert _upload(client).status_code == 200


# ── 이름 거르기 ────────────────────────────────────────────────────────────
@pytest.mark.parametrize("field,value", [
    ("capture_id", ".."),
    ("capture_id", "."),
    ("camera_id", ".."),
    ("camera_id", "."),
])
def test_dot_names_are_400(load, root, field, value):
    _, client = load()
    r = _upload(client, **{field: value})
    assert r.status_code == 400
    assert r.json()["detail"] == "bad_name"
    assert _files(root) == []


@pytest.mark.parametrize("filename", ["..", "."])
def test_dot_filename_is_400(load, root, filename):
    _, client = load()
    r = _upload(client, filename=filename)
    assert r.status_code == 400
    assert _files(root) == []


@pytest.mark.parametrize("name", ["", ".", "..", "   ", "a\x00b", None])
def test_safe_name_rejects_empty_and_dots(load, name):
    mod, _ = load()
    with pytest.raises(HTTPException) as e:
        mod._safe_name(name)
    assert e.value.status_code == 400


def test_traversal_in_names_stays_inside_root(load, root):
    _, client = load()
    r = _upload(client, filename="../../evil.jpg", capture_id="../../x", camera_id="..\\..\\cam")
    assert r.status_code == 200, r.text
    saved = Path(r.json()["path"]).resolve()
    assert saved.is_file()
    assert Path(os.path.commonpath([root.resolve(), saved])) == root.resolve()
    assert saved.name == "evil.jpg"


# ── 크기 상한 ──────────────────────────────────────────────────────────────
def test_over_max_bytes_is_413_and_leaves_no_file(load, root):
    _, client = load(MK2_PANO_MAX_BYTES="100")
    r = _upload(client, data=b"x" * 101, meta=json.dumps({"frame_ref": "f1"}))
    assert r.status_code == 413
    assert r.json()["detail"] == "too_large"
    assert _files(root) == []          # 사진도 .part 도 meta json 도 남지 않는다


def test_exactly_max_bytes_is_accepted(load):
    _, client = load(MK2_PANO_MAX_BYTES="100")
    assert _upload(client, data=b"x" * 100).status_code == 200


# ── 정상 저장 ──────────────────────────────────────────────────────────────
def test_normal_upload_saves_file_and_meta_with_sha1(load, root):
    _, client = load()
    meta = {"frame_ref": "cam360-001_main:42", "capture_timestamp": "2026-10-14T10:00:00.000+09:00"}
    r = _upload(client, camera_id="cam360-001_main", meta=json.dumps(meta))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "saved"
    assert body["camera_id"] == "cam360-001_main"
    assert body["capture_id"] == "PIC_20260626_163847"
    assert body["filename"] == "equirect.jpg"
    assert body["meta_saved"] is True

    folder = root / "cam360-001_main" / "PIC_20260626_163847"
    assert (folder / "equirect.jpg").read_bytes() == JPEG
    saved_meta = json.loads((folder / "equirect.json").read_text(encoding="utf-8"))
    assert saved_meta == {"meta": meta, "sha1": hashlib.sha1(JPEG).hexdigest()[:16]}
    assert _files(root) == ["cam360-001_main/PIC_20260626_163847/equirect.jpg",
                            "cam360-001_main/PIC_20260626_163847/equirect.json"]


def test_default_camera_id_and_no_meta(load, root):
    _, client = load()
    r = _upload(client)
    assert r.status_code == 200
    assert r.json()["meta_saved"] is False
    assert _files(root) == ["cam360-001_main/PIC_20260626_163847/equirect.jpg"]


@pytest.mark.parametrize("meta", ["not json", "[1, 2]"])
def test_non_object_meta_is_not_saved(load, root, meta):
    _, client = load()
    r = _upload(client, meta=meta)
    assert r.status_code == 200
    assert r.json()["meta_saved"] is False
    assert not any(f.endswith(".json") for f in _files(root))


def test_health(load):
    _, client = load()
    r = client.get("/pano_health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


# ── 기동 거부 ──────────────────────────────────────────────────────────────
@pytest.mark.parametrize("host,expected", [
    ("127.0.0.1", True), ("::1", True), ("localhost", True), ("127.8.9.10", True),
    ("0.0.0.0", False), ("100.64.0.1", False), ("example.com", False),
])
def test_is_loopback(load, host, expected):
    mod, _ = load()
    assert mod._is_loopback(host) is expected


def test_refuses_to_start_off_loopback_without_token(tmp_path):
    env = {k: v for k, v in os.environ.items() if k not in ENV_KEYS}
    env.update(MK2_PANO_BIND="0.0.0.0", MK2_PANO_PORT="0", MK2_PANO_ROOT=str(tmp_path / "root"),
               PYTHONIOENCODING="utf-8")
    try:
        p = subprocess.run([sys.executable, str(CAM360 / "pano_receiver.py")], cwd=str(tmp_path), env=env,
                           capture_output=True, text=True, encoding="utf-8", timeout=60)
    except subprocess.TimeoutExpired:
        pytest.fail("pano_receiver started (or hung) instead of refusing a non-loopback bind without a token")
    assert p.returncode == 2, (p.stdout, p.stderr)
    assert "MK2_PANO_TOKEN" in p.stderr
    assert not (tmp_path / "root").exists()     # 거부하면 저장 폴더도 만들지 않는다
