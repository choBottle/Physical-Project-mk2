# Governance

## Roles

| Role | Responsibilities |
|------|------------------|
| Contributor | Opens issues and pull requests and reviews them. Anyone can be a contributor. |
| Part maintainer | Approves and merges pull requests for one folder and sets that part's roadmap. Listed in `.github/CODEOWNERS`. |
| Platform maintainer | Makes the final decision on agreements that cross parts (data contracts, deployment, releases) and tags releases. |

## Current maintainers

| Area | Folders | Maintainer |
|------|---------|------------|
| Backend, common data contracts, database schema | `server/` | @daegyu10 |
| Hardware and edge nodes | `hardware/` | @choBottle |
| AI | `ai/` | @JNY03 |
| Visualization and operator console | `visualization/`, `osmocam/` | @khw18033 |
| Drone | `drone/` | jhjeong (GitHub account to be confirmed) |
| 360-degree camera | `camera360/` | @daegyu10 |
| Deployment, releases, project operations | `deploy/`, `docs/`, `.github/` | @choBottle, with review by the backend maintainer |

New maintainers are added from active contributors by a majority of the
current maintainers. A maintainer who has been inactive for six months
becomes an emeritus maintainer.

## Decisions

1. **Within a part.** The part maintainer decides.
2. **Across parts.** Changes to the common data contracts, MQTT or Kafka
   topics, the database schema, ports, deployment environment variables or
   the license follow this process:
   - Open an issue with the `rfc` label and mention the maintainers of every
     affected part.
   - Leave it open for comments for seven days.
   - If no maintainer objects, the proposal is accepted. If there is an
     objection, the maintainers vote; a tie is decided by the platform
     maintainer.
   - The backend owns the canonical data contracts in
     `server/contracts/common/`. Other parts follow them and use this process
     to change them.
3. Decisions are recorded in the issue and reflected in the design documents.

## Adopting organizations

Organizations that deploy the platform are encouraged to say so in an issue
with the `adopter` label. Site requirements such as offline operation,
security classification and device types are the main input to the roadmap.
Site-specific configuration and data stay out of this repository; only
general improvements are accepted as pull requests.
