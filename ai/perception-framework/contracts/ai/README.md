# AI Integration Contracts

이 디렉터리는 AI 내부 Python 객체가 아니라 파트 경계를 통과하는 JSON 메시지의 기준이다.
하드웨어·백엔드·가시화 구현은 언어별 타입을 독립적으로 유지하되 이 Schema와 예제로
호환성을 검증한다.

## 메시지 봉투

모든 AI 메시지는 `message.schema.json`을 따른다. 이 스키마는 백엔드 공통 머리
[`server/contracts/common/message.schema.json`](../../../../server/contracts/common/message.schema.json)을
`allOf`의 `$ref`로 그대로 포함한다 — **공통 규격의 사본을 여기 두지 않는다.** 이 디렉터리는
AI 채널 어휘와 채널별 payload, AI가 추가로 싣는 칸(`message_id`, `entity_id`, `channel`,
`coordinate_frame`)만 정한다. AI 생산자는 공통 머리 `schema_version` 2.x를 낸다.
MQTT/Kafka topic 문자열은 봉투에 포함하지 않으며 배포 adapter가 결정한다.

검증할 때는 이 디렉터리와 `server/contracts/common/`의 스키마를 함께 `$id` 레지스트리에
올린다(`tests/test_integration_contract_schemas.py`, 저장소 루트 `scripts/check_contracts.py`).

## 채널

| channel | payload schema | 주 소비자 |
|---|---|---|
| `detections` | `detection-result.schema.json` | 백엔드, 가시화 |
| `risk_state` | `risk-judgment.schema.json` | 백엔드, 가시화 |
| `ai_failure` | `ai-failure.schema.json` | 백엔드, 가시화 |
| `capability_status` | `capability-status.schema.json` | 백엔드, 가시화 |
| `model_deployment_result` | `model-deployment-result.schema.json` | 하드웨어, 백엔드, 가시화 |

`frame_ref`는 공통 프레임 참조 v2
[`server/contracts/common/frame-reference.schema.json`](../../../../server/contracts/common/frame-reference.schema.json)
(`camera_id`, `sequence_id`, `timestamp`)을 `$ref`한다. `frame_ref`를 싣는 메시지의 머리
`timestamp`는 `frame_ref.timestamp`와 같다. 탐지 `bbox`는 `{x, y, width, height}` 객체이며
`bbox_space`가 절대/정규화 좌표와 기준 해상도를 선언한다.

물리 명령의 JSON 표현(`physical-command.schema.json`)은 디버깅용이다. 와이어 정본은
`hardware/schema/physical_command.proto`다.

## 호환성 정책

- 기존 필드의 의미나 타입 변경은 `schema_version`을 올린다.
- 공통 머리의 선택 칸(`correlation_id` 등)은 값이 없으면 `null` 대신 칸을 생략한다
  (공통 규격이 문자열만 받는다). payload 안의 선택 필드는 각 payload 스키마를 따른다.
- 새로운 채널은 payload schema, 예제, Python 계약 테스트를 함께 추가한다.
- 가시화용 필드명 변환과 좌표 변환은 각 파트에 흩어 두지 않고 adapter 한 곳에서 한다.
- 실제 브로커 topic, 저장소, 모델 런타임, 오버레이 제품은 이 계약에 포함하지 않는다.
