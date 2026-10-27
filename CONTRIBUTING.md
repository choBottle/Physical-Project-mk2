# Contributing to Physical-Project-mk2

Bug reports, documentation fixes, tests, device adapters and deployment
reports from other sites are welcome. Issues and pull requests may be written
in English or Korean.

For a substantial change, open an issue first. A change to any of the
following needs agreement in an issue before implementation, because several
parts and outside deployments depend on them:

- the common data contracts in `server/contracts/common/`
- MQTT topic structure and Kafka topics
- the database schema
- deployment environment variables and ports

[GOVERNANCE.md](GOVERNANCE.md) describes how those decisions are made.

## Development setup

Start the central stack locally so that development and deployment use the
same configuration:

```bash
cd deploy
./scripts/init-env.sh
docker compose up -d --build --wait
./scripts/healthcheck.sh
```

Then read the README of the part you are changing. Some parts have their own
conventions, such as requirement IDs in comments or a report format.

Per-part toolchains:

- `ai/perception-framework`, `drone/`: Python 3.10 or later in a virtual
  environment
- `visualization/viz-debugger`: Node.js 22
- `hardware/pi`: Raspberry Pi OS; most node code also runs on a desktop with
  the simulated inputs described in the part's documentation

## Tests

Run the tests for the parts you touched. These are the commands CI runs:

| Scope | Command |
|-------|---------|
| Deployment | `cd deploy && ./scripts/healthcheck.sh && ./scripts/e2e-sim.sh` |
| Backend regression | `cd deploy && docker compose exec -e MK2_PROMETHEUS_URL=http://prometheus:9090 -e MK2_LOKI_URL=http://loki:3100 -e MK2_TEMPO_URL=http://tempo:3200 be-gateway python -m pytest -q` |
| AI | `cd ai/perception-framework && pip install -e ".[dev,mqtt,kafka,otel,sim]" && OTEL_SDK_DISABLED=true python -m pytest -q` |
| Console contracts | `cd visualization/contracts && python validate_examples.py` |
| Drone | `cd drone && pip install -e ".[test,image,base]" && python -m pytest -q` |
| Operator console | `cd visualization/viz-debugger && npm ci && npm run typecheck && npm run build && npm run verify:sar` |

`verify:service-words` in the console fails on machines without the local
speech service; that failure is known and does not block a pull request.

## Pull requests

- Keep each pull request focused on one change, on a branch named
  `<part>/<topic>` (for example `server/availability-judge`).
- Use [Conventional Commits](https://www.conventionalcommits.org/) for commit
  messages: `feat(server): ...`, `fix(deploy): ...`, `docs: ...`.
- Add or update tests for behavior changes. A new data path should also get a
  check in `deploy/scripts/healthcheck.sh`.
- If the change affects deployment (a new environment variable, port,
  database change or image version), update `deploy/`, `docs/` and the
  "Deployment changes" section of `CHANGELOG.md` in the same pull request.
- Do not commit secrets, real IP addresses, tailnet host names, home
  directory paths, or photos that show identifiable people or precise
  locations. The secret scan in CI checks the incoming commits.
- CI must pass, and a maintainer of each affected folder
  (`.github/CODEOWNERS`) must approve.

## Deployment rules

| Avoid | Do instead |
|-------|------------|
| Addresses, paths or ports written into code | An environment variable with a placeholder in `.env.example` |
| Editing a server by hand without committing the change | Commit the configuration; keep only secrets in `.env` |
| `:latest` image tags | Pin the version |
| Treating "the container is up" as success | Check that data flows, and add the check to `healthcheck.sh` |
| Opening a new port | Check and update [docs/PORTS.md](docs/PORTS.md) |
| `ALTER TABLE` on a running server | Update the canonical SQL and add a migration file ([database.md](docs/deployment/database.md)) |

## Third-party code

If you bring in code under another license, record its source and license in
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). Code with an unclear license
is not accepted.

By contributing, you agree that your contribution is licensed under the
project's [MIT License](LICENSE).

Participation is governed by the [Code of Conduct](CODE_OF_CONDUCT.md).
Maintainers prepare releases with the checklist in
[docs/RELEASE.md](docs/RELEASE.md).
