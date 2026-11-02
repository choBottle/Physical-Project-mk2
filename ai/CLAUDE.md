# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 0. 코드베이스 작업 가이드

요구사항 정의는 [docs/requirements.md](docs/requirements.md)에 있다(§1 문서 목적 · §2 절대 준수 원칙 ·
§3 금지 사항 · §4 기본 구조 · §5 전체 요구사항 = AI-* 요구사항 ID). 구현 범위의 기준이며,
작업 전 §2·§3을 반드시 읽는다. 아래 "§N" 표기 중 §1~§5는 그 문서의 절을 가리킨다.
이 절은 실제 저장소에서 작업할 때 필요한 정보만 요약한다.

### 명령

Python 패키지는 `perception-framework/`에 있다. 모든 명령은 그 디렉터리에서 실행한다.

```bash
pip install -e ".[dev]"      # 개발 설치 (Python >= 3.10, jsonschema/numpy/opencv/protobuf)
pytest -q                    # 전체 테스트
# 시스템 pytest 6.2.5 + anyio 플러그인 충돌로 collection이 깨지면:
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q
pytest tests/test_selector.py::test_name   # 단일 테스트

pip install -e ".[sim]"                       # 시뮬레이터 전용 (pyjevsim, 최초 1회)
PYTHONPATH=. python simulator/simulation.py   # 하드웨어 없이 프레임워크 성질(선택 기능 축소,
                                               # provider 교체, 물리 명령 lifecycle 등) 확인하는
                                               # DEVS 기반 시뮬레이터 — simulator/README.md 참고
pytest tests/test_scenarios.py                # 같은 시나리오(simulator/scenarios/*.json)를 자동 검증으로
```

빌드·lint 도구는 아직 설정되어 있지 않다.

### 구조와 흐름

핵심은 "무엇을 실행할 수 있는가"를 런타임에 정하는 3단 구조다. 상위 로직
(perception/decision/risk/reference)은 구체 기술을 절대 import하지 않는다.

1. `contracts/capability.py` — `CapabilityRequirement.evaluate(available)`이
   required/optional 선언을 `ACTIVE / DEGRADED / DISABLED`로 환산한다.
   optional 결손은 DEGRADED까지만 내려가고 DISABLED가 되지 않는다는 규칙이
   프레임워크 전체의 장애 격리 근거다(AI-C-05).
2. `contracts/profile.py` — `CompatibilityProfile`(required/preferred 태그 +
   `ResourceCost` + `priority`), `ResourceBudget`, `DeploymentProfile`.
   하드웨어·런타임 조건은 벤더 enum이 아니라 자유 문자열 태그다. 새 하드웨어는
   태그+프로파일 등록으로 추가하고 이 모듈을 수정하지 않는다.
3. `registry/capability_registry.py` — capability kind별 provider 등록부.
   `_local`(자기 노드, 항상 authoritative)과 `_remote`(중앙 레지스트리의 마지막
   스냅샷)를 분리해 중앙이 끊겨도 마지막 known-good로 계속 동작한다. 장치 최종
   가용성은 백엔드 판정을 **입력으로 소비**할 뿐 여기서 재판정하지 않는다.
4. `selection/selector.py` — 호환 후보 중 `(priority, compute_units)` 최소를
   고른다. 후보가 없으면 예외가 아니라 `SelectionResult(provider=None, reason=...)`을
   반환한다. 호출자는 이 None을 정상적인 축소 경로로 처리해야 한다.

`providers/adapters.py`의 Protocol들(Transport/Serializer/MediaSource/AIRuntime/
Control/Observability/NetworkOverlay/ModelDeployment)이 인프라 경계다. `providers/fakes.py`가
테스트·데모용 구현이며, MQTT/Kafka/OTel/K3s/Tailscale 같은 현재 배포 기술은
각 provider 뒤에 숨긴다. 물리 명령의 의미 계약(AI-C-20)은 `contracts/physical_command.py` +
`execution/command_execution.py`가 따로 소유하며, ROS 2 Action/AIP-155를 설계 근거로만
참고하고 해당 런타임에는 의존하지 않는다.

