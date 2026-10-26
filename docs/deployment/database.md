# 데이터베이스 — 스키마 · 권한 · 변경 · 백업

> 정본(단일 출처): [`server/infra/sql/`](../../server/infra/sql/). 이 문서는 지도이고, 칼럼 하나하나의 근거는 SQL 파일의
> 주석에 있다. 배포는 그 파일을 **직접** 읽어 적용한다(사본 없음 — 두 벌이 되면 조용히 갈라진다).

## 1. 왜 저장소가 둘인가

데이터의 **성격**이 저장소를 정한다(아키텍처 원칙 4).

| 데이터 | 저장소 | 이유 |
|---|---|---|
| 센서 계측 · 로봇/액추에이터 상태 추이 | **TimescaleDB** (PostgreSQL 16 확장) | 시간축 위의 수치. 유실·역전 검출이 윈도우 함수(SQL)로 풀린다. 보존·압축 정책을 하이퍼테이블에 붙인다 |
| 명령 감사 · 임무 실행 기록 · 레지스트리 · 촬영본 메타 | **MySQL 8.4** | 관계형·준정적. append-only 를 **DB 권한**으로 강제한다 |
| metric · log · trace | Prometheus · Loki · Tempo | 관측 평면 — [observability.md](observability.md) |
| 트윈 상태 · 명령 진행 · 장치 가용성 | 저장 안 함 | 도착 즉시 WS 로 push |

**정직한 약점:** 관계형 엔진이 둘이라 백업·계정·모니터링이 두 벌이다. 교체 지점은 `server/backend/storage/tsdb_writer.py`
한 파일이라 잠금 범위는 좁다.

## 2. 스키마

### TimescaleDB — DB `mk2` (`mk2_tsdb_schema.sql`)

`telemetry` 하이퍼테이블 하나(시간축 `ts` = **발행 시각** — 늦게 도착한 데이터가 원래 측정 시각 자리에 꽂힌다).

| 칼럼 묶음 | 칼럼 |
|---|---|
| 시간축 · 라우팅 | `ts` · `channel` · `entity_type` |
| 공통 헤더 | `source_id` · `node_id` · `zone_id` · `entity_id` · `session_id` · `sequence_id` · `schema_version` · `origin_kind` |
| 시각 3종 · 파생 | `ingest_at` · `received_at` · `lag_s` · `clock_skew` · `replayed` |
| 본문 공통 | `reason` · `device_status` |
| 멱등 키 | `stream_topic` · `stream_partition` · `stream_offset` (UNIQUE — Kafka 재전달에도 중복 없음) |
| 원본 | `payload` (JSONB — 메시지 전체를 그대로) |

원칙: **원본 그대로 넣고 검출은 조회에서 한다** — 갭·유실은 적재 때 판정하지 않고 `server/docs/be/queries/gap-detection.sql`
의 `LAG()` 로 계산한다(7분 늦게 도착해 갭을 메울 데이터와 충돌하지 않게).

### MySQL — DB `mk2` (`mk2_mysql_schema.sql` · `mk2_media_capture.sql`)

| 테이블 | 축 | 쓰는 주체 | 내용 |
|---|---|---|---|
| `registry_zone` | 선언 | 운영자 | 구역 트리 |
| `registry_entity_declared` | 선언 | 운영자 | **존재해야 할** 개체 목록(미배포 포함) |
| `registry_node_declared` | 선언 | 운영자 | 물리 노드와 원점 배치 |
| `registry_entity_observed` | 관측 | 백엔드 | 실제로 값을 보내온 개체(`status.registration`) |
| `registry_node_observed` | 관측 | 백엔드 | 노드 도달 정보(MAC·IP) |
| `registry_identity_history` | 관측 | 백엔드 | 신원 변경 이력(append) |
| `audit_log` | 감사 | 백엔드 | 누가·언제·무엇을·어떤 결과로 — **수정·삭제 불가** |
| `mission_event` | 실행 기록 | 백엔드 | 임무 사건 열(append-only, 되감기의 근거) — **수정·삭제 불가** |
| `media_capture` | 촬영본 | 백엔드 | 촬영 세션 메타 + 매니페스트 원본(아카이브는 파일시스템) |

규약(전부 SQL 주석에 근거):
- 시각은 전부 **UTC 를 담은 `DATETIME(6)`** — `TIMESTAMP` 는 세션 타임존으로 자동 변환돼 쓰지 않는다.
- 테이블 collation 은 **`utf8mb4_bin`** — TimescaleDB 의 `TEXT` 처럼 대소문자를 구별해야 두 저장소를 잇는 조회가 어긋나지 않는다.
- **FK 를 걸지 않는다** — 선언 축과 관측 축의 불일치(선언만 있는 것 · 관측만 있는 것)를 드러내는 것 자체가 요구사항이다.
  조회: `server/docs/be/queries/registry-declared-vs-observed.sql`.

## 3. 권한 — "코드가 약속"이 아니라 "DB 가 강제"

앱 계정은 둘 다 `mk2_app` 이며 **DDL(CREATE·ALTER·DROP) 권한이 어디에도 없다** — 코드가 스키마를 바꿀 수 없다.

| 대상 | 권한 | 강제하는 것 |
|---|---|---|
| TimescaleDB `telemetry` | SELECT, INSERT | 계측 원본을 덮어쓰거나 지울 경로 자체가 없다 |
| `audit_log` · `mission_event` | SELECT, INSERT | 감사·실행 기록 append-only (BE-S-05 · BE-S-08) |
| `registry_*_observed` · `registry_identity_history` · `media_capture` | SELECT, INSERT, UPDATE | upsert · 보존 처리(`purged_at`). DELETE 없음 |
| `registry_*_declared` · `registry_zone` | SELECT | 선언 축은 사람이 넣는다 |

