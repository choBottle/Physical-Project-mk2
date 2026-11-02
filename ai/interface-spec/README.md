# 인터페이스 규약 (interface-spec)

파트 경계를 넘나드는 통신에 쓰이는 규약 문서를 모아두는 곳이다. 코드가 아니라
**"어떤 형식의 메시지를, 어떤 규칙으로 주고받는가"만 고정한 문서**이며, 하드웨어·백엔드·
가시화 등 어느 파트가 어느 쪽을 구현하든 이 문서 하나만 보고 맞춰 구현하면 통신이
성립하도록 하는 것이 목적이다. 내부 구현(언어, SDK, 코드 구조)은 각 파트 재량이다.

```text
spec/     규약 문서 — 파트별로 실제로 지켜야 할 내용
```

메시지 형식(스키마)은 여기 사본으로 두지 않는다 — 정본 한 벌만 둔다.

- 물리 명령 Protobuf: [`hardware/schema/physical_command.proto`](../../hardware/schema/physical_command.proto)
  (말단이 디코드에 쓰는 바로 그 스키마, package `physical`)
- 물리 명령 JSON 표현(디버깅용): [`perception-framework/contracts/ai/physical-command.schema.json`](../perception-framework/contracts/ai/physical-command.schema.json)
- 사본·생성물 어긋남은 저장소 루트 `python -I scripts/check_contracts.py` 가 잡는다.

## 지금 있는 규약

| 문서 | 대상 경계 | 무엇을 정하는가 |
|---|---|---|
| [`spec/physical-command-interface.md`](spec/physical-command-interface.md) | 엣지 ↔ 로봇/온디바이스 | 물리 명령 전송 토픽, 메시지 형식, 상태 그림, 재전송·취소·마감시각 규칙 |

새 파트 경계 규약이 필요하면 이 디렉터리에 문서를 추가한다 — 형식은 위 문서를 따른다
(무엇을 주고받는가만 정의하고, 어떻게 내부적으로 처리하는지는 다루지 않는다).
