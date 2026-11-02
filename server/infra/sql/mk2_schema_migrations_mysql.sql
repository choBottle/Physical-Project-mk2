-- =============================================================================
-- MK2 — MySQL 스키마 판 추적 (schema_migrations)
--
-- 어느 마이그레이션(server/infra/sql/migrations/*.sql)이 이 DB 에 적용됐는지를 DB 자신이 기억한다.
-- 적용 주체: root 만. 최초 초기화(deploy/server/initdb/mysql/10-mk2-init.sh)와
--            deploy/scripts/migrate.sh 가 이 파일을 그대로 읽는다(재실행 안전 — IF NOT EXISTS · INSERT IGNORE).
--
-- ⚠ 앱 계정(mk2_app)에는 이 테이블 권한을 **주지 않는다**(mk2_grants_mysql.sql.example 에 줄이 없다 — 의도).
--   MySQL GRANT 는 테이블 단위라 줄이 없으면 읽기조차 못 한다. 코드는 스키마 판을 바꿀 수 없다(제약 14).
--
-- 판 이름(version) = 마이그레이션 파일 이름에서 `.sql` 을 뺀 것(예: 20261215_add_foo).
-- 00000000_baseline = "이 표가 생기기 전까지의 정본 스키마". 추적 도입 전에 초기화된 기존 서버도
-- migrate.sh 가 이 표를 만들면서 baseline 으로 표시한다.
-- =============================================================================

USE mk2;

CREATE TABLE IF NOT EXISTS schema_migrations (
  version     VARCHAR(128)  NOT NULL                             COMMENT '마이그레이션 파일 이름(.sql 제외). 00000000_baseline = 추적 도입 시점의 정본',
  applied_at  DATETIME(6)   NOT NULL DEFAULT (UTC_TIMESTAMP(6))  COMMENT 'UTC. 적용 시각',
  applied_by  VARCHAR(32)   NOT NULL DEFAULT 'manual'            COMMENT 'baseline | init(정본에 이미 포함) | migrate.sh | manual(파일 자신의 기록)',
  PRIMARY KEY (version)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin
  COMMENT='스키마 판 추적 — root 만 쓴다. 앱 계정 권한 없음';

INSERT IGNORE INTO schema_migrations (version, applied_by) VALUES ('00000000_baseline', 'baseline');
