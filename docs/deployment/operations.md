# 운영 런북

모든 명령은 `deploy/` 에서 실행한다. 원칙: **"떠 있다"가 아니라 "흐른다"를 본다** — 판정은 `./scripts/healthcheck.sh`.

> Windows Git Bash 에서는 먼저 `export MSYS_NO_PATHCONV=1` — 그러지 않으면 아래 `docker compose exec kafka /opt/kafka/…` ·
> `promtool check config /etc/prometheus/…` 같은 명령의 컨테이너 안 경로를 Git Bash 가 Windows 경로로 바꿔 실패한다.

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
| 백업 / 복구 | `./scripts/backup.sh` (→ `deploy/backups/<UTC>/`) / `./scripts/restore.sh <디렉터리>` (`[y/N]` 확인 — 비대화식은 `--yes`) — [database.md §6](database.md#6-백업--복구--보존) |
| DB 마이그레이션 · 보존 정책 | `./scripts/migrate.sh --dry-run` / `./scripts/migrate.sh` — [database.md §4](database.md#4-스키마-변경-절차-마이그레이션) |

## 재부팅 뒤

compose 의 기동 순서(`depends_on: condition: service_healthy` — 백엔드는 DB·Kafka 가 healthy 가 된 뒤)는 **`docker compose up`
을 실행할 때만** 지켜진다. 재부팅 뒤 컨테이너를 되살리는 것은 도커 데몬의 restart 정책(`unless-stopped`)이고, 데몬은
순서를 보지 않는다. 그래서 백엔드가 DB·Kafka 보다 먼저 떠서 몇 번 죽었다 다시 뜰 수 있다(대개 스스로 회복한다). 또
`MK2_EDGE_BIND` 가 Tailscale 주소면 `tailscaled` 가 주소를 올리기 전에 바인딩하려다 입구 컨테이너가 실패할 수 있다.

운영 서버는 systemd 유닛으로 순서를 고정한다 — 예시 [`deploy/systemd/mk2-central.service`](../../deploy/systemd/mk2-central.service):

```ini
[Unit]
Requires=docker.service
After=docker.service network-online.target tailscaled.service
Wants=network-online.target tailscaled.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/opt/Physical-Project-mk2/deploy     # 이 저장소의 deploy/ 절대 경로
ExecStart=/usr/bin/docker compose up -d --wait --wait-timeout 600
ExecStop=/usr/bin/docker compose stop
```

```bash
sudo cp deploy/systemd/mk2-central.service /etc/systemd/system/   # WorkingDirectory 를 고친 뒤
sudo systemctl daemon-reload && sudo systemctl enable mk2-central
# Tailscale 주소를 주소가 올라오기 전에도 바인딩할 수 있게(권장)
echo 'net.ipv4.ip_nonlocal_bind=1' | sudo tee /etc/sysctl.d/90-mk2-nonlocal-bind.conf && sudo sysctl --system
```

어느 쪽이든 재부팅 뒤에는 확인한다 — `./scripts/healthcheck.sh --quick`.

## 현장 설정 — 추적 파일을 고치지 않는다

업그레이드는 `git checkout <태그>` 다. 추적되는 파일(`docker-compose.yml`, `server/config/*`)을 현장에서 고치면 다음
업그레이드에서 충돌하거나 조용히 덮어써진다. 현장 설정은 **gitignore 된 자리**에만 둔다 — 각 자리의 `*.example` 이 형식이다.

| 바꾸려는 것 | 현장 파일 (gitignore) | 반영 |
|---|---|---|
| 서비스 추가·자원 제한·포트 등 compose 조정 | `deploy/docker-compose.override.yml` (예시 `docker-compose.override.yml.example`) — compose 가 자동으로 함께 읽는다 | `docker compose up -d` |
| 엣지 페더레이션 타깃 | `deploy/site/prometheus/edge-targets/*.yml` | 자동(file_sd) |
| 현장 수집 잡 | `deploy/site/prometheus/scrape/*.yml` | `curl -X POST http://127.0.0.1:7861/-/reload` |
| 현장 알림 규칙 | `deploy/site/prometheus/rules/*.yml` | 위와 같음 |
| Alertmanager 주소 | `deploy/site/prometheus/alertmanagers/*.yml` (서비스는 override 예시) | 자동(file_sd) |
| Mosquitto 운영 프로파일(계정·ACL) | `deploy/site/mosquitto/*.conf` | `docker compose restart mosquitto` |
| 비밀값·노출 주소·포트·보존 기간·이미지 태그 | `deploy/.env` | `docker compose up -d` |
| 엣지 쪽 | `deploy/edge/.env` · `deploy/edge/site/` · `deploy/edge/docker-compose.override.yml` | 같은 방식 |

합쳐진 compose 확인: `docker compose config`. Prometheus 설정 확인:
`docker compose exec prometheus promtool check config /etc/prometheus/prometheus.yml`.
`./scripts/backup.sh` 는 이 파일들을 담지 않는다 — `.env` 와 함께 따로 보관한다.

## 업그레이드 (새 릴리스로)

```bash
./scripts/backup.sh                       # 1. 백업 (.env · site/ · override 는 따로 보관 — 위 「현장 설정」)
git status --short                        #    추적 파일에 현장 수정이 없어야 한다(있으면 site/·override 로 옮긴다)
git fetch --tags && git checkout <새 태그>  # 2. 코드 — 예: v1.0.0-rc.3 (현재 릴리스는 저장소 README 첫머리)
diff .env.example .env                    # 3. 새 환경변수 — CHANGELOG 해당 판의 `### Deployment changes` 절
#    MK2_TSDB_RETENTION_DAYS · MK2_TSDB_COMPRESS_AFTER_DAYS 는 비우면 끔 — database.md §6
#    게시 이미지를 쓰면 .env 의 MK2_BACKEND_IMAGE 태그를 새 판으로 올린다:
#      MK2_BACKEND_IMAGE=ghcr.io/<owner>/mk2-backend:<새 태그>
docker compose pull && docker compose up -d --wait            # 4a. 게시 이미지 — 바뀐 서비스만 재생성
# docker compose up -d --build --wait                        # 4b. 소스에서 빌드(MK2_BACKEND_IMAGE=mk2-backend:local)
./scripts/migrate.sh --dry-run            # 5. DB 마이그레이션 — 대기 목록 확인
./scripts/migrate.sh                      #    대기분 적용 + 보존·압축 정책 반영(할 일 없으면 그대로 끝난다)
./scripts/healthcheck.sh                  # 6. 검증
```

`migrate.sh` 는 매 업그레이드마다 돌린다 — 대기 마이그레이션이 없으면 아무것도 바꾸지 않는다. 추적 도입(#41) 전에
초기화된 서버는 첫 실행에서 `schema_migrations` 표를 만들고 baseline 으로 표시한다([database.md §4](database.md#4-스키마-변경-절차-마이그레이션)).
마이그레이션 중 백엔드가 새 칼럼을 기대하면 잠깐 오류를 낼 수 있다 — CHANGELOG 가 "백엔드 정지 후 적용"을 요구하면
`docker compose stop be-ingest be-storage be-gateway be-capture` → `migrate.sh` → `up -d --wait` 순서로 한다.

`MK2_BACKEND_IMAGE` 태그를 올리지 않으면 코드는 새 판인데 백엔드는 옛 이미지로 돈다. 게시 이미지를 쓸 때 `--build` 를
붙이면 compose 가 그 이름으로 로컬 빌드를 만들어 게시 이미지를 가린다 — 붙이지 않는다.

되돌리기: 이전 태그로 `checkout` → `MK2_BACKEND_IMAGE` 를 이전 태그로 → `up -d --wait`(소스 빌드면 `--build`).
DB 변경이 있었다면 백업으로 `restore.sh`.

폐쇄망 서버: [offline.md §7](offline.md#7-폐쇄망-업그레이드).

## 알림별 대응

### scrape-target-down
`ScrapeTargetDown` — 어느 `job` 인지 본다. `docker compose ps <서비스>` → 죽었으면 `docker compose logs <서비스> --tail 50`.
`edge_federate` 면 엣지 쪽(터널·엣지 Prometheus) 문제다 — 엣지에서 `tailscale status`, `docker compose ps`.
타깃 목록은 `deploy/site/prometheus/edge-targets/*.yml`.

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

### data-volume-disk-usage-high
`DataVolumeDiskUsageHigh` — 데이터 볼륨(`/mk2-data/<timescaledb|mysql|backend|kafka>`)이 놓인 호스트 파일시스템이 85% 를 넘었다
(볼륨이 같은 디스크에 있으면 여러 개가 함께 뜬다). 차오르면 DB 가 쓰기를 멈추고 적재가 실패한다(→ `StorageWriteFailing`).
1. 무엇이 큰지: `docker system df -v` (볼륨별 크기) · 호스트 `df -h`
2. 계측(TimescaleDB)이면 보존·압축 정책 — `.env` 의 `MK2_TSDB_RETENTION_DAYS` · `MK2_TSDB_COMPRESS_AFTER_DAYS` →
   `./scripts/apply-retention.sh` ([database.md §6](database.md#6-백업--복구--보존)). 압축은 다음 정책 실행(하루 몇 번) 때 반영된다.
3. 촬영본(`backend`)이면 오래된 세션을 고른다(`docker compose exec be-capture python -m backend.gateway.capture --retention-dry-run`) → 아카이브를 다른 저장소로 옮긴다.
4. Kafka 는 7일 보존(`KAFKA_LOG_RETENTION_HOURS`) — 평소보다 크면 소비 지연(소비자가 멈췄는지) 확인.
5. 오래된 백업(`deploy/backups/`)이 같은 디스크에 쌓였는지 — 백업은 다른 디스크에 둔다.

## 알려진 사항

| 항목 | 내용 |
|---|---|
| Tempo 워밍업 | 기동 뒤 ~15초간 `/ready` 503 — 정상 |
| Loki `empty ring` 로그 | 기동 직후 한 번 — 정상 |
| `test_c4_truncated_archive_leaves_nothing` | 전체 회귀(353건)를 한 번에 돌릴 때 가끔 실패하는 타이밍 의존 시험. 단독 실행 시 통과(2026-10-26). 배포와 무관 — 시험 쪽 대기 조건 보강 대상 |
| counter 리셋 | 백엔드 재기동마다 0 — `rate()` 로 본다 |
| 시험 장치 | `healthcheck.sh` 는 고정 장치 `hc-probe`, `e2e-sim.sh` 는 `wl-e2e-probe` 로 발행한다 — 레지스트리에는 이 둘만 남는다(실행마다 새 장치가 생기지 않는다). 이번 실행의 행은 적재 시각(`ingest_at` · `last_recorded_at`)으로 가린다. 계측 행은 실행마다 늘고, 앱 계정에 DELETE 가 없어 지우지 않는다(의도). 조회 시 `source_id NOT IN ('hc-probe','wl-e2e-probe')` (1.0 이전 판이 남긴 `hc-<시각>`·`wl-e2e-<시각>` 은 `NOT LIKE 'hc-%' AND NOT LIKE 'wl-e2e-%'`) |