기능 모듈은 요구사항 대분류를 그대로 따른다: `ondevice/`(AI-N), `edge/`(AI-E),
`perception/`(AI-S, AI-E-01/04), `risk/`(AI-R), `execution/`(AI-B, AI-C-20),
`observability/`(AI-O), `continual/`(AI-L), `reference/`(AI-N-01 수직 슬라이스).
구 AI-D(서브태스크 생성·검증) 요구사항은 최신 요구사항 시트에서 제거되어 가시화 파트로
이관되었다 — 관련 코드·계약은 이 저장소에서 삭제되었다(git 이력 참고).

### 코드 작성 규약

- 모든 모듈·테스트 docstring 상단에 `implements: AI-X-NN` 형식으로 요구사항 ID를
  남긴다(§7). 기존 파일들이 이 형식을 지키고 있으니 그대로 따른다.
- 주석·docstring은 영문 설명 + 요구사항 인용은 원문 한국어를 섞어 쓰는 기존
  스타일을 유지한다.
- 변수·스키마 이름은 [perception-framework/perception_framework/contracts/data_dictionary.py](perception-framework/perception_framework/contracts/data_dictionary.py)의
  `AI-C-01` 공통 데이터 사전에 등록한 의미 단위로 통일한다. 새 이름이 필요하면
  먼저 사전에 의미·생산자·소비자·데이터 평면을 추가한다.
- 구현 상태는 [docs/ai/requirement-traceability.md](docs/ai/requirement-traceability.md)에
  요구사항 ID별로 기록되어 있다. 코드를 추가하면 이 표도 갱신한다.
  구조 설명은 [docs/ai/architecture.md](docs/ai/architecture.md).
- 그 밖의 설계 결정·가이드·검증 계획 문서는 목적별로 분류되어 있다 —
  새 문서를 찾거나 추가하기 전에 [docs/ai/README.md](docs/ai/README.md)에서
  위치를 먼저 확인한다(설계 결정은 `docs/ai/design/`, 확장 절차는 `docs/ai/guides/`,
  검증 계획은 `docs/ai/validation/`).
- 작업 단위별 보고서는 `reports/YYYY-MM-DD_HHMM_주제.md` 형식으로 남긴다.

## 1~5. 요구사항 정의

요구사항 정의는 [docs/requirements.md](docs/requirements.md) — 절 번호(§1~§5)와 요구사항 ID는 그 문서 기준이다.

## 6. AI 개발 에이전트의 구현 순서

1. 전체 요구사항을 먼저 읽고 공통 경계와 책임을 추출한다.
2. 요구사항 간 생산자·소비자 관계를 정리하되 변수명은 아직 확정하지 않는다.
3. Core/Optional capability와 provider/adapter 경계를 먼저 설계한다.
4. Capability Registry, 실행 호환성·자원·검증 프로파일, 배포 프로파일 구조를 설계한다.
5. 기능별 공통 인터페이스를 만든 뒤 현재 배포 기술을 provider 구현으로 연결한다.
6. 로컬 실행, 엣지 실행, 원격 실행 중 어느 위치에서도 동일한 상위 기능 계약을 사용할 수 있게 한다.
7. 정상 경로보다 먼저 선택 기능 부재, 네트워크 단절, provider 장애, 자원 부족, 갱신 실패의 동작을 명시한다.
8. 전체 기능이 구현된 뒤 실제 생산자·소비자 정보를 기반으로 공통 데이터 사전과 변수명을 한 번에 통일한다.
9. 각 요구사항 ID별로 구현 위치, 코드 모듈, 테스트 케이스와 충족 여부를 추적할 수 있게 한다.

## 7. 요구사항 추적 규칙

각 구현 단위와 테스트에는 관련 요구사항 ID를 남긴다.

예시:

```text
implements: AI-C-04, AI-C-10, AI-C-05
tests: adapter replacement, optional provider loss, registry fallback
```
