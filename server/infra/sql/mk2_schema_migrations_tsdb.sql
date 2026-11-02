-- =============================================================================
-- MK2 — TimescaleDB 스키마 판 추적 (schema_migrations)
--
-- 어느 마이그레이션(server/infra/sql/migrations/*_tsdb.sql)이 이 DB 에 적용됐는지를 DB 자신이 기억한다.
-- 적용 주체: postgres 만. 최초 초기화(deploy/server/initdb/timescaledb/100_mk2_init.sh)와
--            deploy/scripts/migrate.sh 가 이 파일을 그대로 읽는다(재실행 안전).
--
-- ⚠ 앱 계정(mk2_app)에는 이 테이블 권한을 **주지 않는다**(mk2_grants_tsdb.sql.example 에 줄이 없다 — 의도).
--   소유자는 postgres 이고 PUBLIC 권한도 회수한다. 코드는 스키마 판을 바꿀 수 없다(제약 14).
--
-- 판 이름(version) = 마이그레이션 파일 이름에서 `.sql` 을 뺀 것(예: 20261215_add_foo_tsdb).
-- 00000000_baseline = "이 표가 생기기 전까지의 정본 스키마".
-- =============================================================================

CREATE TABLE IF NOT EXISTS public.schema_migrations (
    version     TEXT         PRIMARY KEY,
    applied_at  TIMESTAMPTZ  NOT NULL DEFAULT now(),
    applied_by  TEXT         NOT NULL DEFAULT 'manual'
);

COMMENT ON TABLE public.schema_migrations IS
    '스키마 판 추적 — postgres 만 쓴다. 앱 계정 권한 없음. version = 마이그레이션 파일 이름(.sql 제외)';

REVOKE ALL ON TABLE public.schema_migrations FROM PUBLIC;

INSERT INTO public.schema_migrations (version, applied_by)
VALUES ('00000000_baseline', 'baseline')
ON CONFLICT (version) DO NOTHING;
