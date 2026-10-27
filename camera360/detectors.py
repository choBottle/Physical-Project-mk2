"""
detectors.py — 검출기 교체점
================================================================
camera360 스크립트(anchor360_live.py · detect_send_3b2*.py · detect_ground_3b1.py)는
검출 모델을 직접 만들지 않고 이 파일의 make_detector() 로 받는다. 그래서 모델을
바꿀 때 스크립트를 고치지 않고 config(yaml) 한 줄만 바꾼다.

  models:
    zeroshot_detector:
      backend: yolo_world        # 기본값. 없으면 yolo_world
      weight: yolov8s-world.pt
      conf: 0.25

backend 값
  yolo_world       ultralytics YOLOWorld (AGPL-3.0). weight = .pt 경로나 ultralytics 모델 이름.
                   파일이 없으면 ultralytics 가 첫 실행 때 받는다.
  grounding_dino   Hugging Face transformers 의 Grounding DINO (Apache-2.0).
                   weight = HF 모델 ID (기본 IDEA-Research/grounding-dino-tiny). pip install transformers
  모듈:클래스      직접 만든 검출기. 예) mypkg.det:MyDetector  — 아래 Detector 꼴을 따르면 된다.
                   생성자는 (weight, classes) 를 받는다. device 를 주면 device= 키워드로도 받는다.

어느 backend 든 열린 어휘(open-vocabulary) 검출기여야 한다 — config 의 classes.zeroshot 문장으로
찾을 대상을 정하기 때문이다. 닫힌 어휘 모델(RT-DETR · YOLOX 등)을 쓰려면 모듈:클래스로 감싸
자기 클래스 이름을 classes 순서에 맞춰 돌려주면 된다.

Detector 꼴
  detect(bgr, conf, imgsz) -> [(cls_idx, conf, (x1, y1, x2, y2)), ...]
      bgr    : OpenCV BGR uint8 이미지
      cls_idx: classes 목록의 번호 (classes[cls_idx] 가 이름)
      좌표   : 입력 이미지 픽셀
"""
import importlib


class YoloWorldDetector:
    """ultralytics YOLOWorld — 지금까지 쓰던 검출기 그대로."""

    def __init__(self, weight, classes, device=None):
        from ultralytics import YOLOWorld      # 이 backend 를 고를 때만 필요하다
        self.model = YOLOWorld(weight)
        self.model.set_classes(list(classes))
        self.kw = {} if device is None else {"device": device}

    def detect(self, bgr, conf, imgsz):
        res = self.model.predict(bgr, conf=conf, imgsz=imgsz, verbose=False, **self.kw)
        out = []
        if res and res[0].boxes is not None:
            for b in res[0].boxes:
                out.append((int(b.cls[0]), float(b.conf[0]),
                            tuple(float(v) for v in b.xyxy[0])))
        return out


class GroundingDinoDetector:
    """Grounding DINO (transformers). imgsz 는 쓰지 않는다 — 프로세서가 크기를 정한다."""

    DEFAULT_ID = "IDEA-Research/grounding-dino-tiny"

    def __init__(self, weight, classes, device=None):
        import torch
        from transformers import AutoModelForZeroShotObjectDetection, AutoProcessor
        model_id = weight if weight and not str(weight).endswith(".pt") else self.DEFAULT_ID
        self.torch = torch
        if device is None or device == "cuda" or device == 0:
            device = "cuda" if torch.cuda.is_available() else "cpu"
        self.device = device
        self.classes = [c.lower() for c in classes]
        self.processor = AutoProcessor.from_pretrained(model_id)
        self.model = AutoModelForZeroShotObjectDetection.from_pretrained(model_id).to(self.device).eval()
        self.text = ". ".join(self.classes) + "."

    def _cls_idx(self, label):
        """모델이 돌려준 문구 → classes 번호. 똑같은 것이 없으면 가장 많이 겹치는 것."""
        label = label.strip().lower()
        if label in self.classes:
            return self.classes.index(label)
        words = set(label.split())
        best, best_n = None, 0
        for i, c in enumerate(self.classes):
            n = len(words & set(c.split()))
            if n > best_n:
                best, best_n = i, n
        return best

    def detect(self, bgr, conf, imgsz):
        rgb = bgr[:, :, ::-1]
        inputs = self.processor(images=rgb, text=self.text, return_tensors="pt").to(self.device)
        with self.torch.no_grad():
            outputs = self.model(**inputs)
        h, w = bgr.shape[:2]
        try:
            r = self.processor.post_process_grounded_object_detection(
                outputs, inputs["input_ids"], threshold=conf, text_threshold=conf,
                target_sizes=[(h, w)])[0]
        except TypeError:                       # transformers 4.50 이전은 box_threshold
            r = self.processor.post_process_grounded_object_detection(
                outputs, inputs["input_ids"], box_threshold=conf, text_threshold=conf,
                target_sizes=[(h, w)])[0]
        labels = r.get("text_labels", r.get("labels"))
        out = []
        for box, score, label in zip(r["boxes"], r["scores"], labels):
            cid = self._cls_idx(label)
            if cid is not None:
                out.append((cid, float(score), tuple(float(v) for v in box.tolist())))
        return out


BACKENDS = {
    "yolo_world": YoloWorldDetector,
    "grounding_dino": GroundingDinoDetector,
}


def make_detector(weight, classes, backend=None, device=None):
    """backend 이름(또는 "모듈:클래스")으로 검출기를 만든다. 없으면 yolo_world.
    device: 주지 않으면 각 backend 기본값 (ultralytics 는 스스로 고른다)."""
    backend = backend or "yolo_world"
    if backend in BACKENDS:
        cls = BACKENDS[backend]
    elif ":" in backend:
        mod, name = backend.split(":", 1)
        cls = getattr(importlib.import_module(mod), name)
    else:
        raise SystemExit("모르는 검출기 backend: %r (쓸 수 있는 것: %s, 또는 모듈:클래스)"
                         % (backend, ", ".join(BACKENDS)))
    return cls(weight, classes) if device is None else cls(weight, classes, device=device)


def backend_of(cfg, slot="zeroshot_detector"):
    """config 사전에서 backend 이름을 꺼낸다 (models.<slot>.backend)."""
    return ((cfg.get("models") or {}).get(slot) or {}).get("backend")
