# Database — schema · grants · changes · backup

> Translated from the Korean source [docs/deployment/database.md](../deployment/database.md) at commit
> [`a694208`](https://github.com/choBottle/Physical-Project-mk2/blob/a6942082abe114864dbdc422e0c8dd1463745d41/docs/deployment/database.md);
> if they disagree, the Korean document is authoritative.

> Source of truth (single source): [`server/infra/sql/`](../../server/infra/sql/). This document is a map; the rationale for
> each column is in the comments of the SQL files. Deployment reads those files **directly** (no copies — two copies would
> silently drift apart).

## 1. Why two stores

The **nature** of the data decides the store (architecture principle 4).

| Data | Store | Why |
|---|---|---|
| Sensor measurements · robot/actuator state over time | **TimescaleDB** (PostgreSQL 16 extension) | Numbers on a time axis. Loss and reordering detection is solved with window functions (SQL). Retention and compression policies attach to the hypertable |
| Command audit · mission run records · registry · capture metadata | **MySQL 8.4** | Relational, mostly static. Append-only is enforced by **DB grants** |
| metric · log · trace | Prometheus · Loki · Tempo | Observability plane — [observability.md](../deployment/observability.md) (Korean) |
| Twin state · command progress · device availability | Not stored | Pushed over WS on arrival |

**Honest weakness:** two relational engines mean two sets of backups, accounts and monitoring. The replacement point is a
single file, `server/backend/storage/tsdb_writer.py`, so the lock-in is narrow.

## 2. Schema

### TimescaleDB — DB `mk2` (`mk2_tsdb_schema.sql`)

One hypertable, `telemetry` (time axis `ts` = **publish time** — data that arrives late is placed at its original
measurement time).

| Column group | Columns |
|---|---|
| Time axis · routing | `ts` · `channel` · `entity_type` |
| Common header | `source_id` · `node_id` · `zone_id` · `entity_id` · `session_id` · `sequence_id` · `schema_version` · `origin_kind` |
| Three timestamps · derived | `ingest_at` · `received_at` · `lag_s` · `clock_skew` · `replayed` |
| Common body | `reason` · `device_status` |
| Idempotency key | `stream_topic` · `stream_partition` · `stream_offset` (UNIQUE — no duplicates even when Kafka redelivers) |
| Original | `payload` (JSONB — the whole message as received) |

Principle: **store the original as is and detect at query time** — gaps and losses are not judged at ingestion but computed
with `LAG()` in `server/docs/be/queries/gap-detection.sql` (so they do not clash with data that arrives 7 minutes late and
fills the gap).

### MySQL — DB `mk2` (`mk2_mysql_schema.sql` · `mk2_media_capture.sql`)

| Table | Axis | Written by | Contents |
|---|---|---|---|
| `registry_zone` | declared | operator | Zone tree |
| `registry_entity_declared` | declared | operator | Entities that **should exist** (including not yet deployed) |
| `registry_node_declared` | declared | operator | Physical nodes and their origin placement |
| `registry_entity_observed` | observed | backend | Entities that actually sent values (`status.registration`) |
| `registry_node_observed` | observed | backend | Node reachability (MAC, IP) |
| `registry_identity_history` | observed | backend | Identity change history (append) |
| `audit_log` | audit | backend | Who, when, what, with which result — **cannot be updated or deleted** |
| `mission_event` | run record | backend | Mission event sequence (append-only, the basis for rewind) — **cannot be updated or deleted** |
| `media_capture` | captures | backend | Capture session metadata + original manifest (archives live on the filesystem) |

Conventions (all grounded in the SQL comments):
- All times are **`DATETIME(6)` holding UTC** — `TIMESTAMP` is converted to the session time zone automatically, so it is not used.
- Table collation is **`utf8mb4_bin`** — case-sensitive like TimescaleDB's `TEXT`, so queries joining the two stores do not
  diverge.
- **No foreign keys** — exposing the mismatch between the declared and observed axes (declared only, observed only) is
  itself a requirement. Query: `server/docs/be/queries/registry-declared-vs-observed.sql`.

## 3. Grants — "enforced by the DB", not "promised by the code"

Both app accounts are `mk2_app` and have **no DDL (CREATE, ALTER, DROP) rights anywhere** — the code cannot change the
schema.

| Target | Grants | What it enforces |
|---|---|---|
| TimescaleDB `telemetry` | SELECT, INSERT | There is no path at all to overwrite or delete measurement originals |
| `audit_log` · `mission_event` | SELECT, INSERT | Audit and run records are append-only (BE-S-05 · BE-S-08) |
| `registry_*_observed` · `registry_identity_history` · `media_capture` | SELECT, INSERT, UPDATE | Upsert · retention handling (`purged_at`). No DELETE |
| `registry_*_declared` · `registry_zone` | SELECT | The declared axis is entered by people |

Connection limits:
- MySQL account host = `MK2_DB_APP_HOST` (default `172.28.%`); TimescaleDB `pg_hba` = only `mk2_app` from `MK2_NET_SUBNET`
  (default `172.28.0.0/16`). Compose **pins** the Docker subnet, so recreating the network does not break this.
- The TimescaleDB `postgres` superuser cannot connect over TCP, only through the socket inside the container:
  `docker compose exec timescaledb psql -U postgres -d mk2`.
  (In Windows Git Bash, run `export MSYS_NO_PATHCONV=1` first when a `docker compose exec …` command in this document
  contains a container path — [README.md §2](README.md#2-requirements))

Section 5 of `./scripts/healthcheck.sh` checks these grants on every run by **negative test** (that UPDATE, DELETE and
CREATE are actually refused).

## 4. Schema change procedure (migrations)

The first-time init scripts run **only once, on an empty volume**. Applying changes to a DB that is already in service is the
job of [`deploy/scripts/migrate.sh`](../../deploy/scripts/migrate.sh).

### Tracking the schema version — `schema_migrations`

In both DBs, the table `schema_migrations(version, applied_at, applied_by)` remembers **which migrations have been applied**
(source of truth: `server/infra/sql/mk2_schema_migrations_{mysql,tsdb}.sql`).

| Row | Meaning |
|---|---|
| `00000000_baseline` | The canonical schema at the time tracking was introduced |
| `<file name>` · `applied_by=init` | New server — already part of the canonical schema, so first-time init marks it "applied" |
| `<file name>` · `applied_by=migrate.sh` | Applied by `migrate.sh` |
| `<file name>` · `applied_by=manual` | Left by the self-recording line at the end of the file (applied by hand) |

- Only root (MySQL) and postgres (TimescaleDB) write the table. **The app account `mk2_app` has no rights on it** — there is
  no line for it in `mk2_grants_*.sql.example` (MySQL GRANTs are per table, so without a line it cannot even read it).
  Section 5 of `healthcheck.sh` negative-tests that writes are refused.
- **A server initialized before tracking was introduced** (a volume without the table): `migrate.sh` creates the table and
  marks it `00000000_baseline`. Up to that point the repository had no migration files, so baseline = the server's actual
  schema.

### Procedure

1. **Edit the canonical files** — bring the `CREATE TABLE` in `server/infra/sql/mk2_*.sql` to its final shape. New servers
   are correct with this alone.
2. **Write the change for existing servers separately** — in `server/infra/sql/migrations/`:

   | Engine | File name | Version name |
   |---|---|---|
   | MySQL | `YYYYMMDD_<topic>.sql` | `YYYYMMDD_<topic>` |
   | TimescaleDB | `YYYYMMDD_<topic>_tsdb.sql` | `YYYYMMDD_<topic>_tsdb` |

   - `<topic>` is alphanumerics and `_` only. For several on the same day, number them like `YYYYMMDD_1_<topic>` —
     **apply order = lexical order of file names per engine**. If a name outside the convention exists, `migrate.sh` stops
     (it does not silently skip it).
   - Write them to be safe to re-run (`IF NOT EXISTS`, etc.). MySQL DDL is not transactional, so a failure can leave a
     partial change. `migrate.sh` applies a TimescaleDB file **in one transaction** — do not use statements that must run
     outside a transaction, such as `CREATE INDEX CONCURRENTLY`.
   - Put a **self-recording line** at the end of the file (so a record is left even when applied by hand — `migrate.sh`
     writes the same row idempotently):
     ```sql
     -- MySQL
     INSERT IGNORE INTO mk2.schema_migrations (version, applied_by) VALUES ('20261215_add_foo', 'manual');
     -- TimescaleDB
     INSERT INTO schema_migrations (version, applied_by) VALUES ('20261215_add_foo_tsdb', 'manual') ON CONFLICT DO NOTHING;
     ```
   - For a new table, also add its per-table GRANT to `mk2_grants_*.sql.example` (MySQL GRANT has no table wildcard).
3. **Apply with `migrate.sh`, after a backup** (from `deploy/`):
   ```bash
   ./scripts/backup.sh
   ./scripts/migrate.sh --dry-run    # applied / pending list only — does not change the DB
   ./scripts/migrate.sh              # apply pending ones in order → apply retention/compression policy (§6)
   ```
   It stops at the first error — the failed file is not recorded and later files are not applied. Fix the cause and run it
   again; it continues from what is left. To leave the retention/compression policy alone, add `--no-retention`.
4. **CI rebuilds from the canonical files on an empty DB** and tests it (deploy-smoke) — if the canonical schema and the
   migration result diverge, it shows up there. The same job checks `migrate.sh` reporting "nothing pending", baseline
   handling on a server without the tracking table, applying the retention/compression policy, and that re-runs are
   idempotent.
5. Write "DB migration required" and the file names in the `### Deployment changes` section of that release in
   `CHANGELOG.md` (it goes into the release notes — operators read this section when upgrading:
   [operations.md "Upgrade"](operations.md#upgrade-to-a-new-release)).

> No general-purpose migration tool (Flyway, Alembic and the like) is used — changes are infrequent, and since the grant
> design keeps the app from running DDL, a person applies changes as root; `migrate.sh` (a thin shell script that only lists,
> orders and records) fits that principle.

## 5. Password rotation

The DB passwords in `.env` are set on the accounts **only at first volume initialization**. To change one, change it on the
DB side first, then update `.env` to match.

```bash
cd deploy
NEW=$(LC_ALL=C tr -dc 'A-Za-z0-9' </dev/urandom | head -c 32)
APPHOST=$(grep '^MK2_DB_APP_HOST=' .env | cut -d= -f2)
docker compose exec -T mysql sh -c "mysql -uroot -p\"\$MYSQL_ROOT_PASSWORD\" -e \"ALTER USER 'mk2_app'@'${APPHOST}' IDENTIFIED BY '${NEW}'\""
sed -i "s/^MK2_MYSQL_PASSWORD=.*/MK2_MYSQL_PASSWORD=${NEW}/" .env
docker compose up -d be-ingest be-storage be-gateway be-capture     # recreate with the new value
```

TimescaleDB works the same way (`ALTER ROLE mk2_app WITH PASSWORD '…'` → `MK2_TSDB_PASSWORD`).

## 6. Backup · restore · retention

```bash
# from the repository root
./deploy/scripts/backup.sh                         # → deploy/backups/<UTC>/  (MySQL dump + TimescaleDB pg_dump -Fc + MANIFEST)
./deploy/scripts/restore.sh deploy/backups/<UTC>   # stop backend → restore → re-apply grants → start

# from deploy/ (as in operations.md) — the same scripts
./scripts/backup.sh                                # → also deploy/backups/<UTC>/
./scripts/restore.sh backups/<UTC>
```

- **Either location works.** Without an argument, the backup always lands in `deploy/backups/<UTC time>/` (e.g.
  `deploy/backups/20261026T061500Z/`), wherever you run it from. A path you pass as an argument (backup destination, directory
  to restore) is **relative to where you run the command** (absolute paths work too) — so from the repository root write
  `deploy/backups/<UTC>`, and from `deploy/` write `backups/<UTC>`.
- **Restore confirmation**: before overwriting, `restore.sh` asks `계속할까? [y/N]` ("continue?") and proceeds only on `y`.
  When nobody is there to answer (scripts, cron), skip the question with `--yes` (`-y`):
  `./scripts/restore.sh --yes backups/<UTC>`. If stdin is not a terminal and there is neither `--yes` nor an answer, it prints
  a message telling you to pass `--yes` and exits with 1. Piping the answer also works
  (`echo y | ./scripts/restore.sh backups/<UTC>` — CI does this).
- Every backup prints `pg_dump: warning: there are circular foreign-key constraints on this table: …` followed by `hint: …`
  lines — **this is harmless.** It comes from circular foreign keys between TimescaleDB's internal catalog tables
  (`hypertable`, `chunk`, …); `restore.sh` restores between `timescaledb_pre_restore()` and `timescaledb_post_restore()`, so
  the dump restores cleanly. `backup.sh` also prints a one-line note about it after the dump.
- Verified: 2026-10-26 backup → empty `telemetry` · delete the declared registry → restore → `healthcheck.sh` 32/32 (the
  number of checks at the time — `healthcheck.sh` now has 35 checks and should print `결과: 통과 35 · 실패 0` after a restore;
  CI `deploy-smoke` runs a backup → restore round trip followed by `healthcheck.sh --quick` on every PR).
- Schedule: daily with `cron` (e.g. `0 3 * * * cd /opt/mk2/deploy && ./scripts/backup.sh /backup/mk2/$(date +\%u)` — seven
  rotating copies, one per weekday).
- **Not backed up**: Kafka (only a 7-day buffer, not long-term storage) · Prometheus/Loki/Tempo (the retention period *is*
  the policy) · capture archives (`/data/media_capture` in the `backend_data` volume — large, so back them up at the
  filesystem/snapshot level).
- **`deploy/.env` is not in the backup** — keep it somewhere safe, such as a password manager.

### TimescaleDB retention · compression (optional — off by default)

The policies on the measurement hypertable `telemetry` are set by two values in `deploy/.env`. **Empty means off** (the
default):

| Variable | Meaning | Policy |
|---|---|---|
| `MK2_TSDB_RETENTION_DAYS` | **Permanently delete** chunks older than this | `add_retention_policy(drop_after)` |
| `MK2_TSDB_COMPRESS_AFTER_DAYS` | Compress chunks older than this (columnar storage — usually several times smaller) | `add_compression_policy(compress_after)` |

```bash
# deploy/.env
MK2_TSDB_RETENTION_DAYS=365
MK2_TSDB_COMPRESS_AFTER_DAYS=7

./scripts/apply-retention.sh --dry-run   # current policy and desired values
./scripts/apply-retention.sh             # apply (migrate.sh also calls this at the end — once per deployment)
```

- **Declarative, safe to re-run**: if the values are unchanged it does nothing; if they changed it removes the policy and
  sets it again with the new value (one transaction). Emptying a value removes that policy — chunks already dropped do not
  come back, and compressed chunks are not decompressed.
- When compression is first enabled it sets `segmentby = stream_topic, stream_partition` ·
  `orderby = ts DESC, stream_offset DESC` — because the columns of the unique key
  (`ts, stream_topic, stream_partition, stream_offset`) must be in segmentby/orderby. TimescaleDB handles late data landing
  in compressed chunks (`ON CONFLICT DO NOTHING` idempotency is kept). Set the compression delay comfortably longer than the
  usual late arrival (spool retransmission).
- Check: `docker compose exec timescaledb psql -U postgres -d mk2 -c "SELECT job_id, proc_name, config FROM timescaledb_information.jobs WHERE hypertable_name='telemetry'"`
- ⚠ Before enabling retention, check the institution's retention obligations (disaster data) and the backup schedule —
  measurements older than the retention period remain only in backups. Free disk space is watched by the
  `DataVolumeDiskUsageHigh` alert (85%) ([observability.md §4](../deployment/observability.md), Korean).
