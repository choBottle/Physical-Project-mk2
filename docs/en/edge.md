# Zone edge node

> Translated from the Korean source [docs/deployment/edge.md](../deployment/edge.md) at commit
> [`3fcbcf4`](https://github.com/choBottle/Physical-Project-mk2/blob/3fcbcf4b5de212d64e81fd077f1481d0e00e7d59/docs/deployment/edge.md);
> if they disagree, the Korean document is authoritative.

> One edge per zone. It is the first stop for device business and observability traffic, so central load grows **with the
> number of zones**, not the number of devices.
> Edge ↔ central runs over a private network, so **a tunnel is mandatory** (current implementation: Tailscale — replaceable).

## 1. What runs where

| Layer | What | Deployment assets |
|---|---|---|
| Edge shared stack | Mosquitto (+ central bridge) · OTel Collector (Agent) · edge Prometheus | [`deploy/edge/`](../../deploy/edge/) (this document) |
| Device nodes | Sensor · robot (Go1/RoboMaster EP) · actuator · detection bridge | [`hardware/pi/deploy/`](../../hardware/pi/deploy/) — systemd units + `hw-robot` image · install guide [`hardware/docs/EDGE_SETUP.md`](../../hardware/docs/EDGE_SETUP.md) (Korean) |
| Drone companion | SAR pass · RTK relay · flight logs | [`drone/deploy/pi/`](../../drone/deploy/pi/) · [`FIELD_CHECKLIST.md`](../../drone/FIELD_CHECKLIST.md) |

### Paths

```text
business  device ─MQTT─▶ edge Mosquitto(1883) ══bridge(tunnel)══▶ central Mosquitto(1883) ─▶ be-ingest ─▶ Kafka ─▶ TimescaleDB·MySQL
commands  device ◀────── edge Mosquitto ◀═══════bridge═══════════ central Mosquitto ◀─ command publisher
observ.   device ─OTLP─▶ edge Collector(4317) ─┬─ metric ─▶ edge Prometheus ◀─/federate(summary)─ central Prometheus
                                               └─ log·trace ─▶ central Collector(4317)
```

Topics forwarded by the edge Mosquitto bridge (generated at start-up from `deploy/edge/.env` by
`deploy/edge/config/mosquitto-entrypoint.sh`):

| Direction | Topic | What |
|---|---|---|
| edge → central | `+/+/+/state` · `+/+/+/status` · `+/+/+/heartbeat` | The three telemetry channels — `{zone}/{etype}/{eid}/{channel}`, the same ones central `be-ingest` subscribes to |
| edge → central | `terminal/+/uplink` | Command responses · Capability |
| central → edge | `terminal/+/downlink` | Commands |

Other topics (local device-to-device topics etc.) stay inside the edge. The bridge connects with a fixed per-zone client id
(`mk2-edge-<zone>`) and a persistent session — commands (QoS 1) queued at the central broker while the tunnel was down are
delivered on reconnect. Conversely, telemetry produced while the tunnel is down is queued by the edge Mosquitto in the bridge
session and forwarded later. The limit is Mosquitto's default `max_queued_messages` (1000 messages); beyond that, messages
are dropped (devices are still connected to the edge broker, so they do not retransmit from their own spool). If long
outages are expected, put a `.conf` that raises `max_queued_messages` in `deploy/edge/site/mosquitto/`.

## 2. Order

### 1) Tunnel

Put both the central server and the edge in the same tailnet and note their addresses.

```bash
tailscale up            # once (with the institution's account)
tailscale ip -4         # this is <tunnel address> below
```

### 2) Central server — entry points on the tunnel address

Central `deploy/.env`:

```bash
MK2_EDGE_BIND=<central tunnel address>
```

The Kafka EDGE listener (9095) is **not used in 1.0** — the edge does not connect to Kafka; it hands traffic to central
Mosquitto through the MQTT bridge. Leave `MK2_KAFKA_EDGE_BIND` and `MK2_KAFKA_EDGE_ADVERTISED` at their defaults
(loopback, localhost); change them only for the experimental deployment in §4.

After `docker compose up -d`, `nc -zv <central tunnel address> 1883 4317 8766` from the edge must show all three open.

### 3) Edge shared stack

```bash
cd deploy/edge
cp .env.example .env
#   MK2_ZONE_ID=zoneA
#   MK2_CENTRAL_OTLP=<central tunnel address>:4317
#   MK2_CENTRAL_MQTT_HOST=<central tunnel address>    ← central Mosquitto for the business bridge (port: MK2_CENTRAL_MQTT_PORT, default 1883)
#   MK2_EDGE_TUNNEL_BIND=<edge tunnel address>        ← entry the central server pulls federation from
docker compose up -d --wait
```

If accounts are enabled on central Mosquitto, put the bridge account in `MK2_CENTRAL_MQTT_USER` and
`MK2_CENTRAL_MQTT_PASSWORD`. Edge site settings (device accounts, site scrape jobs) go in the gitignored `deploy/edge/site/`
and `deploy/edge/docker-compose.override.yml`, not in tracked files —
[operations.md "Site settings"](operations.md#site-settings--do-not-edit-tracked-files).

### 4) Device nodes

Point three values of the device node configuration (`hardware/pi/deploy/hw-node.env.example`) at the edge:

| Variable | Value |
|---|---|
| `HW_BROKER_HOST` | The edge itself (`localhost`) or the edge LAN address — the edge Mosquitto bridges to central |
| `HW_OTEL_ENDPOINT` | `http://<edge address>:4317` |
| `HW_ZONE_ID` | Same value as `MK2_ZONE_ID` in `deploy/edge/.env` |

### 5) Enable central federation

Add the edge tunnel address to central `deploy/site/prometheus/edge-targets/edge.yml` —
[observability.md §6](../deployment/observability.md) (Korean).

## 3. Verification

| Check | How | Expected |
|---|---|---|
| Bridge connected | On the edge: `docker compose exec mosquitto mosquitto_sub -t '$SYS/broker/connection/#' -v -C 1 -W 5` | `$SYS/broker/connection/mk2-edge-zoneA/state 1` |
| Business data reaches the central DB | On central: `docker compose exec timescaledb psql -U postgres -d mk2 -c "SELECT source_id, max(ingest_at) FROM telemetry WHERE zone_id='zoneA' AND ingest_at > now() - interval '10 min' GROUP BY 1"` | This zone's devices with recent times |
| Commands reach the edge | On the edge, keep `docker compose exec mosquitto mosquitto_sub -t 'terminal/+/downlink' -v` running and publish a command on central | Arrives at the edge |
| Edge metrics on the edge | `curl http://<edge tunnel address>:9090/api/v1/label/__name__/values` | `hw_*` |
| Edge metrics on central (federation) | Central Prometheus `up{job="edge_federate"}` · `count by (zone_id) (hw_publish_count_total{agg_layer="edge"})` (`zone_id` is the target label in `edge.yml`) | `1` · this zone's series |

Device nodes do not export logs via OTel (they use journald on the Pi), so verify the edge observability path with metrics as
above. The edge Collector's log path itself is open (verified 2026-10-26: **a test log sent directly** to the edge Collector
arrived in central Loki with `zone_id=zoneT` and `agg_layer=edge`). CI (`deploy-smoke`'s `edge-stack`) tests the business
bridge in both directions on every PR (edge publish → arrives at central broker · out-of-scope topics stay on the edge ·
central command → arrives at the edge).

## 4. Current limits (outside v1.0 scope)

- **Edge Kafka bridge**: the architecture's final form is "edge Mosquitto → edge ingest → central Kafka (EDGE 9095)". 1.0
  forwards through the edge Mosquitto MQTT bridge to central Mosquitto and runs ingest centrally (§1 paths). Running
  `be-ingest` on the edge (`MK2_KAFKA_BOOTSTRAP=<central>:9095`, central `MK2_KAFKA_EDGE_BIND` and
  `MK2_KAFKA_EDGE_ADVERTISED` set to the tunnel address) was demonstrated on 2026-09-19 with a PC acting as a temporary edge,
  but is not yet in the edge compose — [RELEASE.md roadmap](../RELEASE.md) (Korean). Until then, 9095 need not be opened on
  the tunnel.
- The bridge is plaintext MQTT — the tunnel provides encryption. For deployments outside a tunnel, see
  [security.md](security.md).
- k3s-based edge orchestration is at the level of the recovery notes in
  [`hardware/k3s/README.md`](../../hardware/k3s/README.md) (Korean).
- Device node systemd units are templates — install them with `hardware/pi/deploy/install-units.sh --user <user>` (copying
  them directly with `sudo cp` makes them fail to start).
- No internet on the edge or devices: [offline.md §5–6](../deployment/offline.md) (Korean).
