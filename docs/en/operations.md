# Operations runbook

> Translated from the Korean source [docs/deployment/operations.md](../deployment/operations.md) at commit
> [`3fcbcf4`](https://github.com/choBottle/Physical-Project-mk2/blob/3fcbcf4b5de212d64e81fd077f1481d0e00e7d59/docs/deployment/operations.md);
> if they disagree, the Korean document is authoritative. The Korean runbook is being revised (upgrade and migration
> steps) — check it for anything newer than that commit.

Run every command from `deploy/`. Principle: **check that data flows, not merely that containers are up** — the verdict is
`./scripts/healthcheck.sh`.

## Everyday commands

| Task | Command |
|---|---|
| Status | `docker compose ps -a` |
| Full check | `./scripts/healthcheck.sh` (liveness only: `--quick`) |
| Logs | `docker compose logs -f be-ingest` (search all logs in Grafana → Explore → Loki `{service_name=~"be-.*"}`) |
| Restart one service | `docker compose restart be-storage` |
| Reload config (Prometheus) | `curl -X POST http://127.0.0.1:7861/-/reload` |
| Reload config (others) | `docker compose up -d --force-recreate <service>` |
| Stop (keep data) | `docker compose down` |
| ⚠ Delete everything (including data) | `docker compose down -v` — test servers only |
| Backup / restore | `./scripts/backup.sh` / `./scripts/restore.sh <directory>` — [database.md §6](../deployment/database.md) (Korean) |

## After a reboot

Compose's start order (`depends_on: condition: service_healthy` — the backend waits for DB and Kafka to be healthy) is
honoured **only when `docker compose up` runs**. After a reboot, containers are revived by the Docker daemon's restart policy
(`unless-stopped`), and the daemon ignores ordering. The backend may therefore start before DB/Kafka and crash-restart a few
times (it usually recovers by itself). Also, if `MK2_EDGE_BIND` is a Tailscale address, an entry container can fail because
it tries to bind before `tailscaled` has brought the address up.

Production servers pin the order with a systemd unit — example
[`deploy/systemd/mk2-central.service`](../../deploy/systemd/mk2-central.service):

```ini
[Unit]
Requires=docker.service
After=docker.service network-online.target tailscaled.service
Wants=network-online.target tailscaled.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/opt/Physical-Project-mk2/deploy     # absolute path of this repository's deploy/
ExecStart=/usr/bin/docker compose up -d --wait --wait-timeout 600
ExecStop=/usr/bin/docker compose stop
```

```bash
sudo cp deploy/systemd/mk2-central.service /etc/systemd/system/   # after fixing WorkingDirectory
sudo systemctl daemon-reload && sudo systemctl enable mk2-central
# Allow binding the Tailscale address before it is up (recommended)
echo 'net.ipv4.ip_nonlocal_bind=1' | sudo tee /etc/sysctl.d/90-mk2-nonlocal-bind.conf && sudo sysctl --system
```

Either way, check after a reboot — `./scripts/healthcheck.sh --quick`.

## Site settings — do not edit tracked files

Upgrading is `git checkout <tag>`. Editing tracked files (`docker-compose.yml`, `server/config/*`) on site causes conflicts
or silent overwrites on the next upgrade. Site settings go **only in gitignored locations** — the `*.example` in each
location shows the format.

| To change | Site file (gitignored) | Apply with |
|---|---|---|
| Add services, resource limits, ports and other compose tweaks | `deploy/docker-compose.override.yml` (example `docker-compose.override.yml.example`) — compose reads it automatically | `docker compose up -d` |
| Edge federation targets | `deploy/site/prometheus/edge-targets/*.yml` | automatic (file_sd) |
| Site scrape jobs | `deploy/site/prometheus/scrape/*.yml` | `curl -X POST http://127.0.0.1:7861/-/reload` |
| Site alert rules | `deploy/site/prometheus/rules/*.yml` | same as above |
| Alertmanager address | `deploy/site/prometheus/alertmanagers/*.yml` (the service itself: override example) | automatic (file_sd) |
| Mosquitto production profile (accounts, ACL) | `deploy/site/mosquitto/*.conf` | `docker compose restart mosquitto` |
| Secrets, exposure addresses, ports, retention, image tag | `deploy/.env` | `docker compose up -d` |
| Edge side | `deploy/edge/.env` · `deploy/edge/site/` · `deploy/edge/docker-compose.override.yml` | same approach |

Check the merged compose with `docker compose config`. Check the Prometheus config with
`docker compose exec prometheus promtool check config /etc/prometheus/prometheus.yml`.
`./scripts/backup.sh` does not include these files — keep them, together with `.env`, separately.

## Upgrade (to a new release)

```bash
./scripts/backup.sh                       # 1. Backup (.env, site/ and override are kept separately — see "Site settings")
git status --short                        #    no site edits in tracked files (move any into site/ or override)
git fetch --tags && git checkout v1.1.0   # 2. Code
diff .env.example .env                    # 3. New environment variables — the release's `### Deployment changes` section in CHANGELOG
#    If that section lists a DB migration, apply it first using database.md §4
#    If you use the published image, bump the MK2_BACKEND_IMAGE tag in .env:
#      MK2_BACKEND_IMAGE=ghcr.io/<owner>/mk2-backend:v1.1.0
docker compose pull && docker compose up -d --wait            # 4a. Published image — only changed services are recreated
# docker compose up -d --build --wait                        # 4b. Build from source (MK2_BACKEND_IMAGE=mk2-backend:local)
./scripts/healthcheck.sh                  # 5. Verify
```

If you do not bump the `MK2_BACKEND_IMAGE` tag, the code is the new release but the backend keeps running the old image.
With a published image, do not add `--build`: compose would build a local image under that name and shadow the published one.

Rollback: `checkout` the previous tag → set `MK2_BACKEND_IMAGE` back to the previous tag → `up -d --wait` (`--build` if
building from source). If the DB changed, use `restore.sh` with the backup.

Air-gapped servers: [offline.md §7](../deployment/offline.md) (Korean).

## Response per alert

### scrape-target-down
`ScrapeTargetDown` — look at which `job`. `docker compose ps <service>` → if dead, `docker compose logs <service> --tail 50`.
If it is `edge_federate`, the problem is on the edge side (tunnel, edge Prometheus) — on the edge, `tailscale status`,
`docker compose ps`. The target list is `deploy/site/prometheus/edge-targets/*.yml`.

### backend-telemetry-absent
`BackendSelfTelemetryAbsent` — the backend is down, or the backend → Collector → Prometheus path is broken.
1. `docker compose ps be-ingest be-storage` 2. Check the first backend log line `관측 활성: … → http://otel-collector:4317`
("observability enabled")
3. `docker compose logs otel-collector --tail 30` 4. In Prometheus Targets, check that `otel_collector` is up.
Losing observability **does not stop the business path** (observability is not a precondition of business) — check
separately that TimescaleDB ingestion continues.

### kafka-produce-failing
`KafkaProduceFailing` — `docker compose logs be-ingest | grep "produce 실패"` ("produce failed"). Check broker liveness
(`docker compose ps kafka`), free disk (`df -h` — Kafka keeps 7 days), and that topics exist
(`docker compose exec kafka /opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 --list`).
If topics are missing, `docker compose up kafka-init`.

### storage-write-failing
`StorageWriteFailing` — `docker compose logs be-storage --tail 50`. Check TimescaleDB liveness and disk, and app-account
grants (if the schema changed recently, was a GRANT on a new table missed? — section 5 of `healthcheck.sh`). Data stays in
Kafka for 7 days during write failures; after the fix, consumers re-read from the committed offset (idempotency keys prevent
duplicates).

### ingest-reject-rate-high
`IngestRejectRateHigh` — publishers are sending a different version of the common schema. The quarantine file has the
reason: `docker compose exec be-ingest tail -5 /data/quarantine.jsonl`. Schema: `server/contracts/common/` and the
integrated data specification. Usually the device firmware or node code is outdated — notify that team (the server does not
loosen the schema).

### pipeline-lag-high
`PipelineLagHigh` — publish → storage latency. First suspect `clock_skew` (device clock). In TimescaleDB:
`SELECT source_id, avg(lag_s) FROM telemetry WHERE ts > now() - interval '10 min' GROUP BY 1 ORDER BY 2 DESC LIMIT 5;`
If only specific devices are high, it is that device's retransmission (spool) or clock; if everything is high, it is Kafka
consumer lag (`be-storage` load, DB latency).

## Known issues

| Item | Details |
|---|---|
| Tempo warm-up | `/ready` returns 503 for ~15 s after start — normal |
| Loki `empty ring` log | Once right after start — normal |
| `test_c4_truncated_archive_leaves_nothing` | Timing-dependent test that occasionally fails when the full regression suite (353 tests) runs at once. Passes when run alone (2026-10-26). Unrelated to deployment — the test's wait condition should be strengthened |
| Counter resets | Reset to 0 on every backend restart — read them with `rate()` |
| Test devices | `healthcheck.sh` publishes as the fixed device `hc-probe`, `e2e-sim.sh` as `wl-e2e-probe` — only these two remain in the registry (no new device per run). Each run's rows are selected by ingest time (`ingest_at`, `last_recorded_at`). Measurement rows grow with every run and are not deleted because the app account has no DELETE (intentional). When querying, use `source_id NOT IN ('hc-probe','wl-e2e-probe')` (for `hc-<time>` / `wl-e2e-<time>` left by pre-1.0 versions, `NOT LIKE 'hc-%' AND NOT LIKE 'wl-e2e-%'`) |
