# Third-party notices

The code in this repository is licensed under the root [LICENSE](LICENSE)
(MIT). The components below keep their original licenses; the root license
does not replace them.

## Included in this repository

| Path | Original work | License | Notes |
|------|---------------|---------|-------|
| [`osmocam/`](osmocam/) | [luisreysan/osmocam](https://github.com/luisreysan/osmocam), "The OsmoCam authors" | MIT ([`osmocam/LICENSE`](osmocam/LICENSE)) | Modified to output an MJPEG stream. Notices for projects referenced by the original are in [`osmocam/NOTICE.md`](osmocam/NOTICE.md). |
| `drone/radar_team/`, `drone/tests/data/cansar/` | Code provided by the radar team (`cansar_pi.py`, `cansar.service` and others) and an unmodified test copy | MIT (root [LICENSE](LICENSE)) | The original authors agreed to MIT publication on 2026-10-26. The originals are preserved; changes by the drone team are marked `# [드론 쪽 제안 10/4]` and kept in `cansar_pi.diff`. |

## Used as dependencies, not included

| Component | License | Note |
|-----------|---------|------|
| `pyvirtualcam` (osmocam) | GPL-2.0 | Distributing osmocam as a single bundled executable would make that bundle GPL. Source distribution, as done here, is not affected. |
| Unitree Legged SDK (hardware, Go1) | Vendor license | Not included. Obtain it from the vendor. |
| DJI RoboMaster SDK (hardware, EP) | Apache-2.0 | Installed from a fork via git. |
| Deployment images: Kafka (Apache-2.0), Mosquitto (EPL-2.0/EDL-1.0), MySQL (GPL-2.0, used only as a server), TimescaleDB (Timescale License, Community edition), Prometheus (Apache-2.0), Loki, Tempo and Grafana (AGPL-3.0), OpenTelemetry Collector (Apache-2.0) | Per image | The images are run unmodified. If you modify Grafana, Loki, Tempo (AGPL) or TimescaleDB and offer them as a service, review those licenses separately. |

## Models and model libraries

No model weights are included in this repository; `*.pt`, `*.pth`,
`*.onnx`, `*.engine`, `*.ckpt` and `*.safetensors` files are ignored by git.
Weights are downloaded by the libraries on first use or obtained by the
operator. The licenses below apply to whoever installs and runs them, and
some of them are more restrictive than the MIT License of this repository.

| Component | Used by | License | What it means for a deployment |
|-----------|---------|---------|--------------------------------|
| Ultralytics (`ultralytics` package, YOLOv8, YOLO-World and RT-DETR weights it downloads) | `camera360/` detectors, `ai/perception-framework` (`yolo_world_provider.py`, `fastsam_provider.py`, `rpn_propose.py`) | AGPL-3.0, or a commercial Ultralytics license | Optional. If you modify it, or offer a network service built on it, AGPL-3.0 obligations apply to that combined work. Use another detector (see [docs/deployment/pluggability.md](docs/deployment/pluggability.md)) if that is not acceptable. |
| Ultralytics YOLOE | `camera360/vision_infer.py` | AGPL-3.0 | Same as Ultralytics. |
| FastSAM | `ai/perception-framework` (`fastsam_provider.py`) | AGPL-3.0 | Same as Ultralytics. |
| MobileCLIP weights (`mobileclip_blt.ts`, downloaded by Ultralytics for YOLOE text prompts) | `camera360/vision_infer.py` | Apple Machine Learning Research Model license (code MIT) | The weights are released for research use. Review the license before any other use. |
| UniDepth | `camera360/unidepth_dual_yolo.py`, `camera360/vision_infer.py`, `ai/perception-framework` (`self_localization.py`) | CC BY-NC 4.0 | Non-commercial use only. Do not use it in a commercial deployment. |
| MoGe | `camera360/vision_infer.py` | MIT (code) | Check the license on the model card of the weights you download. |
| Grounding DINO (`IDEA-Research/grounding-dino-tiny` via Hugging Face transformers) | `camera360/detectors.py` (`grounding_dino` backend), `ai/perception-framework` (`grounding_dino_provider.py`) | Apache-2.0 | No additional obligations beyond the notice. |
| OpenAI CLIP ViT-B/32 | `ai/perception-framework` (`clip_dictionary_provider.py`, `open_vocabulary.py`); YOLO-World text encoder | MIT | No additional obligations beyond the notice. |

A copy of `yolov8s-world.pt` was committed by mistake in `206bd37` and
removed in the following release; it was the unmodified Ultralytics release
asset (AGPL-3.0) and is available from Ultralytics.

## Trademarks

DJI, Osmo, Unitree, RoboMaster and Insta360 are trademarks of their
respective owners. This project is not affiliated with or endorsed by those
companies.
