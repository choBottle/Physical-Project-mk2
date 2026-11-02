"""detectors.py — 검출기 교체점(make_detector · backend_of). 실제 모델은 띄우지 않는다."""
import sys
import types
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import detectors  # noqa: E402


class FakeDetector:
    def __init__(self, weight, classes, device="unset"):
        self.weight, self.classes, self.device = weight, list(classes), device

    def detect(self, bgr, conf, imgsz):
        return []


@pytest.fixture
def fake_yolo(monkeypatch):
    monkeypatch.setitem(detectors.BACKENDS, "yolo_world", FakeDetector)
    return FakeDetector


def test_default_backend_is_yolo_world(fake_yolo):
    d = detectors.make_detector("w.pt", ["person", "car"])
    assert isinstance(d, fake_yolo)
    assert (d.weight, d.classes) == ("w.pt", ["person", "car"])
    assert d.device == "unset"              # device 를 안 주면 키워드로도 넘기지 않는다


def test_device_passed_as_keyword_only_when_given(fake_yolo):
    assert detectors.make_detector("w.pt", ["a"], backend="yolo_world", device="cpu").device == "cpu"


def test_module_colon_class_backend(monkeypatch):
    mod = types.ModuleType("mk2_fake_det_mod")
    mod.MyDet = FakeDetector
    monkeypatch.setitem(sys.modules, "mk2_fake_det_mod", mod)
    d = detectors.make_detector("weights", ["x"], backend="mk2_fake_det_mod:MyDet", device=0)
    assert isinstance(d, FakeDetector) and d.device == 0


def test_unknown_backend_exits_with_choices():
    with pytest.raises(SystemExit) as e:
        detectors.make_detector("w", ["a"], backend="no_such_backend")
    assert "yolo_world" in str(e.value) and "grounding_dino" in str(e.value)


def test_known_backends():
    assert set(detectors.BACKENDS) == {"yolo_world", "grounding_dino"}


@pytest.mark.parametrize("cfg,slot,expected", [
    ({}, "zeroshot_detector", None),
    ({"models": None}, "zeroshot_detector", None),
    ({"models": {"zeroshot_detector": None}}, "zeroshot_detector", None),
    ({"models": {"zeroshot_detector": {"weight": "w.pt"}}}, "zeroshot_detector", None),
    ({"models": {"zeroshot_detector": {"backend": "grounding_dino"}}}, "zeroshot_detector", "grounding_dino"),
    ({"models": {"other": {"backend": "m:C"}}}, "other", "m:C"),
])
def test_backend_of(cfg, slot, expected):
    assert detectors.backend_of(cfg, slot) == expected


def test_grounding_dino_label_to_class_index():
    # 생성자는 transformers 를 부르므로 건너뛰고 문구→번호 매핑만 본다.
    g = object.__new__(detectors.GroundingDinoDetector)
    g.classes = ["person", "traffic cone", "red car"]
    assert g._cls_idx("Person ") == 0
    assert g._cls_idx("cone") == 1           # 가장 많이 겹치는 것
    assert g._cls_idx("red car") == 2
    assert g._cls_idx("bicycle") is None
