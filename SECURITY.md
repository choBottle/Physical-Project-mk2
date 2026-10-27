# Security policy

## Supported versions

Security fixes are applied to the latest release and to the `main` branch.
Release candidates and older releases may not receive a backport; upgrade to
the latest release instead.

## Reporting a vulnerability

Please do not open a public issue for a suspected vulnerability. Use GitHub's
private vulnerability reporting for this repository (**Security** tab, then
**Report a vulnerability**) and include:

- the affected version or commit;
- steps to reproduce the issue;
- the expected impact; and
- any suggested mitigation.

Do not include real credentials, tokens, IP addresses of a deployment, or
unrelated personal information in the report. The maintainers aim to
acknowledge a report within seven days and to share an assessment and a plan
within fourteen days, then coordinate disclosure with the reporter after a
fix or mitigation is available.

## Current security model

The platform assumes that every client is inside a trusted private network or
tunnel (Tailscale in the reference deployment). The following are known
properties of the current design, not vulnerabilities:

- MQTT accepts anonymous clients.
- OTLP and Kafka connections are plaintext.
- There is no user authentication or role-based access control.

Exposure is controlled by the bind addresses `MK2_EDGE_BIND` and
`MK2_ADMIN_BIND`, by tokens on the WebSocket gateway and the capture upload
endpoint, and by database grants that prevent the application account from
changing audit and mission records. A way to bypass one of these documented
controls is in scope for a report. Authentication, RBAC and TLS are on the
1.x roadmap. See [docs/deployment/security.md](docs/deployment/security.md)
for the exposure policy and the production checklist.

## If a secret was committed

1. Rotate the secret immediately. A commit that deletes it does not remove it
   from the history.
2. Tell the maintainers through a private vulnerability report.

For ordinary bugs and usage questions, use
[GitHub Issues](https://github.com/choBottle/Physical-Project-mk2/issues).