접속 제한:
- MySQL 계정 host = `MK2_DB_APP_HOST`(기본 `172.28.%`), TimescaleDB `pg_hba` = `MK2_NET_SUBNET`(기본 `172.28.0.0/16`)의 `mk2_app` 만.
  compose 가 도커 대역을 **고정**하므로 네트워크를 다시 만들어도 깨지지 않는다.
- TimescaleDB `postgres` 슈퍼유저는 TCP 로 못 붙고 컨테이너 안 소켓으로만: `docker compose exec timescaledb psql -U postgres -d mk2`.

`./scripts/healthcheck.sh` 5번 절이 이 권한을 **음성 대조**(UPDATE·DELETE·CREATE 가 실제로 거부되는지)로 매번 확인한다.

## 4. 스키마 변경 절차 (마이그레이션)

최초 초기화 스크립트는 **빈 볼륨에서 한 번만** 돈다. 이미 운영 중인 DB 에 변경을 반영하는 규칙:

1. **정본 파일을 고친다** — `server/infra/sql/mk2_*.sql` 의 `CREATE TABLE` 을 최종 모양으로. 새 서버는 이것만으로 맞는다.
2. **기존 서버용 변경분을 따로 쓴다** — `server/infra/sql/migrations/YYYYMMDD_<주제>.sql` (`ALTER …`, 재실행 안전하게).
   새 테이블이면 테이블별 GRANT 를 `mk2_grants_*.sql.example` 에도 더한다(MySQL GRANT 에는 테이블 와일드카드가 없다).
3. **적용은 사람이 root 로**, 백업 뒤에:
   ```bash
   ./deploy/scripts/backup.sh
   docker compose -f deploy/docker-compose.yml exec -T mysql sh -c 'mysql -uroot -p"$MYSQL_ROOT_PASSWORD"' \
     < server/infra/sql/migrations/20261101_example.sql
   docker compose -f deploy/docker-compose.yml exec -T timescaledb psql -U postgres -d mk2 -v ON_ERROR_STOP=1 \
     < server/infra/sql/migrations/20261101_example_tsdb.sql
   ```
4. **CI 가 빈 DB 에서 정본으로 다시 세워** 시험한다(deploy-smoke) — 정본과 마이그레이션 결과가 갈라지면 여기서 드러난다.
5. `CHANGELOG.md` 에 "DB 변경 — 마이그레이션 필요"로 적는다(릴리스 노트에 올라간다).

> 자동 마이그레이션 도구(Flyway·Alembic 류) 도입은 v1.x 로드맵 항목이다([RELEASE.md](../RELEASE.md)). 지금은 변경 빈도가
> 낮고, 권한 설계상 앱이 DDL 을 못 하므로 사람 적용이 원칙에도 맞는다.

## 5. 비밀번호 교체

`.env` 의 DB 비밀번호는 **볼륨 최초 초기화 때만** 계정에 박힌다. 바꿀 때는 DB 쪽을 먼저 바꾸고 `.env` 를 맞춘다.

```bash
cd deploy
NEW=$(LC_ALL=C tr -dc 'A-Za-z0-9' </dev/urandom | head -c 32)
APPHOST=$(grep '^MK2_DB_APP_HOST=' .env | cut -d= -f2)
docker compose exec -T mysql sh -c "mysql -uroot -p\"\$MYSQL_ROOT_PASSWORD\" -e \"ALTER USER 'mk2_app'@'${APPHOST}' IDENTIFIED BY '${NEW}'\""
sed -i "s/^MK2_MYSQL_PASSWORD=.*/MK2_MYSQL_PASSWORD=${NEW}/" .env
docker compose up -d be-ingest be-storage be-gateway be-capture     # 새 값으로 재생성
```

TimescaleDB 도 같은 방식(`ALTER ROLE mk2_app WITH PASSWORD '…'` → `MK2_TSDB_PASSWORD`).

## 6. 백업 · 복구 · 보존

```bash
./deploy/scripts/backup.sh                         # → deploy/backups/<UTC>/  (MySQL 덤프 + TimescaleDB pg_dump -Fc + MANIFEST)
./deploy/scripts/restore.sh deploy/backups/<UTC>   # 백엔드 정지 → 복구 → 권한 재적용 → 기동
```

- 검증: 2026-10-26 백업 → `telemetry` 비우기 · 선언 레지스트리 삭제 → 복구 → `healthcheck.sh` 32/32.
- 주기: `cron` 으로 매일(예: `0 3 * * * cd /opt/mk2/deploy && ./scripts/backup.sh /backup/mk2/$(date +\%u)` — 요일별 7개 순환).
- **백업하지 않는 것**: Kafka(7일 버퍼일 뿐 장기 저장소가 아니다) · Prometheus/Loki/Tempo(보존 기간이 곧 정책) ·
  촬영본 아카이브(`backend_data` 볼륨의 `/data/media_capture` — 용량이 커서 파일시스템/스냅샷 수준 백업 대상).
- **`deploy/.env` 는 백업에 들어가지 않는다** — 비밀번호 관리 도구 등 별도 안전한 곳에 둔다.
- TimescaleDB 보존·압축 정책은 아직 없다(BE-S-04, 발동 조건 미충족). 하이퍼테이블이라 정책만 붙이면 된다:
  `SELECT add_retention_policy('telemetry', INTERVAL '365 days');`
