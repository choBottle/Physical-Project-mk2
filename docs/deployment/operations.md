# 운영 런북

모든 명령은 `deploy/` 에서 실행한다. 원칙: **"떠 있다"가 아니라 "흐른다"를 본다** — 판정은 `./scripts/healthcheck.sh`.

## 일상 명령

| 하려는 것 | 명령 |
|---|---|
| 상태 | `docker compose ps -a` |
| 전체 점검 | `./scripts/healthcheck.sh` (생존만: `--quick`) |
| 로그 | `docker compose logs -f be-ingest` (전체 로그 검색은 Grafana → Explore → Loki `{service_name=~"be-.*"}`) |
| 서비스 하나 재기동 | `docker compose restart be-storage` |
| 설정 파일 반영 (Prometheus) | `curl -X POST http://127.0.0.1:7861/-/reload` |
| 설정 파일 반영 (그 외) | `docker compose up -d --force-recreate <서비스>` |
| 정지 (데이터 유지) | `docker compose down` |
| ⚠ 완전 삭제 (데이터 포함) | `docker compose down -v` — 시험 서버에서만 |
| 백업 / 복구 | `./scripts/backup.sh` / `./scripts/restore.sh <디렉터리>` — [database.md §6](database.md#6-백업--복구--보존) |

**재부팅 뒤:** 모든 서비스는 `restart: unless-stopped` 이고 백엔드는 DB·Kafka 가 healthy 가 된 뒤에 뜬다(compose 가 순서를 보장).
그래도 확인한다 — `./scripts/healthcheck.sh --quick`.

## 업그레이드 (새 릴리스로)

```bash
./scripts/backup.sh                       # 1. 백업
git fetch --tags && git checkout v1.1.0   # 2. 코드
diff .env.example .env                    # 3. 새 환경변수가 생겼는지 (CHANGELOG 의 "배포 변경" 절)
#    CHANGELOG 에 "DB 변경 — 마이그레이션 필요" 가 있으면 database.md §4 절차로 먼저 적용
docker compose pull && docker compose up -d --build --wait   # 4. 바뀐 서비스만 재생성
./scripts/healthcheck.sh                  # 5. 검증
```

되돌리기: 이전 태그로 `checkout` → `up -d --build --wait`. DB 변경이 있었다면 백업으로 `restore.sh`.

## 알림별 대응

### scrape-target-down
`ScrapeTargetDown` — 어느 `job` 인지 본다. `docker compose ps <서비스>` → 죽었으면 `docker compose logs <서비스> --tail 50`.
`edge_federate` 면 엣지 쪽(터널·엣지 Prometheus) 문제다 — 엣지에서 `tailscale status`, `docker compose ps`.

### backend-telemetry-absent
`BackendSelfTelemetryAbsent` — 백엔드가 죽었거나 백엔드 → Collector → Prometheus 경로가 끊겼다.
1. `docker compose ps be-ingest be-storage` 2. 백엔드 로그 첫 줄의 `관측 활성: … → http://otel-collector:4317` 확인
3. `docker compose logs otel-collector --tail 30` 4. Prometheus Targets 에서 `otel_collector` 가 up 인지.
관측이 끊겨도 **업무 경로는 멈추지 않는다**(관측은 업무의 전제조건이 아니다) — TimescaleDB 적재가 계속되는지 따로 본다.

### kafka-produce-failing
`KafkaProduceFailing` — `docker compose logs be-ingest | grep "produce 실패"`. 브로커 생존(`docker compose ps kafka`),
디스크 여유(`df -h` — Kafka 7일 보존), 토픽 존재(`docker compose exec kafka /opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 --list`).
토픽이 없으면 `docker compose up kafka-init`.

### storage-write-failing
`StorageWriteFailing` — `docker compose logs be-storage --tail 50`. TimescaleDB 생존·디스크, 앱 계정 권한(최근 스키마를
바꿨다면 새 테이블에 GRANT 를 빠뜨리지 않았는지 — `healthcheck.sh` 5번 절). 적재 실패 중에도 Kafka 에 7일간 남아 있어,
고친 뒤 소비자가 커밋된 오프셋부터 다시 읽는다(멱등 키로 중복 없음).

### ingest-reject-rate-high
`IngestRejectRateHigh` — 발행자가 공통 규격과 다른 판으로 보낸다. 격리 파일에 사유가 있다:
`docker compose exec be-ingest tail -5 /data/quarantine.jsonl`. 규격: `server/contracts/common/` · 통합데이터규약.
대개 장치 펌웨어/노드 코드가 옛 판이다 — 해당 파트에 알린다(서버가 규격을 느슨하게 바꾸지 않는다).

### pipeline-lag-high
`PipelineLagHigh` — 발행 → 적재 지연. 먼저 `clock_skew`(장치 시계) 가능성: TimescaleDB 에서
`SELECT source_id, avg(lag_s) FROM telemetry WHERE ts > now() - interval '10 min' GROUP BY 1 ORDER BY 2 DESC LIMIT 5;`
특정 장치만 크면 그 장치의 재전송(spool) 또는 시계 문제, 전체가 크면 Kafka 소비 지연(`be-storage` 부하·DB 지연).

## 알려진 사항

| 항목 | 내용 |
|---|---|
| Tempo 워밍업 | 기동 뒤 ~15초간 `/ready` 503 — 정상 |
| Loki `empty ring` 로그 | 기동 직후 한 번 — 정상 |
| `test_c4_truncated_archive_leaves_nothing` | 전체 회귀(353건)를 한 번에 돌릴 때 가끔 실패하는 타이밍 의존 시험. 단독 실행 시 통과(2026-10-26). 배포와 무관 — 시험 쪽 대기 조건 보강 대상 |
| counter 리셋 | 백엔드 재기동마다 0 — `rate()` 로 본다 |
| 시험 행 | `healthcheck.sh` 가 `source_id=hc-<시각>` 4행을 남긴다. 앱 계정에 DELETE 가 없어 지우지 않는다(의도). 조회 시 `source_id NOT LIKE 'hc-%'` |
