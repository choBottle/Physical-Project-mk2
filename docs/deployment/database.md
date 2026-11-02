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
  (Windows Git Bash 에서 이 문서의 `docker compose exec …` 명령에 컨테이너 안 경로가 들어가면 먼저 `export MSYS_NO_PATHCONV=1`
  — [README.md §2](README.md#2-요구-사양))

`./scripts/healthcheck.sh` 5번 절이 이 권한을 **음성 대조**(UPDATE·DELETE·CREATE 가 실제로 거부되는지)로 매번 확인한다.

## 4. 스키마 변경 절차 (마이그레이션)

최초 초기화 스크립트는 **빈 볼륨에서 한 번만** 돈다. 이미 운영 중인 DB 에 변경을 반영하는 것은
[`deploy/scripts/migrate.sh`](../../deploy/scripts/migrate.sh) 이다.

### 스키마 판 추적 — `schema_migrations`

두 DB 모두 `schema_migrations(version, applied_at, applied_by)` 표가 **어느 마이그레이션이 적용됐는지**를 기억한다
(정본: `server/infra/sql/mk2_schema_migrations_{mysql,tsdb}.sql`).

| 행 | 뜻 |
|---|---|
| `00000000_baseline` | 추적 도입 시점의 정본 스키마 |
| `<파일 이름>` · `applied_by=init` | 새 서버 — 정본에 이미 들어 있어 최초 초기화가 "적용됨"으로 표시 |
| `<파일 이름>` · `applied_by=migrate.sh` | `migrate.sh` 가 적용 |
| `<파일 이름>` · `applied_by=manual` | 파일 끝의 자기 기록 줄로 남은 것(손으로 적용한 경우) |

- 표는 root(MySQL)·postgres(TimescaleDB)만 쓴다. **앱 계정 `mk2_app` 에는 권한이 없다** — `mk2_grants_*.sql.example` 에
  줄을 두지 않는다(MySQL GRANT 는 테이블 단위라 줄이 없으면 읽기도 못 한다). `healthcheck.sh` 5번 절이 쓰기 거부를 음성 대조한다.
- **추적 도입 전에 초기화된 서버**(표가 없는 볼륨): `migrate.sh` 가 표를 만들고 `00000000_baseline` 으로 표시한다. 이
  시점까지 저장소에 마이그레이션 파일이 없었으므로 baseline = 그 서버의 실제 스키마다.

### 절차

1. **정본 파일을 고친다** — `server/infra/sql/mk2_*.sql` 의 `CREATE TABLE` 을 최종 모양으로. 새 서버는 이것만으로 맞는다.
2. **기존 서버용 변경분을 따로 쓴다** — `server/infra/sql/migrations/` 에:

   | 엔진 | 파일 이름 | 판 이름(version) |
   |---|---|---|
   | MySQL | `YYYYMMDD_<주제>.sql` | `YYYYMMDD_<주제>` |
   | TimescaleDB | `YYYYMMDD_<주제>_tsdb.sql` | `YYYYMMDD_<주제>_tsdb` |

   - `<주제>` 는 영숫자·`_` 만. 같은 날 여러 개면 `YYYYMMDD_1_<주제>` 처럼 번호를 붙인다 — **적용 순서 = 엔진별 파일 이름 사전순**.
     규약 밖 이름이 있으면 `migrate.sh` 가 멈춘다(조용히 건너뛰지 않는다).
   - 재실행 안전하게 쓴다(`IF NOT EXISTS` 등). MySQL DDL 은 트랜잭션이 안 돼 실패 시 일부만 반영될 수 있다.
     TimescaleDB 파일은 `migrate.sh` 가 **한 트랜잭션**으로 넣는다 — `CREATE INDEX CONCURRENTLY` 처럼 트랜잭션 밖 문장은 쓰지 않는다.
   - 파일 끝에 **자기 기록 줄**을 둔다(손으로 적용해도 기록이 남게 — `migrate.sh` 도 같은 행을 멱등하게 남긴다):
     ```sql
     -- MySQL
     INSERT IGNORE INTO mk2.schema_migrations (version, applied_by) VALUES ('20261215_add_foo', 'manual');
     -- TimescaleDB
     INSERT INTO schema_migrations (version, applied_by) VALUES ('20261215_add_foo_tsdb', 'manual') ON CONFLICT DO NOTHING;
     ```
   - 새 테이블이면 테이블별 GRANT 를 `mk2_grants_*.sql.example` 에도 더한다(MySQL GRANT 에는 테이블 와일드카드가 없다).
3. **적용은 백업 뒤 `migrate.sh` 로** (`deploy/` 에서):
   ```bash
   ./scripts/backup.sh
   ./scripts/migrate.sh --dry-run    # 적용됨 / 대기 목록만 — DB 를 바꾸지 않는다
   ./scripts/migrate.sh              # 대기분을 순서대로 적용 → 보존·압축 정책 반영(§6)
   ```
   첫 오류에서 멈춘다 — 실패한 파일은 기록되지 않고 그 뒤 파일은 적용하지 않는다. 원인을 고친 뒤 다시 실행하면 남은 것부터 이어 간다.
   보존·압축 정책을 건드리지 않으려면 `--no-retention`.
4. **CI 가 빈 DB 에서 정본으로 다시 세워** 시험한다(deploy-smoke) — 정본과 마이그레이션 결과가 갈라지면 여기서 드러난다.
   같은 잡이 `migrate.sh` 의 "대기 0"·추적표 없는 서버의 baseline 처리·보존/압축 정책 반영과 재실행 멱등을 확인한다.
5. `CHANGELOG.md` 해당 판의 `### Deployment changes` 절에 "DB migration required" 와 파일 이름을 적는다(릴리스 노트에
   올라간다 — 운영자는 업그레이드 때 이 절을 본다: [operations.md 「업그레이드」](operations.md#업그레이드-새-릴리스로)).

> 범용 마이그레이션 도구(Flyway·Alembic 류)는 쓰지 않는다 — 변경 빈도가 낮고, 권한 설계상 앱이 DDL 을 못 하므로
> 사람이 root 로 적용하는 원칙에 `migrate.sh`(목록·순서·기록만 하는 얇은 셸)가 맞는다.

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
# 저장소 루트에서
./deploy/scripts/backup.sh                         # → deploy/backups/<UTC>/  (MySQL 덤프 + TimescaleDB pg_dump -Fc + MANIFEST)
./deploy/scripts/restore.sh deploy/backups/<UTC>   # 백엔드 정지 → 복구 → 권한 재적용 → 기동

# deploy/ 에서 (operations.md 의 방식) — 같은 스크립트다
./scripts/backup.sh                                # → 역시 deploy/backups/<UTC>/
./scripts/restore.sh backups/<UTC>
```

- **어디서 실행해도 된다.** 인자 없이 부르면 백업은 실행 위치와 상관없이 항상 `deploy/backups/<UTC 시각>/`(예:
  `deploy/backups/20261026T061500Z/`)에 생긴다. 인자로 준 경로(백업 위치·복구할 디렉터리)는 **명령을 실행한 위치 기준**이다
  (절대경로도 된다) — 그래서 저장소 루트에서는 `deploy/backups/<UTC>`, `deploy/` 에서는 `backups/<UTC>` 로 쓴다.
- **복구 확인 질문**: `restore.sh` 는 덮어쓰기 전에 `계속할까? [y/N]` 을 묻고 `y` 일 때만 진행한다. 스크립트·cron 처럼
  사람이 없으면 `--yes`(`-y`)로 질문을 건너뛴다: `./scripts/restore.sh --yes backups/<UTC>`. 표준입력이 터미널이 아닌데
  `--yes` 도 입력도 없으면 `--yes` 를 주라는 안내를 찍고 1 로 끝난다. 파이프로 답을 넣는 것도 된다(`echo y | ./scripts/restore.sh backups/<UTC>` — CI 가 이렇게 쓴다).
- 백업 중 `pg_dump: warning: there are circular foreign-key constraints on this table: …` 와 `hint: …` 가 매번 찍힌다 —
  **무해하다.** TimescaleDB 내부 카탈로그 표(`hypertable`·`chunk` 등)의 순환 외래키 때문이고, `restore.sh` 가
  `timescaledb_pre_restore()`/`timescaledb_post_restore()` 사이에서 풀어 문제없이 복구된다. `backup.sh` 도 덤프 뒤 이 안내를 한 줄 찍는다.
- 검증: 2026-10-26 백업 → `telemetry` 비우기 · 선언 레지스트리 삭제 → 복구 → `healthcheck.sh` 32/32(당시 항목 수 — 현재
  `healthcheck.sh` 는 35항목이고 복구 뒤에도 `결과: 통과 35 · 실패 0` 이어야 한다. CI `deploy-smoke` 는 매 PR 백업 → 복구 왕복 뒤 `healthcheck.sh --quick` 을 돌린다).
- 주기: `cron` 으로 매일(예: `0 3 * * * cd /opt/mk2/deploy && ./scripts/backup.sh /backup/mk2/$(date +\%u)` — 요일별 7개 순환).
- **백업하지 않는 것**: Kafka(7일 버퍼일 뿐 장기 저장소가 아니다) · Prometheus/Loki/Tempo(보존 기간이 곧 정책) ·
  촬영본 아카이브(`backend_data` 볼륨의 `/data/media_capture` — 용량이 커서 파일시스템/스냅샷 수준 백업 대상).
- **`deploy/.env` 는 백업에 들어가지 않는다** — 비밀번호 관리 도구 등 별도 안전한 곳에 둔다.

### TimescaleDB 보존 · 압축 (선택 — 기본 꺼짐)

계측 하이퍼테이블 `telemetry` 에 붙는 정책을 `deploy/.env` 두 값으로 정한다. **비우면 끔**(기본):

| 변수 | 뜻 | 정책 |
|---|---|---|
| `MK2_TSDB_RETENTION_DAYS` | 이보다 오래된 청크를 **영구 삭제** | `add_retention_policy(drop_after)` |
| `MK2_TSDB_COMPRESS_AFTER_DAYS` | 이보다 오래된 청크를 압축(컬럼 저장 — 보통 수 배 작아진다) | `add_compression_policy(compress_after)` |

```bash
# deploy/.env
MK2_TSDB_RETENTION_DAYS=365
MK2_TSDB_COMPRESS_AFTER_DAYS=7

./scripts/apply-retention.sh --dry-run   # 지금 정책과 원하는 값
./scripts/apply-retention.sh             # 반영 (migrate.sh 도 끝에 이것을 부른다 — 배포 때 한 번)
```

- **선언형·재실행 안전**: 값이 같으면 아무것도 하지 않고, 바뀌면 정책을 지우고 새 값으로 다시 건다(한 트랜잭션).
  값을 비우면 그 정책을 지운다 — 이미 지워진 청크는 돌아오지 않고, 압축된 청크는 풀지 않는다.
- 압축은 처음 켤 때 `segmentby = stream_topic, stream_partition` · `orderby = ts DESC, stream_offset DESC` 로 설정한다 —
  유일 키(`ts, stream_topic, stream_partition, stream_offset`)의 칼럼이 segmentby/orderby 에 있어야 해서다. 늦게 도착한
  데이터가 압축 청크에 들어가는 것은 TimescaleDB 가 처리한다(`ON CONFLICT DO NOTHING` 멱등 유지). 압축 시점은 보통의
  지연 도착(spool 재전송)보다 넉넉히 길게 잡는다.
- 확인: `docker compose exec timescaledb psql -U postgres -d mk2 -c "SELECT job_id, proc_name, config FROM timescaledb_information.jobs WHERE hypertable_name='telemetry'"`
- ⚠ 보존을 켜기 전에 기관의 보존 의무(재난 데이터)와 백업 주기를 확인한다 — 보존 기간보다 오래된 계측은 백업에만 남는다.
  디스크 여유는 `DataVolumeDiskUsageHigh` 알림(85%)이 본다([observability.md §4](observability.md#4-알림-규칙)).
