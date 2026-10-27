# Changelog

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and versions follow [Semantic Versioning](https://semver.org/). What counts as
the public API is defined in [docs/RELEASE.md](docs/RELEASE.md). Each release
has a separate "Deployment changes" section for new environment variables,
ports, database migrations and image versions.

## [Unreleased]

### Added

- `docs/deployment/endpoints.md`: what to change on each device when the
  object-detection stream server, the perception server, the 360 anchor
  server or the Unity PC moves to another host, and how to check it.
- `hosts.local.json` (real robot and drone addresses for the stream server)
  is ignored by git.

### Changed

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
