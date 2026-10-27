# Physical-Project-mk2

<p align="center">
  <a href="docs/deployment/README.md"><img src="https://img.shields.io/badge/Docs-Deployment_Guide-FFD700?style=for-the-badge" alt="Documentation"></a>
  <a href="https://github.com/choBottle/Physical-Project-mk2/discussions"><img src="https://img.shields.io/badge/Discussions-181717?style=for-the-badge&logo=github&logoColor=white" alt="Discussions"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-green?style=for-the-badge" alt="License: MIT"></a>
  <a href="https://github.com/choBottle/Physical-Project-mk2/releases"><img src="https://img.shields.io/github/v/release/choBottle/Physical-Project-mk2?include_prereleases&style=for-the-badge" alt="Release"></a>
  <a href="README.md"><img src="https://img.shields.io/badge/Lang-한국어-red?style=for-the-badge" alt="한국어"></a>
</p>

<p align="center">
  <a href="https://github.com/choBottle/Physical-Project-mk2/actions/workflows/ci.yml"><img src="https://github.com/choBottle/Physical-Project-mk2/actions/workflows/ci.yml/badge.svg" alt="ci"></a>
  <a href="https://github.com/choBottle/Physical-Project-mk2/actions/workflows/deploy-smoke.yml"><img src="https://github.com/choBottle/Physical-Project-mk2/actions/workflows/deploy-smoke.yml/badge.svg" alt="deploy-smoke"></a>
</p>

**An open physical-AI platform for disaster-response and national-infrastructure sites.** Sensors, robots, drones and
cameras publish to zone edge nodes and a central server, which collect, store and observe the data by its nature
(business, observability, media) and connect it to a digital twin and operator consoles. Like ROS 2 for robotics, the goal
is an **open platform that defense, climate and disaster-response agencies can take and stand up at their own sites.**

No vendor lock-in — MQTT, Kafka, OpenTelemetry and Tailscale are **replaceable current implementations**, and the contracts
between parts are **JSON Schema**, not code.

<table>
<tr><td><b>Reproducible from an empty server</b></td><td>A 13-service central stack (Mosquitto · Kafka · TimescaleDB · MySQL · OTel Collector · Prometheus · Loki · Tempo · Grafana · 4 backend services) with one <code>docker compose</code>. Secrets live in a single <code>.env</code>; DB schema and grants initialize on first start.</td></tr>
<tr><td><b>The nature of data picks the channel</b></td><td>Business = MQTT (devices) → Kafka (backbone), observability = OpenTelemetry, media = a separate path, browsers = WebSocket. Features grow; channels don't.</td></tr>
<tr><td><b>Load scales with zones</b></td><td>Each zone edge (Mosquitto · OTel agent · edge Prometheus) absorbs its devices first; the center federates across a tunnel.</td></tr>
<tr><td><b>From device to screen</b></td><td>Raspberry Pi sensor, robot (Go1 · RoboMaster EP) and actuator nodes, PX4 drone SAR, Insta360 anchor camera → center → the <code>viz-debugger</code> console and a Unity digital twin.</td></tr>
<tr><td><b>Capability-based AI</b></td><td><code>perception-framework</code> composes perception, risk assessment and planning per device capability, with a DEVS simulator.</td></tr>
<tr><td><b>Observes itself</b></td><td>The backend emits its own metrics, logs and traces, not just the devices'. Dashboards and alert rules are committed.</td></tr>
<tr><td><b>CI proves the deployment</b></td><td>Every PR stands the stack up on an empty runner: healthcheck (32 checks) → end-to-end test with the real device-node code → backend regression → backup/restore round trip.</td></tr>
</table>

---

## Quick Install — central server

### Linux · macOS · Windows (WSL2 or Git Bash)

All you need is Docker (Compose v2.24+).

```bash
git clone https://github.com/choBottle/Physical-Project-mk2.git
cd Physical-Project-mk2/deploy
./scripts/init-env.sh                 # generates passwords and tokens → deploy/.env
docker compose up -d --build --wait   # 13 services (3–5 min on first run)
```

> **Without building:** set `MK2_BACKEND_IMAGE=ghcr.io/chobottle/mk2-backend:<version>` in `deploy/.env` and run
> `docker compose up -d --wait` — the image is public.

> **Edge and devices:** zone edge in [`deploy/edge/`](deploy/edge/), Raspberry Pi nodes in [`hardware/pi/deploy/`](hardware/pi/deploy/)
> (`install-units.sh --user <user>`). See the [edge guide](docs/deployment/edge.md).

---

## Getting Started

```bash
./scripts/seed-demo.sh     # (optional) declare demo zones and devices
./scripts/healthcheck.sh   # "flowing", not just "running" — business path · 3 observability signals · DB grants (32 checks)
./scripts/e2e-sim.sh       # real device-node code (simulated sensor) → center → console subscription · storage · metrics (10 checks)
./scripts/backup.sh        # backup (restore: ./scripts/restore.sh)
```

- **Grafana** http://127.0.0.1:7862 (`GRAFANA_ADMIN_*` in `deploy/.env`) → **MK2 Backend Overview**
- **Test data:** `docker compose exec be-ingest python tests/publisher.py --host mosquitto --count 10`
- **Console:** in `visualization/viz-debugger` run `npm ci && npm run dev`, then in Connections set the gateway to `ws://127.0.0.1:8765/state?token=<MK2_WS_TOKEN>` and the zone to `zoneA`

