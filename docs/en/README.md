# Deployment guide — standing up the MK2 platform on an empty server

> Translated from the Korean source [docs/deployment/README.md](../deployment/README.md) at commit
> [`a694208`](https://github.com/choBottle/Physical-Project-mk2/blob/a6942082abe114864dbdc422e0c8dd1463745d41/docs/deployment/README.md);
> if they disagree, the Korean document is authoritative.

> Goal of this document: **someone who has never seen this project (another institution, a new contributor) can bring up
> the central server stack on one empty Linux server in under 30 minutes and confirm for themselves that data flows.**
> A stack that only runs on our lab server is not deployed.

| Document | Contents |
|---|---|
| **This document** | Overview · requirements · installation · verification · troubleshooting |
| [operations.md](operations.md) | Operations runbook — restart · upgrade · backup · response per alert |
| [edge.md](edge.md) | Zone edge node (Raspberry Pi) setup · connecting to the central server |
| [security.md](security.md) | Exposure policy · tokens · tunnel · production checklist |
| [database.md](database.md) | DB schema (MySQL · TimescaleDB) · grants · schema change procedure (migrations) · password rotation · backup/restore/retention |
| [observability.md](../deployment/observability.md) (Korean) | Prometheus · Loki · Tempo · Grafana · metric list · alerts · edge federation |
| [offline.md](../deployment/offline.md) (Korean) | Air-gapped install — one bundle of images, repository and Python wheels |
| [e2e.md](../deployment/e2e.md) (Korean) | End-to-end test — real device node code → central → operator screen |
| [../PORTS.md](../PORTS.md) | Port registry (single source) |

---

## 1. Overview

MK2 has five segments. `deploy/` in this repository reproduces **segment 2 (edge) and segment 4 (central server)**.

```text
[1 Devices]           [2 Zone edge]                 [3 Tunnel]       [4 Central server]                       [5 Users]
sensors·robots·drones ─MQTT─▶ Mosquitto                              Mosquitto ─▶ be-ingest ─▶ Kafka ─┬▶ be-storage ─▶ TimescaleDB · MySQL
cameras         ─OTLP─▶ OTel Collector(Agent) ──── Tailscale ────▶ OTel Collector ─▶ Prometheus·Loki·Tempo ─▶ Grafana
                ─video─▶ (media sender)       (business, telemetry  be-gateway /ingest ──────────────┴▶ be-gateway /state·/media ─▶ operator screen
                         edge Prometheus ◀──── and video share  ── Prometheus(edge_federate)
                                               one tunnel)
```

| Kind of data | Channel | Storage |
|---|---|---|
| Business (measurements, state, liveness) | MQTT (devices) → Kafka (backbone) | measurements = **TimescaleDB**; audit, registry, mission runs = **MySQL** |
| Observability (metric, log, trace) | OpenTelemetry (OTLP) | **Prometheus** · **Loki** · **Tempo** |
| Video | Separate media path (WS, method B) | Relay only (captures: filesystem + MySQL metadata) |
| Browser | WebSocket (be-gateway) | Not stored (real-time push) |

Design rationale: [`server/docs/be/00-architecture.md`](../../server/docs/be/00-architecture.md) (Korean).

### Central server components (`deploy/docker-compose.yml`)

| Service | Image (pinned) | Role |
|---|---|---|
| `mosquitto` | `eclipse-mosquitto:2.0.22` | MQTT broker — accepts publishes from devices and edges |
| `kafka` + `kafka-init` | `apache/kafka:4.1.0` (KRaft) | Business backbone, multiple consumers. `kafka-init` creates 3 topics and exits |
| `mysql` | `mysql:8.4` | Audit · registry · mission runs · capture metadata |
| `timescaledb` | `timescale/timescaledb:2.30.0-pg16` | Measurement time series (`telemetry` hypertable) |
| `be-ingest` | `mk2-backend` (`server/Dockerfile`) | MQTT subscribe → two-stage common-schema validation → Kafka |
| `be-storage` | same | Kafka → TimescaleDB · MySQL registry |
| `be-gateway` | same | Kafka → WebSocket (`/state`, `/media`) + edge media ingest (`/ingest`) |
| `be-capture` | same | Capture upload (`PUT /capture`) |
| `otel-collector` | `otel/opentelemetry-collector-contrib:0.150.1` | Collects and routes the three signals |
| `prometheus` | `prom/prometheus:v3.9.1` | Metric storage + alert rules + edge federation |
| `loki` | `grafana/loki:3.5.5` | Log storage (14-day retention) |
| `tempo` | `grafana/tempo:2.8.2` | Trace storage (168-hour retention) |
| `grafana` | `grafana/grafana:12.2.0` | Operations dashboards (datasources and dashboards auto-provisioned) |

---

## 2. Requirements

| Item | Minimum | Recommended (1–3 zones on site) |
|---|---|---|
| OS | 64-bit Linux that runs Docker (Ubuntu 22.04/24.04 are the tested targets) | same |
| CPU / RAM | 4 cores / 8 GB | 8 cores / 16 GB or more |
| Disk | 40 GB | 200 GB+ SSD (TimescaleDB, Prometheus and captures grow) |
| Software | Docker Engine 24+ · Docker Compose v2.24+ · git · bash | + Tailscale (or WireGuard) when attaching edges |

> Docker Desktop on Windows/macOS runs the same stack for development and demos (this procedure was verified on Docker
> Desktop 29). Production deployments assume Linux.
>
> On Windows, run the scripts from Git Bash or WSL2. **In Git Bash, run `export MSYS_NO_PATHCONV=1` first** — otherwise Git
> Bash rewrites container paths in documented commands such as `docker compose exec … /opt/kafka/…` and
> `promtool check config /etc/prometheus/…` into Windows paths like `C:/Program Files/Git/opt/…` (the repository scripts set
> it themselves).

---

## 3. Installation — five steps

```bash
# 1. Get the code
git clone https://github.com/choBottle/Physical-Project-mk2.git
cd Physical-Project-mk2/deploy

# 2. Environment — generates 8 passwords/tokens as random 32-char alphanumerics (.env, mode 600, not committed)
./scripts/init-env.sh

# 3. Start — builds the backend image and waits until all 13 services are healthy (first run: 3–5 min)
docker compose up -d --build --wait

# 4. (optional) Demo registry — declares 2 zones and 2 devices (one of them not deployed)
./scripts/seed-demo.sh

# 5. Verify — not just "running" but "flowing"
./scripts/healthcheck.sh
```

The deployment is done when the last line reads `결과: 통과 35 · 실패 0` ("result: 35 passed · 0 failed").

To extend the check to the device end, run `./scripts/e2e-sim.sh` — it attaches the real node code with a fake sensor and
follows the data up to the operator-screen subscription ([e2e.md](../deployment/e2e.md), Korean).

> ⚠ **Project name `COMPOSE_PROJECT_NAME`** — the first value in `deploy/.env` (default `mk2`; `init-env.sh` copies it
> unchanged from `.env.example`). Compose prefixes container, network and **volume** names with it (`mk2_mysql_data`,
> `mk2_timescale_data`, …). If the host already had an `mk2` deployment (including a clone in another folder) or volumes of a
> removed deployment are left over, the new deployment **reuses those volumes as they are.** DB passwords are set at first
> volume initialization, so the volumes hold **the old `.env`'s passwords**; they do not match the newly generated `.env` and
> the backend cannot connect to the DB. `init-env.sh` prints a warning when it finds such volumes. Then choose one of:
> ① to keep the old data, restore the old `.env`; ② to run a separate deployment next to it, change `COMPOSE_PROJECT_NAME` in
> `deploy/.env` to another name (e.g. `mk2test`) before starting. If the old deployment's network is still there (a stopped
> deployment counts), the subnets collide too, so change `MK2_NET_SUBNET` and `MK2_DB_APP_HOST` as a pair (e.g.
> `172.29.0.0/16` and `172.29.%`) — `init-env.sh` picks a free subnet and prints it when it finds a collision. Running both at
> once also collides on ports — move operator ports with `MK2_PORT_*`, and the fixed device-facing ports only on a test host
> with an override — §6; ③ to discard the old
> data, after confirming that is intended, `docker volume rm <name>_mysql_data <name>_timescale_data` (irreversible).
> A `COMPOSE_PROJECT_NAME` shell environment variable takes precedence over `.env`.

