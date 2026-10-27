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

## Trademarks

DJI, Osmo, Unitree, RoboMaster and Insta360 are trademarks of their
respective owners. This project is not affiliated with or endorsed by those
companies.
