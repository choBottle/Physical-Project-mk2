# 기존 서버용 스키마 변경분

새 서버는 상위 폴더의 정본(`mk2_*.sql`)만으로 최신 스키마가 선다(최초 초기화가 이 폴더의 파일을 전부 "적용됨"으로 표시한다).
이 폴더에는 **이미 운영 중인 DB** 에 같은 변경을 반영하는 `ALTER` 류 파일을 둔다. 재실행해도 안전하게 쓴다.

| 엔진 | 파일 이름 | 판 이름(`schema_migrations.version`) |
|---|---|---|
| MySQL | `YYYYMMDD_<주제>.sql` | `YYYYMMDD_<주제>` |
| TimescaleDB | `YYYYMMDD_<주제>_tsdb.sql` | `YYYYMMDD_<주제>_tsdb` |

- `<주제>` 는 영숫자·`_` 만. 같은 날 여러 개면 `YYYYMMDD_1_<주제>`. 적용 순서 = 엔진별 파일 이름 사전순.
- 파일 끝에 자기 기록 줄(`INSERT … schema_migrations …`)을 둔다.
- 적용: `deploy/` 에서 `./scripts/migrate.sh --dry-run` → `./scripts/migrate.sh` (백업 먼저).

절차: [`docs/deployment/database.md` §4](../../../../docs/deployment/database.md#4-스키마-변경-절차-마이그레이션)
