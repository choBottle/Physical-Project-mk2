-- =============================================================================
-- MK2 레지스트리 선언 축 — 데모·시험용 시드
--
-- 선언 축(registry_*_declared · registry_zone)은 **배포마다 운영자가 넣는다** — 앱 계정(mk2_app)은
-- SELECT 만 가진다(BE-Q-03: 미배포 대상도 목록에 나와야 하므로 텔레메트리로 자동으로 채우지 않는다).
-- 이 파일은 그 예시이자 회귀 시험(test_registry_declared_visible_without_telemetry)의 전제다.
-- 원본: server/docs/be/queries/registry-declared-vs-observed.sql 부록.
--
-- 적용(root, 재실행 안전):  ./deploy/scripts/seed-demo.sh
-- 실제 현장 배포에서는 이 파일을 복사해 그 현장의 구역·장치 목록으로 바꿔 넣는다.
-- =============================================================================
USE mk2;

INSERT IGNORE INTO registry_zone (zone_id, parent_zone_id, display_name)
VALUES ('zoneA', NULL, '상류 감시구역'),
       ('zoneB', NULL, '하류 감시구역');

-- 실제로 값을 보내는 개체
INSERT IGNORE INTO registry_entity_declared
    (entity_id, zone_id, entity_type, node_id, display_name, deployed, note)
VALUES ('wl-001', 'zoneA', 'sensor', 'pi7', '수위계 1호', 1, NULL);

-- ★ 아직 배포되지 않아 값을 보낸 적이 없는 개체 — 이것이 조회에 나와야 한다(BE-Q-03)
INSERT IGNORE INTO registry_entity_declared
    (entity_id, zone_id, entity_type, node_id, display_name, deployed, note)
VALUES ('wl-002', 'zoneA', 'sensor', NULL, '수위계 2호(미설치)', 0, '설치 예정');

SELECT entity_id, zone_id, deployed FROM registry_entity_declared ORDER BY entity_id;