📖 **[Full deployment guide →](docs/deployment/README.md)** (Korean)

---

## Layout

```text
[devices]          [zone edge]                    [central server]                                  [users]
sensors·robots ──▶ Mosquitto · OTel agent ═tunnel═▶ Kafka ─▶ storage (TimescaleDB · MySQL)      ─▶ console
360·drone cams ──▶ edge Prometheus (raw)           OTel Collector ─▶ Prometheus · Loki · Tempo ─▶ Grafana
                                                   WS gateway (live state · media relay)        ─▶ Unity twin
```

| Folder | Part | What | Owner |
| --- | --- | --- | --- |
| [`server/`](server/) | Backend | ingest · storage · WS gateway · capture upload · **common data contracts** · DB schema | @daegyu10 |
| [`hardware/`](hardware/) | Hardware · edge | Raspberry Pi sensor/robot (Go1 · RoboMaster EP)/actuator nodes · Unity bridge · edge reference | @choBottle |
| [`ai/`](ai/) | AI | perception-framework — capability-based perception, risk and planning · DEVS simulator | @JNY03 |
| [`visualization/`](visualization/) | Visualization | viz-debugger console (incl. drone SAR views) · contracts (JSON Schema) · STT/generation labs | @khw18033 |
| [`drone/`](drone/) | Drone | PX4 SAR (synthetic aperture radar) passes · RTK relay · flight data · radar integration | jhjeong |
| [`camera360/`](camera360/) | 360 camera | Insta360 anchor camera → ground-plane obstacles → Unity | @daegyu10 |
| [`osmocam/`](osmocam/) | Camera source | DJI Osmo as a wireless MJPEG source (MIT fork) | @khw18033 |
| [`deploy/`](deploy/) | **Deployment** | central and edge stacks (compose) · observability config · DB init · ops scripts | shared |
| [`docs/`](docs/) | Docs | deployment guide · ports · releases · open-source readiness | shared |

Each folder was a team branch, merged **with its commit history preserved** (`git log -- server/`).

---

## Documentation

Documentation is primarily in Korean; issues and pull requests in English are welcome.

| Document | What's covered |
| --- | --- |
| [Deployment guide](docs/deployment/README.md) | overview · requirements · install · verification · troubleshooting |
| [Database](docs/deployment/database.md) | MySQL · TimescaleDB schema · grants · migrations · backup/restore |
| [Observability](docs/deployment/observability.md) | Prometheus · Loki · Tempo · Grafana · metrics · alerts · edge federation |
| [Edge](docs/deployment/edge.md) | standing up a zone edge · connecting to the center · device nodes |
| [End-to-end test](docs/deployment/e2e.md) | device → center → console (simulated and real hardware) · records |
| [Security](docs/deployment/security.md) | exposure policy · tokens · tunnel · production checklist |
| [Operations runbook](docs/deployment/operations.md) | restart · upgrade · backup · per-alert response |
| [Ports](docs/PORTS.md) | port registry (single source of truth) |
| [Release policy](docs/RELEASE.md) | versioning · release process · 1.0 criteria · 1.x roadmap |

---

## Status

**v1.0.0 release candidate** — [`v1.0.0-rc.1`](https://github.com/choBottle/Physical-Project-mk2/releases/tag/v1.0.0-rc.1).
Remaining 1.0 work is tracked in the [release criteria](docs/RELEASE.md#3-v100-출시-기준). Authentication, RBAC and TLS are
on the 1.x roadmap; until then, run it **inside a tunnel only** ([security](docs/deployment/security.md)).

---

## Contributing

Contributions are welcome! See [CONTRIBUTING](CONTRIBUTING.md) for setup, conventions and the PR process, and
[GOVERNANCE](GOVERNANCE.md) for how decisions are made.

```bash
git clone https://github.com/choBottle/Physical-Project-mk2.git
cd Physical-Project-mk2
# per-part tests — same commands as CI
(cd ai/perception-framework && pip install -e ".[dev,mqtt,kafka,otel,sim]" && OTEL_SDK_DISABLED=true python -m pytest -q)
(cd visualization/viz-debugger && npm ci && npm run typecheck && npm run build)
(cd drone && pip install -e ".[test,image,base]" && python -m pytest -q)
(cd deploy && ./scripts/init-env.sh && docker compose up -d --build --wait && ./scripts/healthcheck.sh)
```

---

## Community

- 💬 [Discussions](https://github.com/choBottle/Physical-Project-mk2/discussions) — questions · ideas · adoption stories
- 🐛 [Issues](https://github.com/choBottle/Physical-Project-mk2/issues) — bugs · deployment problems (attach `healthcheck.sh` output)
- 🔒 [Security reports](SECURITY.md) — private vulnerability reporting instead of public issues
- 🤝 [Code of Conduct](CODE_OF_CONDUCT.md)

---

## License

MIT — see [LICENSE](LICENSE). Bundled third-party components (`osmocam/`, radar integration code, …) keep their original
licenses — [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

Built by the Physical-Project-mk2 contributors —
[@daegyu10](https://github.com/daegyu10) · [@choBottle](https://github.com/choBottle) · [@JNY03](https://github.com/JNY03) · [@khw18033](https://github.com/khw18033) · jhjeong.
