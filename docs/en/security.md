# Security · exposure policy

> Translated from the Korean source [docs/deployment/security.md](../deployment/security.md) at commit
> [`3fcbcf4`](https://github.com/choBottle/Physical-Project-mk2/blob/3fcbcf4b5de212d64e81fd077f1481d0e00e7d59/docs/deployment/security.md);
> if they disagree, the Korean document is authoritative. The Korean document is being revised (MQTT credentials for the
> backend) — check it for anything newer than that commit.

> The current profile is **"trusted members inside the tunnel"**. **1.0.x supports only deployments inside a private
> network or tunnel** ([RELEASE.md §3](../RELEASE.md), Korean).
> Authentication and authorization (RBAC, BE-Q-04) and transport encryption (TLS/SASL) are 1.1.0 goals.
> Until then, this document states plainly **what is protected and what is not yet**. To report a vulnerability, see
> [SECURITY.md](../../SECURITY.md).

## 1. Exposure principle — the bind address is the control

| Group | Ports | Default bind | Authentication |
|---|---|---|---|
| Edge entry (`MK2_EDGE_BIND`) | MQTT 1883 · MQTT/WS 9001 · OTLP 4316/4317/4318 | `127.0.0.1` | **None** (anonymous MQTT, plaintext OTLP) |
| Kafka EDGE (`MK2_KAFKA_EDGE_BIND`) | 9095 | `127.0.0.1` | **None** (PLAINTEXT). Not used by edges in 1.0, so no need to open it |
| Backend entry (`MK2_EDGE_BIND`) | WS 8765 · media 8766 · capture 8767 | `127.0.0.1` | URL query token (`MK2_WS_TOKEN`, `MK2_EDGE_TOKEN`, `MK2_CAPTURE_TOKEN`) |
| Operator (`MK2_ADMIN_BIND`) | Grafana · Prometheus · Loki · Tempo · MySQL · TimescaleDB | `127.0.0.1` | Grafana account · DB accounts (none for Prometheus, Loki, Tempo) |
| Internal only | Kafka 9092 | `127.0.0.1` fixed | None |

- Ports published by Docker are processed **before** the host firewall (ufw). The effective control is therefore **the bind
  address in compose**, not ufw rules. Always bind the edge entry to the **tunnel address**; never use `0.0.0.0`.
- Do not expose operator UIs outside the server. Remotely, use `ssh -L 7862:127.0.0.1:7862 <server>`.
- The backend **refuses to start** (exit 2) when bound to a non-loopback address with an empty token.

## 2. Secrets

- All in one place, `deploy/.env` (mode 600, gitignored). `scripts/init-env.sh` generates 32-character alphanumerics.
- Alphanumerics only — each parser that reads `.env` (shell, compose, systemd) treats special characters differently.
- Never put real addresses or tokens in the repository, issues or chat. Use placeholders such as `<central tunnel address>`
  in documents.
- The DB app account has no DDL and no UPDATE/DELETE on audit and run records — a compromised app cannot alter the record
  ([database.md §3](../deployment/database.md), Korean).

## 3. Production checklist (outside a tunnel · multi-institution · public deployment)

| # | Item | Current | Action |
|---|---|---|---|
| 1 | MQTT authentication | Anonymous | Copy `deploy/site/mosquitto/auth.conf.example` for password_file + ACL. However, the backend (be-ingest) has no MQTT account setting yet, so enabling it disconnects the backend — 1.1.0 ([#29](https://github.com/choBottle/Physical-Project-mk2/issues/29)) |
| 2 | MQTT TLS | None | 8883 listener + certificates |
| 3 | Kafka EDGE | PLAINTEXT | SASL_SSL (together with BE-Q-04) |
| 4 | OTLP ingest authentication | None | Collector `bearertokenauth` extension, token on edge Collectors |
| 5 | WS token → user authentication | Shared token | RBAC (BE-Q-04) · WSS |
| 6 | Grafana | Local admin | SSO/OIDC, rotate the admin password |
| 7 | Prometheus/Loki/Tempo API | No auth (local bind) | Reverse proxy + auth, or keep local |
| 8 | Image supply chain | Pinned version tags | Pin by digest (`image@sha256:…`) + vulnerability scan (CI) |
| 9 | Backup encryption | Plaintext dumps | Encrypt the backup storage · access control |
| 10 | Personal and location data | May be present in video, captures, SAR data | Retention and access policy; no raw data in the public repository |

## 4. Public repository rules

This repository is public. Before committing:
- Check that `git diff --staged` contains no IPs, tokens, `/home/<user>` paths or internal hostnames (CI's secret scan is
  the second line of defence).
- Check that photos, videos and screenshots show no faces, non-public facilities or precise locations.
- If something was pushed by mistake, a deleting commit is not enough — **rotate that value immediately** and tell the
  maintainers.
