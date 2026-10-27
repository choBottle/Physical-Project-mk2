## What and why

<!-- Related issue: #123 -->

## Parts

- [ ] server  - [ ] hardware  - [ ] ai  - [ ] visualization  - [ ] drone  - [ ] camera360  - [ ] osmocam  - [ ] deploy/docs

## Deployment impact

If any of these apply, update the documentation in the same pull request.

- [ ] New or changed environment variable: `deploy/.env.example` and the part's `.env.example`
- [ ] New or changed port: `docs/PORTS.md` and the Compose files
- [ ] Database schema change: canonical SQL in `server/infra/sql/`, a file in `migrations/`, grants, `docs/deployment/database.md`
- [ ] Data contract or MQTT/Kafka topic change: link to the agreed `rfc` issue:
- [ ] Image version change: pinned version in the Compose files, CI `validate` passes
- [ ] New data path: a check in `deploy/scripts/healthcheck.sh`
- [ ] None of the above

## Checklist

- [ ] `CHANGELOG.md` `[Unreleased]` updated (deployment changes in "Deployment changes")
- [ ] No secrets, real IP addresses, tailnet host names or `/home/<user>` paths in the diff
- [ ] No photos or videos with identifiable people or precise locations
- [ ] Tested locally: <!-- for example: ./deploy/scripts/healthcheck.sh 32/32, pytest ... -->
