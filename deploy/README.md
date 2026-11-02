# deploy — 배포 자산

```text
deploy/
├── docker-compose.yml        중앙 서버 스택 (13개 서비스)
├── .env.example              환경변수 템플릿 → scripts/init-env.sh 가 .env 생성
├── server/
│   ├── config/               mosquitto · otel-collector · prometheus(+알림 규칙) · loki · tempo
│   ├── initdb/               MySQL · TimescaleDB 최초 초기화 (스키마 정본은 ../server/infra/sql/)
│   ├── grafana/              데이터소스 · 대시보드 프로비저닝
│   └── seed/                 레지스트리 데모 시드
├── docker-compose.override.yml.example   현장 compose 조정 예시 → docker-compose.override.yml (gitignore)
├── site/                     현장 설정 (gitignore — *.example 만 추적): prometheus 엣지 타깃·잡·규칙·Alertmanager · mosquitto
├── systemd/                  재부팅 뒤 기동 순서 — mk2-central.service 예시
├── edge/                     구역 엣지 스택 (Mosquitto + 중앙 브릿지 · OTel Agent · 엣지 Prometheus) · edge/site/ 현장 설정
└── scripts/                  init-env · healthcheck · e2e-sim · seed-demo · backup · restore
```

```bash
./scripts/init-env.sh && docker compose up -d --build --wait && ./scripts/healthcheck.sh
```

추적 파일(`docker-compose.yml`·`server/config/*`)은 현장에서 고치지 않는다 — 현장 값은 `.env`·`site/`·override 에
([operations.md 「현장 설정」](../docs/deployment/operations.md#현장-설정--추적-파일을-고치지-않는다)).

문서: [docs/deployment/](../docs/deployment/README.md)
