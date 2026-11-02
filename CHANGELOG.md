# Changelog

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and versions follow [Semantic Versioning](https://semver.org/). What counts as
the public API is defined in [docs/RELEASE.md](docs/RELEASE.md). Each release
has a separate "Deployment changes" section for new environment variables,
ports, database migrations and image versions.

## [Unreleased]

### Added

- One canonical `hardware/schema/physical_command.proto`; the viz and AI
  copies are regenerated from it and AI now speaks the hardware wire format.
  `scripts/check_contracts.py` (CI) fails on proto, generated-code, golden-byte
  or example drift (#38).
- Backend MQTT credentials, opt-in (`MK2_MQTT_USERNAME` / `MK2_MQTT_PASSWORD`),
  so the central broker can require passwords; CI job `mqtt-auth` checks it.
  The backend image is published for `linux/amd64` and `linux/arm64` (#43).
- DB schema version tracking: `schema_migrations` table in MySQL and
  TimescaleDB and `deploy/scripts/migrate.sh` (`--dry-run`). Opt-in TimescaleDB
  retention/compression and a `DataVolumeDiskUsageHigh` alert (>85%) (#44).
- ESLint (correctness rules only) for `viz-debugger` and `web-dashboard`; first
  unit tests for `camera360` and `osmocam` (#45).
- Air-gapped installation: `deploy/scripts/bundle-offline.sh` /
  `load-offline.sh` and `docs/deployment/offline.md`. English deployment docs
  under `docs/en/` (Korean remains authoritative) (#46).
- Edge → central MQTT bridge (#36): the edge Mosquitto forwards
  `+/+/+/state|status|heartbeat` and `terminal/+/uplink` to the central broker
  and receives `terminal/+/downlink`. CI's edge-stack job checks both
  directions. Before this, devices following `edge.md` never reached the
  central databases.
- Site override files that survive upgrades (#36):
  `deploy/docker-compose.override.yml`, `deploy/site/prometheus/*`,
  `deploy/site/mosquitto/*.conf` and `deploy/edge/site/*`, all gitignored with
  tracked `*.example` files. `deploy/systemd/mk2-central.service` starts the
  stack after Docker and Tailscale on boot.
- CI (#37): backend unit tests without infrastructure on Python 3.10 and 3.12,
  `server/contracts/common` example validation, hardware bench tests,
  web-dashboard typecheck, and a ruff lint job (syntax errors and undefined
  names only, `ruff.toml`).
- `docs/deployment/twin-demo.md`: recorded run with screenshots. A 360 photo
  goes through `anchor360_live.py` detection and the twin gateway into
  Gazebo; the operator console shows the Gazebo screen (in the slot used for
  Unity), the 360 camera stream and a simulated robot reported through the
  central stack. `hardware/twin/demo/run-demo.sh` starts the Gazebo side.
- README and README.ko: a screenshots section (Unity twin, Gazebo twin,
  operator console, Grafana, drone SAR) so new users can see what a
  deployment looks like.

### Changed

- AI requirements (53 `AI-*` items) moved verbatim from `ai/CLAUDE.md` to
  `ai/docs/requirements.md` (#45).
- AI messages use envelope 2.0 and the current frame-reference shape, validated
  against `server/contracts/common`. String command parameters now raise
  instead of being dropped (the wire carries numbers only) (#38).
- `server/Dockerfile` installs runtime dependencies from a hashed
  `server/requirements.lock` and no longer ships test dependencies; the base
  image is pinned by digest. The server requires Python 3.10 or later (#37).
- Workflows run with `contents: read` by default; `release.yml` grants write
  scopes per job and pins third-party actions to commit SHAs (#37).
- `healthcheck.sh` and `e2e-sim.sh` reuse fixed probe entities
  (`hc-probe`, `wl-e2e-probe`) instead of registering a new device on every
  run (#36).
- Docs: personal Windows paths and host names replaced with placeholders,
  broken relative links fixed, README port tables complete, CONTRIBUTING and
  the PR template match the CI checks (#35).
- README and README.ko name `v1.0.0-rc.2` as the current release (they still
  said rc.1).
- `docs/RELEASE.md`: 1.0.x is scoped to private networks and tunnels;
  authentication, RBAC and TLS are a 1.1.0 target, added as opt-in settings.
  `SECURITY.md` and `docs/deployment/security.md` say the same.
- `docs/RELEASE.md` section 5 and `GOVERNANCE.md`: which repository is
  canonical, and the checklist for moving it to the `sysailab` organization.
  The 1.x roadmap is now section 6.
- Site LAN addresses are no longer hard-coded in code, unit files and
  manifests; they come from environment variables with a `127.0.0.1`
  fallback. Documentation and test fixtures use RFC 5737 example addresses
  or placeholders such as `<camera-ip>`. Vendor-fixed device networks (Go1
  `192.168.123.x`, RoboMaster EP USB, DJI Osmo AP, radar SDR link, Insta360
  Farsight DHCP range) are unchanged.

### Removed

- Legacy `camera360/구버전(참고금지)/`, `camera360/image backup/`,
  `osmocam/osmocam.py.orig` and the orphan `visualization/package-lock.json`;
  `visualization/web-dashboard/.env.local` is no longer tracked (#35).
- Internal records moved to the private repository
  `sysailab/mk2-internal-docs`, under the same paths:
  `visualization/documents/` `회의록/`, `작업보고/`, `옛판/`, `작업프롬프트/`,
  `논문/`, `협의/`, and `ai/docs/obsidian/` (about 41 MB, 384 files). They are
  not needed to build, deploy or contribute. Earlier commits still contain
  them. `visualization/documents/verify_docs.py` treats citations of the moved
  files (listed in `moved-to-internal.txt`) as valid.

### Fixed

- A fresh install could fail with `mkdir …/media_capture: file exists`: the
  four backend services copied the image's `/data` into the new
  `backend_data` volume at the same time. A one-shot `backend-volume-init`
  service now does it first; `healthcheck.sh` checks it (35 checks).
- **Security:** `camera360/pano_receiver.py` accepted `..` as a camera or
  capture id and wrote outside its root, listened on all interfaces without
  authentication and read whole uploads into memory. It now rejects those
  names, streams with a size cap, takes a token and refuses to start off
  loopback without one (#34).
- `restore.sh` / `backup.sh` resolve the backup path from the caller's
  directory, so the command in `database.md` works; a failed restore is
  reported, the backend is restarted and the script exits non-zero instead of
  printing "완료" (#34).
- Capture archive uploads above `MK2_CAPTURE_ARCHIVE_MAX_BYTES` are refused
  before the body is read (#34).
- `ai/demo/test/navigate_to_target_service.py` was a syntax error on Python
  3.10/3.11 (nested f-string quotes) (#37).
- `CITATION.cff` named 1.0.0-rc.1.
- Release notes generated by `release.yml` give the GHCR image path in
  lowercase (`ghcr.io/chobottle/...`); the owner name was copied as-is and
  `docker pull` rejects upper-case repository names.
- Twin gateway: Gazebo updates are batched per tick (`create_multiple`,
  `set_pose_vector`) instead of one `gz service` process per entity, which
  fell behind and timed out with a 10 Hz robot plus 360 obstacles. A missing
  `gz` binary is logged instead of silently stopping the Gazebo thread.
- `anchor360_live.py` prints each destination as `host:port` instead of
  `host:port:port` when a port is given in `--unity-ip`.

### Deployment changes

- **Existing servers: run `./scripts/migrate.sh` once after upgrading** — it
  creates `schema_migrations` and marks the baseline. Run it on every upgrade
  from now on (no-op when nothing is pending) (#44).
- New optional: `MK2_TSDB_RETENTION_DAYS`, `MK2_TSDB_COMPRESS_AFTER_DAYS`
  (empty = off; retention deletes old telemetry permanently) (#44);
  `MK2_MQTT_USERNAME`, `MK2_MQTT_PASSWORD` (empty = anonymous; when enabling,
  recreate `mosquitto` and `be-ingest`) (#43).
- `otel-collector` mounts the data volumes read-only for the disk alert — run
  `docker compose up -d` so it is recreated (#44).
- **pano_receiver listens on 127.0.0.1 by default.** To receive from the
  camera laptop set `MK2_PANO_BIND=<tunnel IP>` and `MK2_PANO_TOKEN` on the
  server and the same `MK2_PANO_TOKEN` on the laptop. Also new:
  `MK2_PANO_PORT`, `MK2_PANO_ROOT`, `MK2_PANO_MAX_BYTES` (#34).
- New: `MK2_CAPTURE_ARCHIVE_MAX_BYTES` (default 8 GiB) (#34),
  `MK2_TRT_BACKUP_DIR` for `pro2_auto_bg.py` (#35).
- Edge: `MK2_CENTRAL_MQTT_HOST` is **required** in `deploy/edge/.env`;
  optional `MK2_CENTRAL_MQTT_PORT`, `MK2_CENTRAL_MQTT_USER`,
  `MK2_CENTRAL_MQTT_PASSWORD` (#36).
- Kafka EDGE 9095 binds `MK2_KAFKA_EDGE_BIND` (default `127.0.0.1`) and no
  longer follows `MK2_EDGE_BIND`; nothing at the edge uses it in 1.0 (#36).
- **Before upgrading**, move site edits of `prometheus.yml` or
  `mosquitto.conf` into `deploy/site/`; `edge_federate` is always on and
  reads targets from `deploy/site/prometheus/edge-targets/` (#36).
- Backend tests are no longer in the image; deploy-smoke installs
  `server/requirements-dev.lock` before running them (#37).
- New environment variables: `MK2_UNITY_IP` and `MK2_PRO2_IP` (camera360
  laptop), `HW_GO1_SDK_UNITY_IP` (Go1 `go1_sdk_pc`). See
  `docs/deployment/endpoints.md`.
- **Defaults changed** from the lab's addresses to `127.0.0.1` (or a
  documentation address for the Pro2 camera). A device that relied on the old
  built-in value must set it: `HW_UNITY_IP` or `HW_GO1_SDK_UNITY_IP` and
  `HW_BROKER_HOST` in `/etc/hw-robot.env` on the Go1 Pi; `MK2_PRO2_IP` and
  `MK2_UNITY_IP` on the 360-camera laptop.
- `go1-detect-forward.service` and `robot-relay.service` no longer pass
  `--unity-ip` on the command line, so `HW_UNITY_IP` now takes effect.
  Reinstall the units with `hardware/pi/deploy/install-units.sh` and rebuild
  `go1_sdk_pc`.
- The `augment-analyzer` k8s manifests take `${HW_BROKER_HOST}`; render them
  with `envsubst` before `kubectl apply`.

## [1.0.0-rc.2] - 2026-10-27

Second release candidate. It adds the 1.0.x decoupling steps (marked 1.0.1,
1.0.2 and 1.0.3 below) to 1.0.0 before the real-hardware end-to-end run; see
`docs/RELEASE.md` section 4.

### Added

- `docs/deployment/endpoints.md`: what to change on each device when the
  object-detection stream server, the perception server, the 360 anchor
  server or the Unity PC moves to another host, and how to check it.
- `hosts.local.json` (real robot and drone addresses for the stream server)
  is ignored by git.
- **Replaceable 360 detector.** `camera360/detectors.py` builds the detector
  from `models.zeroshot_detector.backend` in the camera360 config:
  `yolo_world` (default, Ultralytics, AGPL-3.0), `grounding_dino`
  (transformers, Apache-2.0) or `module:Class`. `anchor360_live.py` and the
  `detect_*` scripts use it. With the default backend the output is identical
  to the previous version.
- **Any 360 camera.** `camera360/upload_equirect.py` uploads equirectangular
  JPEGs from files, a watched folder or an RTSP/RTMP/USB stream in the same
  format as `stream_to_server.py`, without Insta360 Pro2 control.
- **More than one twin.** `anchor360_live.py --unity-ip` (or
  `MK2_TWIN_HOSTS`), `HW_UNITY_IP` in `go1_detect_forward.py` and
  `robot_state_relay.py --unity_ip` accept a comma-separated list of
  `host[:port]`, so Unity and another viewer can receive the same packets.
  `hardware/HW-interface/twin_listen.py` is a reference receiver for a
  non-Unity twin.
- `docs/deployment/pluggability.md`: what can be swapped by configuration and
  what is still tied to Unity or to a specific model.
- **(1.0.1) Every camera360 detector uses the swap point.**
  `unidepth_dual_yolo.py` builds its fine-tuned and zero-shot detectors with
  `make_detector()` (`models.finetune_detector.backend`,
  `models.zeroshot_detector.backend`). In `vision_infer.py`,
  `models.yoloe.backend` lets another detector fill the `yoloe` slot; the
  slot name, output folders and Redis stream names are unchanged. Overlay
  colors no longer need Ultralytics.
- **(1.0.2) Stream server sources from a file.** `server_stream_multi_source.py`
  reads its sources from `camera360/sources.json` (or `--sources`,
  `PD_SOURCES`): name, port, `kind` (`upload`, `mjpeg`, `drone_api`), device
  video port and path, camera number and MQTT port. Without the file it uses
  the same four sources as before. Pull and MQTT ports are no longer fixed in
  code, addresses for any source come from `--host name=addr`,
  `PD_HOST_<NAME>` or `hosts.local.json`, and `vision_infer.py` takes its
  device list from the same file. `--robot1/--robot2/--drone` and
  `--robot-cam` still work.
- **(1.0.3) Engine-neutral twin gateway.** `hardware/twin/twin_gateway.py`
  receives the existing twin packets (robot state 15201, 360 obstacles 5010,
  Go1 detection and motion 5009), converts them to building ENU and sends
  them to Gazebo (gz sim create, set_pose, remove), to a neutral JSON UDP
  stream or to a `module:Class` sink. Senders and Unity are unchanged; the
  gateway is one more destination. Neutral entities follow
  `hardware/HW-interface/twin-entity.schema.json`.
- `ai/perception-framework`: optional `ultralytics` extra.

### Changed

- License notices: `THIRD_PARTY_NOTICES.md` lists the models and model
  libraries and their licenses (Ultralytics, YOLOE and FastSAM AGPL-3.0,
  UniDepth CC BY-NC 4.0, MobileCLIP research license, MoGe, Grounding DINO,
  CLIP).
- Copyright holder: "Sysailab, Hanbat National University, and
  Physical-Project-mk2 contributors" (LICENSE, README, CITATION.cff).
- **One operator console.** `visualization/viz-debugger` is now the only copy
  of the console. The drone team's copy in `drone/viz-debugger` was removed
  after its drone-only features were ported: radar status, simple SAR mode,
  cansar quick-look cards, alerts and sounds, reflector survey, Pi status
  chip, pass geofence, map tile prefetch and saved reprocessing parameters.
- The drone Python packages (`sar_pass`, `rtk_relay`, `fc_watch`, `sar_data`,
  `sar_image`, `deploy/`, `radar_team/`, `tests/`) moved from
  `drone/viz-debugger/drone/` to `drone/`. The older copy in
  `visualization/viz-debugger/drone/` was removed; its `fc_watch` fix (NaN
  becomes null) was merged into `drone/`.
- **360-degree camera to Unity on data contract v2.** `anchor360_live.py` and
  `pano_receiver.py` from `camera360/v2/` replaced the files in `camera360/`,
  and `camera360/v2/` was removed (its `stream_to_server.py` and C# receiver
  were identical to the main copies). This completes the switch planned in
  the team's 2026-10-14 v2 migration manual.
- `detect_send_3b2.py` and `detect_send_3b2_timed.py` send v2 packets
  (`label`, `position`, `ground_dist_m`, `size_m`, `bbox`, `confidence`, plus
  the common header).
- `Anchor360ObstacleReceiver.cs` reads v2 and still accepts v1 packets, so
  Unity keeps building obstacles while the server is being switched. The
  copies in the team's Unity projects were updated the same way; their
  file-loading option and case-study logging hook were kept.

### Removed

- `camera360/yolov8s-world.pt` (Ultralytics weights, AGPL-3.0), committed by
  mistake in `206bd37`. Model weights are now ignored by git; Ultralytics
  downloads the file on first use.

### Fixed

Found by running the same inputs through the merged repository and through
the state right after the import (`6dcd1fb`), on 2026-10-27:

- camera360: relative model paths in the configuration YAML are resolved
  against the YAML's folder in `anchor360_live.py`, `detect_send_3b2*.py` and
  `detect_ground_3b1.py`. They were resolved against the working directory,
  so the model was not found and ultralytics downloaded the stock model
  instead. The YAML is opened as UTF-8 (Korean Windows).
- hardware: an empty `HW_UPLOAD_URL=` or `HW_DETECT_BASE=` now falls back to
  the default instead of producing an empty URL. If either is unset, the
  node prints a warning at startup and `install-units.sh` reports it, because
  without them nothing reaches Unity (obstacles on 5009, video on 5001).
- The blurred sample photos were saved again with the original JPEG
  quantization tables. Outside the blurred areas they now match the
  originals; the lower-quality save had shifted boxes and the localization
  result of the `ai/demo` sample. Fewer person detections inside the blurred
  areas is intended.
- viz-debugger: `test:drone` points at the moved `drone/` folder, and
  `verify:fake-device` waits for the disarm report after landing instead of
  racing it.

### Deployment changes

- Drone Pi installation path: `pip install -e <repo>/drone` and
  `sudo <repo>/drone/deploy/pi/install.sh` (previously
  `.../viz-debugger/drone`). On a Pi that is already installed, run
  `install.sh` once from the new location.
- **Updating a Go1 Pi to this version:** add `HW_UPLOAD_URL` and
  `HW_DETECT_BASE` (the perception server address) to `/etc/hw-robot.env`,
  then reinstall the units with
  `hardware/pi/deploy/install-units.sh --user <user>`. A `git pull` alone is
  not enough; the previously installed units do not read that file.
- 360-degree camera server: after switching `anchor360_live.py` and
  `pano_receiver.py`, packets are v2. Update the Unity receiver first or at
  the same time; it accepts v1 as well, so updating Unity first is safe.
- camera360 GPU server: the Redis password was removed from the YAML. Set
  `MK2_REDIS_PASSWORD`.

## [1.0.0-rc.1] - 2026-10-26

First public release candidate. The items left before 1.0 are listed in
[docs/RELEASE.md](docs/RELEASE.md).

### Added

- **Monorepo.** Seven team branches (`ldg_BE`, `HW`, `jny_AI`, `khw_VZ`,
  `Junho_drone`, `360camera_work`, `osmo-nano-stream`) were merged into
  `server/`, `hardware/`, `ai/`, `visualization/`, `drone/`, `camera360/` and
  `osmocam/` with their history preserved.
- **Reproducible deployment** in `deploy/`:
  - a 13-service central stack (Mosquitto, Kafka, MySQL, TimescaleDB, four
    backend services, OpenTelemetry Collector, Prometheus, Loki, Tempo,
    Grafana);
  - the backend container image `server/Dockerfile`;
  - first-start database initialization (schema, application account,
    per-table grants, restricted `pg_hba`) that reads the canonical SQL in
    `server/infra/sql/` directly;
  - six Prometheus alert rules and provisioned Grafana data sources and
    dashboards;
  - the zone edge stack `deploy/edge/` (Mosquitto, OpenTelemetry agent, edge
    Prometheus);
  - scripts `init-env.sh`, `healthcheck.sh` (32 checks), `seed-demo.sh`,
    `backup.sh` and `restore.sh`.
- **Documentation:** deployment guide, database, observability, edge,
  security, operations runbook, port registry, release policy and the
  open-source readiness record.
- **Project files:** MIT `LICENSE`, `THIRD_PARTY_NOTICES`, `CONTRIBUTING`,
  `CODE_OF_CONDUCT`, `SECURITY`, `GOVERNANCE`, CODEOWNERS, issue and pull
  request templates.
- **CI:** `ci` (deployment configuration checks, contract examples, AI tests,
  secret scan), `deploy-smoke` (start the stack on an empty runner, health
  check, backend regression, backup and restore) and `release` (GHCR image
  and draft release).

### Changed (open-source preparation, #1 to #8)

- **Site-specific values removed.** Public IP addresses of the lab server,
  Tailscale addresses, tailnet names and `/home/<user>` paths were removed
  from code defaults. Defaults are now `localhost`, the running user's home
  directory or the script's folder; real values come from environment
  variables listed in each part's `.env.example`.
- hardware: the 15 systemd units are templates; `pi/deploy/install-units.sh`
  fills in the user and paths and installs them.
- visualization and drone console: connection presets come from Vite
  environment variables. This also fixed environment variables that never
  reached the `vite build` output.
- ai: the `perception-framework` Docker image builds again (its default
  command starts the capability status panel), and CI builds the image.
- camera360: dependency files split by role (`requirements.txt`,
  `requirements-vision.txt`); the Redis password moved from the
  configuration file to an environment variable.
- License: the MIT consent of all contributors and of the radar team is
  recorded.
- Photos: all 152 images were reviewed; EXIF data was removed from the one
  photo that contained GPS coordinates.
- `server/backend/settings.py`: the publisher's default broker is
  `localhost` instead of a lab server's public IP (set `MK2_BROKER_HOST`).
- The drone CI workflow moved from `drone/.github/` to
  `.github/workflows/drone.yml`, because GitHub does not run workflows in
  subfolders.

### Removed

- Tracked build artifacts: `visualization/web-dashboard/.vite/deps` (build
  cache), `camera360/360camera_work_260921.zip` (folder snapshot) and
  `hardware/pi/robot/go1_sdk_pc.cpp.bak3`.

### Deployment changes

- **The AI capability status panel moved from port 8765 to 8775**, because
  8765 is the central WebSocket gateway. `--port` still overrides it.
- **Install hardware units only with `install-units.sh`.** Copying a
  `.service` file directly fails at startup because of the placeholders. The
  two Go1 camera units need `HW_UPLOAD_URL` and `HW_DETECT_BASE` in
  `/etc/hw-robot.env`.
- New environment variables: camera360 `MK2_SERVER_HOST`, `MK2_UPLOAD_URL`,
  `MK2_UPLOAD_STREAM_URL`, `MK2_ANCHOR360_URL`, `MK2_REDIS_PASSWORD`,
  `MK2_CAPSTONE_DB`; AI demo `MK2_MQTT_BROKER_URL`; viz-debugger
  `VITE_PHYSICAL_PRESET_*`, `VITE_DETECT_PRESET_*`, `VITE_AUTODRIVE_AI_*`.
- Differences from the manually operated lab server: the Docker network is
  fixed to `172.28.0.0/16` (`MK2_NET_SUBNET`); the MySQL application account
  host changed from `'172.18.%'` to `MK2_DB_APP_HOST` (default `172.28.%`);
  the backend runs in containers instead of systemd. Host port numbers are
  unchanged.
- The OpenTelemetry Collector accepts both 4316 and 4317 (4317 is the default
  of the hardware and AI nodes).
- Tempo's OTLP port (4317) is not published on the host, so traces cannot
  bypass the Collector.