No internet on the target server: see [offline.md](../deployment/offline.md) (Korean) — use the published backend image
instead of `--build`.

### What happens automatically on first start

Every manual server step has been moved into first-time container initialization, so **the same result is produced on any
server.**

| Step | By | What |
|---|---|---|
| MySQL init | `deploy/server/initdb/mysql/10-mk2-init.sh` | Schema from `server/infra/sql/` → app account → `media_capture` → per-table grants (order is mandatory: GRANT needs the tables) |
| TimescaleDB init | `deploy/server/initdb/timescaledb/100_mk2_init.sh` | Hypertable schema → app account (SELECT and INSERT only) → `pg_hba` restricted to the app account on the Docker subnet |
| Kafka topics | `kafka-init` service | Creates `mk2.telemetry.{state,status,heartbeat}` (auto-create is off — prevents typo topics) |
| Observability wiring | Grafana provisioning | Prometheus, Loki, Tempo datasources + `MK2 Backend Overview` dashboard |

> ⚠ The init scripts run **only once, when the data volume is empty**. To apply a schema change to an existing server,
> see [database.md §4](database.md#4-schema-change-procedure-migrations).

### Addresses (on the server)

| What | Address | Notes |
|---|---|---|
| Grafana | http://127.0.0.1:7862 | `GRAFANA_ADMIN_USER` / `GRAFANA_ADMIN_PASSWORD` (`deploy/.env`) |
| Prometheus | http://127.0.0.1:7861 | MK2 alert rules in the Alerts tab |
| WS gateway | ws://127.0.0.1:8765/state?token=`MK2_WS_TOKEN` | Test viewer: `server/backend/gateway/console.html` |
| MySQL / TimescaleDB | 127.0.0.1:7858 / 127.0.0.1:7859 | App account `mk2_app` |

To view Grafana from outside the server (operator PC), do not open the port; use an SSH tunnel:
`ssh -L 7862:127.0.0.1:7862 <server>`.

---

## 4. Attaching edges — changing the exposure policy

By default **every entry point binds to `127.0.0.1`**. Nothing outside the server can connect (safe default).
When attaching edges or viewers, change one line in `deploy/.env` to the server's **tunnel address**:

```bash
MK2_EDGE_BIND=100.x.y.z                # output of: tailscale ip -4
```

The Kafka EDGE listener (9095) is not used in 1.0 — the edge business path is edge Mosquitto bridge → central Mosquitto
(1883). Leave `MK2_KAFKA_EDGE_BIND` and `MK2_KAFKA_EDGE_ADVERTISED` at their defaults (loopback, localhost).

```bash
docker compose up -d     # only the changed services are recreated
```

> 🔴 Do not use `0.0.0.0`. MQTT (anonymous) and OTLP have no authentication, so binding them only to the tunnel address
> *is* the access control. Rationale and the production checklist: [security.md](security.md).

Edge-side procedure: [edge.md](edge.md).

---

## 5. Configuration at a glance — what to change where

| To change | File |
|---|---|
| Passwords, tokens, exposure addresses, ports, retention | `deploy/.env` (template `deploy/.env.example`) |
| Service composition, image versions | `deploy/docker-compose.yml` |
| DB schema (source of truth) | `server/infra/sql/*.sql` — **no copies**. Compose reads these files directly |
| Prometheus scrape targets, alert rules (repository-managed) | `deploy/server/config/prometheus.yml` · `prometheus-rules.yml` — not edited on site |
| **Site settings** — edge targets, site jobs and rules, Alertmanager, Mosquitto accounts, compose tweaks | `deploy/site/**` · `deploy/docker-compose.override.yml` (gitignored; `*.example` shows the format) — [operations.md "Site settings"](operations.md#site-settings--do-not-edit-tracked-files) |
| Start order after reboot | `deploy/systemd/mk2-central.service` (example) — [operations.md "After a reboot"](operations.md#after-a-reboot) |
| Collector pipeline | `deploy/server/config/otel-collector.yaml` |
| Loki, Tempo retention | `deploy/server/config/loki.yaml` · `tempo.yaml` |
| Grafana dashboards | `deploy/server/grafana/dashboards/*.json` |
| Backend runtime parameters | Environment variables — single source: the table at the top of `server/backend/settings.py` |

**The production server and the repository read the same files.** Previously the server's compose and config files lived
outside the repository (gitignored) because they contained passwords and internal addresses, so there was no way to rebuild
the server or hand it to another institution. Secrets are now isolated in one `.env` and all shared configuration is
committed. Only site-specific values live in the gitignored `deploy/site/` and override — upgrades (`git checkout <tag>`)
do not collide with site settings.

---

## 6. Troubleshooting

| Symptom | Cause · action |
|---|---|
| `Bind for 127.0.0.1:7862 failed: port is already allocated` (Docker prints the actual bind address — `127.0.0.1` by default, or your `MK2_ADMIN_BIND` / `MK2_EDGE_BIND` value) | Another service on the server uses the port. Move **operator ports** (MySQL 7858 · TimescaleDB 7859 · Prometheus 7861 · Grafana 7862 · Loki 3100 · Tempo 3200) with the `MK2_PORT_*` variables in `deploy/.env`. **Device-facing ports** (1883 · 9001 · 4316–4318 · 8765–8767 · 9095) are fixed — devices and edges are configured with these numbers, so changing them on the server disconnects the devices. If one of them is already taken on a test host, override only that service's ports in a gitignored `deploy/docker-compose.override.yml` (example below). **Never do this on a production host** — remove the conflicting service instead |
| A freshly generated `.env` (even on a new clone) but the backend cannot connect to the DB · `init-env.sh` printed a volume warning | Old volumes with the same `COMPOSE_PROJECT_NAME` (default `mk2`) are being reused — they hold the old passwords. Follow the "Project name" warning in §3: restore the old `.env`, use a different `COMPOSE_PROJECT_NAME`, or remove the volumes deliberately. Check with `docker volume ls \| grep _mysql_data` |
| `failed to create network …: invalid pool request: Pool overlaps with other one on this address space` | Another Docker network (an old deployment, a deployment with a different `COMPOSE_PROJECT_NAME`, or another tool) already uses `MK2_NET_SUBNET` (default `172.28.0.0/16`). Change `MK2_NET_SUBNET` and `MK2_DB_APP_HOST` in `deploy/.env` as a pair to a free range (e.g. `172.29.0.0/16` and `172.29.%` — the MySQL application account's host restriction follows the subnet). The subnet is written into the application account's grants (MySQL host · TimescaleDB `pg_hba`) when the DB volumes are first initialized, so change it **only for a deployment that starts with new volumes** ([database.md §3](database.md)). List the subnets in use: `docker network inspect -f '{{.Name}} {{range .IPAM.Config}}{{.Subnet}}{{end}}' $(docker network ls -q)` |
| `mysql`/`timescaledb` stays `unhealthy` | `docker compose logs mysql \| grep mk2-init` — see which init step stopped. If shell scripts were checked out with CRLF they die with `bad interpreter` → `git config core.autocrlf false` and check out again (the repository's `.gitattributes` enforces LF) |
| Backend cannot connect to the DB after regenerating `.env` | DB passwords are set **at first volume initialization**. The new `.env` and the existing volume disagree. On a test server, `docker compose down -v` to delete volumes and start over; on production, see [database.md §5](database.md#5-password-rotation) |
| be-gateway exits with `exit 2` | Bound to a non-loopback address with an empty token. Check `MK2_WS_TOKEN`, `MK2_EDGE_TOKEN` |
| Tempo `/ready` returns 503 | 15-second warm-up after start. If still 503 after that, check `ingester.lifecycler` in `tempo.yaml` |
| Edge device data missing from the central DB | Check the edge bridge — on the edge, `docker compose exec mosquitto mosquitto_sub -t '$SYS/broker/connection/#' -v -C 1 -W 5` must print `1`. If `0` or no answer, check `MK2_CENTRAL_MQTT_HOST` in `deploy/edge/.env`, central `MK2_EDGE_BIND`, and the tunnel ([edge.md](edge.md)) |
| (experimental) Edge connects to Kafka 9095 but no data arrives | `MK2_KAFKA_EDGE_ADVERTISED` is `localhost` — the broker tells clients to "come to localhost" |
| No backend metrics in Grafana | Backend export interval 15 s + scrape 5 s. Wait one minute, then section 4 of `./scripts/healthcheck.sh` |

When a fixed device-facing port is already in use on a test host (e.g. another MQTT broker on the host uses 1883), create
`deploy/docker-compose.override.yml` (gitignored; compose reads it automatically; `!override` needs Compose 2.24.4+):

```yaml
services:
  mosquitto:
    ports: !override          # replace the list instead of merging it
      - "127.0.0.1:11883:1883"
      - "127.0.0.1:19001:9001"
```

Check the merged result with `docker compose config`, then `docker compose up -d`. Keep the container-side number (right)
and change only the host side (middle) — `healthcheck.sh` and `e2e-sim.sh` test inside the container network and are not
affected, but devices outside the host must use the new number. **Do not use this on a production server** (it no longer
matches the device configuration).

If it still fails, open an [issue](../../.github/ISSUE_TEMPLATE/deployment.yml) with the `./scripts/healthcheck.sh` output,
`docker compose ps -a`, and the logs of the affected service.

---

## 7. Verification record of this procedure

| Date | Environment | Result |
|---|---|---|
| 2026-10-26 | Windows 11 · Docker Desktop 29.5 (all volumes deleted, then §3 of this document as written) | 13 services healthy · `healthcheck.sh` **32/32** · backend regression `pytest` **351 passed, 2 skipped, 0 failed** · 32/32 after a backup → restore round trip. (In an earlier run one timing-dependent test failed once — [operations.md](operations.md#known-issues)) |
| 2026-10-26 | same · `deploy/edge` | A log sent to the edge Collector arrived in central Loki with `zone_id` and `agg_layer=edge` |
| 2026-11-02 | Windows 11 · Docker Desktop 29.5 · fresh clone from GitHub (`main` 6ba9e49) | 13 services healthy · `healthcheck.sh` **34/34** · `migrate.sh --dry-run` nothing pending · `e2e-sim.sh` **10/10** (publish→console median 11 ms) · `backup.sh`/`restore.sh` round trip from the repo root · edge stack bridged to the real central stack: 5 state messages sent to the edge reached central TimescaleDB, a birth reached the MySQL registry, a central downlink reached the edge · Grafana dashboard and 3 data sources · Prometheus targets 5/5 · viz-debugger `npm ci`/typecheck/build |
| 2026-11-02 | same · **upgrade** `v1.0.0-rc.2` → `main` | fresh rc.2 install (32/32) + data → the operations.md upgrade procedure as written (source build) → healthcheck 31/34 before `migrate.sh` (expected: no tracking table) → `migrate.sh` marks the baseline → **34/34**; rows and registrations from rc.2 kept. One backend-volume copy race seen on the fresh rc.2 install → fixed with `backend-volume-init` (then 3 fresh installs in a row, 35/35) |
| Every PR | GitHub Actions `ubuntu-latest` | [`deploy-smoke`](../../.github/workflows/deploy-smoke.yml) — on an empty runner: `up --wait` → `healthcheck.sh` → `e2e-sim.sh` |

**"Works in our dev environment but not in a new one" is checked by CI on every change, not by a person.**
