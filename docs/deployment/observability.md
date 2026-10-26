# 관측 — Prometheus · Loki · Tempo · Grafana

> 원칙: **백엔드 자신도 관측한다.** 장치만 보면 "장치가 안 보내는 것"과 "백엔드가 못 받는 것"을 구분할 수 없다.

## 1. 경로

```text
백엔드·HW 노드·AI·브라우저 ──OTLP──▶ OTel Collector ──┬─ metric ─▶ :8889 ◀─scrape(5s)─ Prometheus ─▶ Grafana
  (gRPC 4316/4317 · HTTP 4318)                         ├─ trace  ─▶ tempo:4317 ──────────── Tempo ─────▶ Grafana
                                                       └─ log    ─▶ http://loki:3100/otlp ── Loki ─────▶ Grafana
엣지 Prometheus(구역 raw) ◀───────── /federate(요약만) ───────── 중앙 Prometheus
```

- 수신 포트 **4316 과 4317 은 같은 수신단**이다. 4316 은 백엔드 문서·기본값(`MK2_OTEL_ENDPOINT`)이 쓰던 번호, 4317 은 OTLP
  표준이며 HW 노드·AI 프레임워크의 기본값이다. 둘 다 열어 두어 어느 쪽 설정으로도 붙는다.
- Collector 를 우회하는 입구(Tempo·Loki 직접 수신)는 호스트에 열지 않는다.
- 이미지 버전을 고정한다. Collector 는 0.150 계열에서 컴포넌트 이름이 바뀌었다(`otlp`→`otlp_grpc`, `otlphttp`→`otlp_http`) —
  `:latest` 를 쓰면 설정이 다음 갱신에서 조용히 깨진다. 올릴 때는 CI 의 `validate` 단계가 먼저 판정한다.

## 2. 보존

| 저장소 | 보존 | 설정 위치 |
|---|---|---|
| Prometheus | 15일 | `deploy/.env` `MK2_PROMETHEUS_RETENTION` |
| Loki | 14일 | `deploy/server/config/loki.yaml` (`retention_enabled`·`retention_period`·`delete_request_store` 세 줄이 **함께** 있어야 집행) |
| Tempo | 168시간 | `deploy/server/config/tempo.yaml` `block_retention` |
| 엣지 Prometheus | 7일 | `deploy/edge/.env` `MK2_EDGE_PROMETHEUS_RETENTION` |

## 3. 백엔드 지표 목록

OTel 이름(`be.ingest.received`)이 Prometheus 에서 `be_ingest_received_total` 이 된다(counter 는 `_total`, 단위가 있으면 `_seconds` 등).

**A층 — 백엔드 자기 관측** (라벨에 `source_id`·`zone_id` 를 넣지 않는다 — 장치 수만큼 시계열이 곱해진다)

| 지표 | 종류 | 라벨 | 뜻 |
|---|---|---|---|
| `be_ingest_received_total` | counter | `channel` | 공통 규격 2단 검증을 통과한 수신 |
| `be_ingest_rejected_total` | counter | `channel` · `stage`(envelope·payload·unknown_channel) | 격리된 수신 — 발행자 규격 판 불일치의 신호 |
| `be_kafka_produce_total` | counter | `channel` · `outcome` | ingest → Kafka 전달 결과 |
| `be_storage_consumed_total` | counter | `channel` | 저장 소비자가 읽은 수 |
| `be_storage_write_total` | counter | `channel` · `outcome` | TimescaleDB 적재 결과 |
| `be_registry_observe_total` | counter | `outcome` | 레지스트리 관측 축 갱신 |
| `be_pipeline_lag_seconds` | histogram | | 발행 시각 → 적재까지 |
| `be_gateway_clients` | gauge | | WS 접속 수 |
| `be_gateway_push_total` | counter | | WS push |
| `be_gateway_media_frames_total` · `_media_gop_cut_total` · `_media_rejected_total` · `_media_ingress_total` | counter | | 미디어 중계 · drop-old |
| `be_gateway_media_coldstart_seconds` | histogram | | 뷰어 접속 → 첫 키프레임 |
| `be_gateway_capture_total` | counter | `outcome` | 촬영본 업로드 |

