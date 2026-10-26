# 제3자 구성요소 고지 (Third-Party Notices)

이 저장소의 코드는 루트 [`LICENSE`](LICENSE)(MIT)를 따른다. 단, 아래 구성요소는 **각자의 원 라이선스**를
따르며 루트 라이선스가 그것을 대체하지 않는다.

## 저장소 안에 포함된 것

| 경로 | 원 저작물 | 라이선스 | 비고 |
|---|---|---|---|
| [`osmocam/`](osmocam/) | [luisreysan/osmocam](https://github.com/luisreysan/osmocam) — "The OsmoCam authors" | MIT ([`osmocam/LICENSE`](osmocam/LICENSE)) | MJPEG 스트림 출력으로 개조한 판. 원 저작물이 참조한 프로젝트들의 고지는 [`osmocam/NOTICE.md`](osmocam/NOTICE.md) |
| `drone/viz-debugger/drone/radar_team/` · `drone/viz-debugger/drone/tests/data/cansar/` | 레이더 팀 제공 코드(`cansar_pi.py` · `cansar.service` 등)와 시험용 원본 사본 | MIT (루트 [`LICENSE`](LICENSE)) | 원 저작자(레이더 팀)가 2026-10-26 MIT 공개에 동의. 원본을 그대로 보존하고 드론 쪽 수정은 `# [드론 쪽 제안 10/4]` 표시 · `cansar_pi.diff` 로 구분 |

## 의존성으로만 쓰는 것 (저장소에 포함하지 않음)

| 구성요소 | 라이선스 | 주의 |
|---|---|---|
| `pyvirtualcam` (osmocam) | GPL-2.0 | osmocam 을 **단일 실행 파일로 묶어 배포**하면 그 산출물은 GPL 이 된다. 소스 배포(현재 방식)에는 해당 없음 |
| Unitree Legged SDK (hardware, Go1) | 벤더 라이선스 | 저장소에 포함하지 않는다. 사용자가 벤더에서 직접 받는다 |
| DJI RoboMaster SDK (hardware, EP) | Apache-2.0 | 포크(git) 의존 |
| 배포 스택 이미지 — Kafka(Apache-2.0) · Mosquitto(EPL-2.0/EDL-1.0) · MySQL(GPL-2.0, 서버로만 사용) · TimescaleDB(Timescale License, Community) · Prometheus(Apache-2.0) · Loki/Tempo/Grafana(AGPL-3.0) · OpenTelemetry Collector(Apache-2.0) | 각 이미지 | **수정 없이 컨테이너 이미지로 실행**만 한다. Grafana·Loki·Tempo(AGPL)·TimescaleDB 를 수정해 서비스로 제공하는 경우 각 라이선스 조건을 따로 검토한다 |

## 상표

DJI·Osmo·Unitree·RoboMaster·Insta360 은 각 소유자의 상표다. 이 프로젝트는 그 회사들과 무관하며 보증을 받지 않았다.
