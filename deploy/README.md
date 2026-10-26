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
├── edge/                     구역 엣지 스택 (Mosquitto · OTel Agent · 엣지 Prometheus)
└── scripts/                  init-env · healthcheck · seed-demo · backup · restore
```

```bash
./scripts/init-env.sh && docker compose up -d --build --wait && ./scripts/healthcheck.sh
```

문서: [docs/deployment/](../docs/deployment/README.md)