**C층 — 업무 값의 관측 표현** (`be_telemetry_*`, 예: `be_telemetry_water_level_m`) — 원본이 **아니다**(원본은 TimescaleDB).
대시보드·경보용 사본이며, 값이 흐를 때만 존재한다(5분 갱신이 없으면 내려간다 — "장치가 안 보내면 시계열도 없다").

> counter 는 재기동마다 0 이 된다. 절대값을 읽지 말고 `rate()`/`increase()` 로 본다.
> 다른 파트의 지표 이름 공간(`hw.*`, `perception_framework.*`, 화면 자체 지표)은 각 파트 문서 —
> [`server/docs/be/vz-observability-namespace.md`](../../server/docs/be/vz-observability-namespace.md).

## 4. 알림 규칙

`deploy/server/config/prometheus-rules.yml` — Prometheus UI 의 **Alerts** 탭에서 상태를 본다.

| 알림 | 심각도 | 판정 |
|---|---|---|
| `ScrapeTargetDown` | critical | 수집 대상 `up == 0` 2분 |
| `BackendSelfTelemetryAbsent` | warning | 백엔드 지표 10분 부재 |
| `KafkaProduceFailing` | critical | produce `outcome!="ok"` 발생 |
| `StorageWriteFailing` | critical | 적재 실패 발생 |
| `IngestRejectRateHigh` | warning | 격리 비율 10% 초과 10분 |
| `PipelineLagHigh` | warning | 지연 p90 > 5초 10분 |

각 알림의 대응 절차는 [operations.md](operations.md). **알림을 사람에게 보내려면** Alertmanager 를 붙인다(현재 미포함 — 받는
채널(메일·메신저)이 기관마다 달라서다). `prometheus.yml` 에 `alerting.alertmanagers` 를 추가하고 compose 에
`prom/alertmanager` 서비스를 더하는 것이 다음 단계다.

> 장치 **최종 가용성** 판정은 이 규칙이 아니라 백엔드 단일 지점의 몫이다(MQTT 세션 우선 — 아키텍처 원칙 7).

## 5. Grafana

`deploy/server/grafana/` 가 데이터소스(uid 고정: `mk2-prometheus` · `mk2-loki` · `mk2-tempo`)와 대시보드를 자동 등록한다.

| 대시보드 | 내용 |
|---|---|
| **MK2 Backend Overview** | 수집 대상 상태 · ingest 수신/격리 · Kafka produce · 적재 결과 · 지연 p50/p90 · WS/미디어 · 백엔드 로그 |

대시보드를 고쳤으면 Grafana 에서 JSON 으로 내보내 `deploy/server/grafana/dashboards/` 에 커밋한다(UI 수정은 재기동 때 사라진다 —
`allowUiUpdates: false`).

## 6. 엣지 페더레이션 (2계층)

엣지가 raw 를 보관하고 중앙은 **요약만** 당긴다 — 중앙 부하가 장치 수가 아니라 구역 수에 비례한다.

1. 엣지에 `deploy/edge` 스택을 세운다([edge.md](edge.md)) — 엣지 Prometheus 가 `MK2_EDGE_TUNNEL_BIND:9090` 에 뜬다.
2. 중앙 `deploy/server/config/prometheus.yml` 의 `edge_federate` 잡 주석을 풀고 타깃을 엣지 터널 주소로.
3. `curl -X POST http://127.0.0.1:7861/-/reload` (재생성 불필요).
4. 확인: `up{job="edge_federate"} == 1`, 그리고 `{agg_layer="edge"}` 시계열이 `match[]` 로 고른 것만 왔는지.
   `match[]` 를 넓히지 않는다 — 엣지 raw 전량을 끌어오면 2계층의 의미가 없다.

log·trace 는 요약하지 않는다 — 엣지 Collector 가 원본을 중앙으로 그대로 보낸다(`zone_id`·`agg_layer=edge` 리소스 속성을 붙여서).
