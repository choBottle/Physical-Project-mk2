"""camlink 의 순수 함수 — DUML 프레임 인코딩/해석(duml) · 고정 payload(protocol) · H.264/H.265 판별(nal).

BLE · Wi-Fi · 카메라 없이 돈다.
"""
import struct
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from camlink import duml, nal, protocol  # noqa: E402
from camlink.duml import FLAG_REPLY, FLAG_REQUEST, FrameReader, Message  # noqa: E402


def _msg(payload=b"\x01\x02\x03", seq=0x1234, flags=FLAG_REQUEST):
    return Message(protocol.ADDR_APP, protocol.ADDR_CAMERA, seq, flags, 0x00, 0x88, payload)


# ── duml ───────────────────────────────────────────────────────────────────
def test_encode_layout():
    m = _msg()
    frame = m.encode()
    assert frame[0] == duml.START
    assert len(frame) == duml.OVERHEAD + len(m.payload)
    length_field = struct.unpack_from("<H", frame, 1)[0]
    assert length_field & 0x3FF == len(frame)
    assert length_field >> 10 == duml.VERSION
    assert frame[3] == duml.crc8(frame[:3])
    assert (frame[4], frame[5]) == (protocol.ADDR_APP, protocol.ADDR_CAMERA)
    assert struct.unpack_from("<HBBB", frame, 6) == (0x1234, FLAG_REQUEST, 0x00, 0x88)
    assert frame[11:-2] == m.payload
    assert int.from_bytes(frame[-2:], "little") == duml.crc16(frame[:-2])


@pytest.mark.parametrize("payload", [b"", b"\x00", bytes(range(256))])
def test_roundtrip(payload):
    m = _msg(payload)
    assert duml.parse_all(m.encode()) == [m]


def test_reader_handles_split_joined_and_noise():
    a, b = _msg(b"first"), _msg(b"second", seq=2)
    stream = b"\x00\x13noise" + a.encode() + b"\xaa" + b.encode()
    reader = FrameReader()
    got = []
    for i in range(0, len(stream), 5):           # BLE 알림처럼 잘게 나눠 넣는다
        got += reader.feed(stream[i:i + 5])
    assert got == [a, b]


def test_reader_drops_bad_crc16():
    good = _msg(b"ok").encode()
    bad = bytearray(_msg(b"xx").encode())
    bad[-1] ^= 0xFF
    assert duml.parse_all(bytes(bad) + good) == [_msg(b"ok")]


def test_reader_waits_for_incomplete_frame():
    frame = _msg(b"partial").encode()
    reader = FrameReader()
    assert reader.feed(frame[:-3]) == []
    assert reader.feed(frame[-3:]) == [_msg(b"partial")]


def test_reply_flags_and_answer():
    req = _msg()
    assert req.needs_reply and not req.is_reply
    rep = req.answer(b"\x00")
    assert rep.is_reply and not rep.needs_reply
    assert (rep.sender, rep.receiver, rep.seq, rep.command) == (req.receiver, req.sender, req.seq, req.command)
    assert req.answer(b"", sender=0x99).sender == 0x99


def test_crc_known_values():
    # 표 기반 CRC 가 같은 다항식의 비트 단위 계산과 같은지 본다.
    def crc_bitwise(data, value, poly, mask):
        for byte in data:
            value ^= byte
            for _ in range(8):
                value = (value >> 1) ^ poly if value & 1 else value >> 1
        return value & mask

    data = b"\x55\x0e\x04camlink"
    assert duml.crc8(data) == crc_bitwise(data, 0x77, 0x8C, 0xFF)
    assert duml.crc16(data) == crc_bitwise(data, 0x3692, 0x8408, 0xFFFF)


# ── protocol ───────────────────────────────────────────────────────────────
def test_pairing_message_payload():
    m = protocol.pairing_message()
    assert (m.sender, m.receiver, m.command) == (protocol.ADDR_APP, protocol.ADDR_WIFI, (0x07, 0x45))
    ident, token = protocol.APP_IDENTITY.encode(), protocol.PAIR_TOKEN.encode()
    assert m.payload == bytes((len(ident),)) + ident + bytes((len(token),)) + token
    assert duml.parse_all(m.encode()) == [m]


def test_app_info_reply_length():
    assert len(protocol.APP_INFO_REPLY) == 62


def test_topic_subscription_layout():
    raw = protocol.topic_subscription("battery", 0x01020304)
    name = b"battery"
    assert raw.startswith(b"\x02\x02\x00\x00")
    sub_id, = struct.unpack_from("<I", raw, 4)
    total, n = struct.unpack_from("<HH", raw, 11)
    assert sub_id == 0x01020304
    assert (total, n) == (len(name) + 6, len(name))
    assert raw[15:15 + len(name)] == name and raw.endswith(bytes(4))
    assert len(raw) == 15 + len(name) + 4


# ── nal ────────────────────────────────────────────────────────────────────
AVC_SPS = b"\x00\x00\x00\x01\x67\x64\x00\x1f"          # NAL type 7, High profile (100)
HEVC_VPS = b"\x00\x00\x00\x01\x40\x01\x0c\x01"


def test_codec_of():
    assert nal.codec_of(AVC_SPS + b"\x00\x00\x01\x68\xee") == nal.H264
    assert nal.codec_of(HEVC_VPS + b"\x00\x00\x01\x42\x01") == nal.HEVC
    assert nal.codec_of(b"\x00\x00\x01\x41\x9a\x00") is None          # P 슬라이스만 — 키프레임 아님
    assert nal.codec_of(b"") is None


def test_hevc_idr_n_lp_is_not_mistaken_for_h264():
    # H.265 IDR_N_LP 슬라이스 머리(28 01)는 H.264 로 읽으면 type 8 이지만, 둘째 바이트가 프로파일이 아니다.
    assert nal.codec_of(b"\x00\x00\x01\x28\x01\xaf") is None
    # 0x27 = H.264 SPS(type 7) 꼴이지만 둘째 바이트 01 은 프로파일이 아니다.
    assert nal.codec_of(b"\x00\x00\x01\x27\x01\x00") is None


def test_parameter_sets_offset_includes_leading_zero():
    assert nal.parameter_sets(b"\xaa\xbb" + AVC_SPS) == (2, nal.H264)
    assert nal.parameter_sets(b"\xaa\x00\x00\x01\x40\x01") == (1, nal.HEVC)
    assert nal.parameter_sets(b"\xaa" * 10 + AVC_SPS, limit=8) is None


def test_nal_starts():
    unit = b"\x00\x00\x01\x09\x00\x00\x00\x01\x67"
    assert list(nal.nal_starts(unit)) == [3, 8]
