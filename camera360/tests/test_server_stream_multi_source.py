"""server_stream_multi_source.py — 소스 목록 읽기 · .frm 형식 · 넘기기 묶음 · multipart 해석.

이 서버는 표준 라이브러리만으로 돈다(redis · paho 는 없어도 import 된다). GPU · 카메라는 필요 없다.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import server_stream_multi_source as ssm  # noqa: E402


@pytest.fixture(autouse=True)
def _no_env_sources(monkeypatch):
    monkeypatch.delenv("PD_SOURCES", raising=False)


def _write(tmp_path, sources):
    p = tmp_path / "sources.json"
    p.write_text(json.dumps({"sources": sources}), encoding="utf-8")
    return p


# ── 소스 목록 ──────────────────────────────────────────────────────────────
def test_repo_sources_json_loads_with_defaults():
    srcs = ssm.load_sources(ssm.SOURCES_FILE)
    assert [s["name"] for s in srcs] == ["cam360", "drone", "robot1", "robot2"]
    assert len({s["port"] for s in srcs}) == len(srcs)
    cam = srcs[0]
    assert cam["kind"] == "upload" and cam["mqtt_port"] is None and cam["cam"] == 1
    assert all(s["kind"] in ssm.KINDS for s in srcs)


def test_repo_sources_json_matches_builtin_defaults():
    # sources.json 이 없을 때의 기본값과 저장소 sources.json 이 어긋나지 않게 한다.
    raw = json.loads(ssm.SOURCES_FILE.read_text(encoding="utf-8"))["sources"]
    assert raw == ssm.DEFAULT_SOURCES


def test_env_pd_sources_wins_over_file(tmp_path, monkeypatch):
    p = _write(tmp_path, [{"name": "only", "port": 11000, "kind": "upload"}])
    monkeypatch.setenv("PD_SOURCES", str(p))
    srcs = ssm.load_sources()
    assert [s["name"] for s in srcs] == ["only"]
    assert srcs[0]["aliases"] == [] and srcs[0]["path"] == "/stream/{cam}"


def test_non_upload_gets_default_mqtt_port(tmp_path):
    p = _write(tmp_path, [{"name": "r", "port": 11000, "kind": "mjpeg", "video_port": 8090}])
    assert ssm.load_sources(p)[0]["mqtt_port"] == 1883


@pytest.mark.parametrize("sources", [
    [{"name": "a", "port": 1, "kind": "upload"}, {"name": "b", "port": 1, "kind": "upload"}],   # 포트 겹침
    [{"name": "a", "port": 1, "kind": "upload"}, {"name": "a", "port": 2, "kind": "upload"}],   # 이름 겹침
    [{"name": "a", "port": "1", "kind": "upload"}],                                             # 포트가 글자
    [{"name": "", "port": 1, "kind": "upload"}],                                                # 이름 없음
    [{"name": "a", "port": 1, "kind": "rtsp"}],                                                 # 모르는 kind
    [{"name": "a", "port": 1, "kind": "mjpeg"}],                                                # video_port 없음
])
def test_bad_sources_exit(tmp_path, sources):
    with pytest.raises(SystemExit):
        ssm.load_sources(_write(tmp_path, sources))


def test_unreadable_sources_file_exits(tmp_path):
    p = tmp_path / "broken.json"
    p.write_text("{not json", encoding="utf-8")
    with pytest.raises(SystemExit):
        ssm.load_sources(p)
    with pytest.raises(SystemExit):
        ssm.load_sources(tmp_path / "missing.json")


# ── .frm 형식 · 넘기기 묶음 ────────────────────────────────────────────────
def test_frame_roundtrip():
    header = {"source": "cam360", "seq": 7, "이름": "값"}
    image = b"\xff\xd8\xff\x00jpeg"
    assert ssm.unpack_frame(ssm.pack_frame(header, image)) == (header, image)


@pytest.mark.parametrize("data", [b"", b"\x00\x00", b"\x00\x00\x00\xff{}"])
def test_unpack_frame_rejects_short_or_bad_length(data):
    with pytest.raises(ValueError):
        ssm.unpack_frame(data)


@pytest.mark.parametrize("head,ext", [(b"\xff\xd8\xff\xe0", ".jpg"), (b"\x89PNG\r\n\x1a\n", ".png"), (b"GIF8", ".bin")])
def test_image_ext(head, ext):
    assert ssm.image_ext(head + b"rest") == ext


def test_records_roundtrip_and_truncation():
    items = [(b"F", b"frame-bytes"), (b"S", b""), (b"S", b'{"k":1}')]
    body = ssm.pack_records(items)
    assert list(ssm.unpack_records(body)) == items
    with pytest.raises(ValueError):
        list(ssm.unpack_records(body[:-1]))


# ── multipart ──────────────────────────────────────────────────────────────
def _multipart(boundary, parts):
    out = b""
    for headers, content in parts:
        out += b"--" + boundary + b"\r\n" + b"".join(h + b"\r\n" for h in headers) + b"\r\n" + content + b"\r\n"
    return out + b"--" + boundary + b"--\r\n"


def test_multipart_to_frame_json_meta_wins_over_text_field():
    b = b"XyZ"
    body = _multipart(b, [
        ([b'Content-Disposition: form-data; name="camera_id"'], b"text-cam"),
        ([b'Content-Disposition: form-data; name="meta"', b"Content-Type: application/json"],
         json.dumps({"camera_id": "json-cam", "seq": 3}).encode()),
        ([b'Content-Disposition: form-data; name="file"; filename="a.jpg"', b"Content-Type: image/jpeg"],
         b"\xff\xd8\xff\r\n\x00binary"),
        ([b'Content-Disposition: form-data; name="blob"'], b"\xff\xfe\xfd"),
    ])
    ctype = 'multipart/form-data; boundary="XyZ"'
    assert ssm.content_type_param(ctype, "boundary") == "XyZ"
    parts = ssm.split_multipart(body, "XyZ")
    assert len(parts) == 4
    sender, image = ssm.form_to_frame(parts)
    assert image == b"\xff\xd8\xff\r\n\x00binary"
    assert sender["camera_id"] == "json-cam"           # 타입 있는 JSON 칸이 글자 칸을 이긴다
    assert sender["seq"] == 3
    assert sender["blob"] == {"base64": "//79"}         # utf-8 이 아니면 base64 로 남긴다


def test_frame_fields_skips_reserved_and_serialises_values():
    header = {"sender": {"image": "x", "header": "y", "": "z", "seq": 3, "camera_id": "c"}}
    fields = ssm.frame_fields(b"img", header)
    assert fields["image"] == b"img"
    assert json.loads(fields["header"]) == header
    assert fields["seq"] == "3" and fields["camera_id"] == "c"
    assert "" not in fields


def test_disposition_and_header_value():
    assert ssm.disposition('form-data; name="meta"; filename="a.jpg"') == {"name": "meta", "filename": "a.jpg"}
    assert ssm.header_value({"Content-Type": "x"}, "content-type") == "x"
    assert ssm.header_value({}, "content-type") is None
