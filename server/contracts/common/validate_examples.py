"""공통 규격 예제(`examples/*.json`)가 자기 규격을 통과·거부하는지 한 번에 확인한다.

implements: BE-C-01
tests: CI `server-unit` 잡이 돌린다(인프라 없음 — 파일과 jsonschema 만 쓴다)

검증기는 백엔드가 실제로 쓰는 것(`backend.ingest.envelope`)을 그대로 쓴다 — 포맷 검사(date-time)와
`$id` 레지스트리(파일 간 `$ref`)가 운영 경로와 같아야 예제 판정이 의미가 있다.

파일 이름 규약(접두사 → 규격):
  envelope-*          message.schema.json (공통 헤더)
  payload-<ch>-<et>-* 공통 헤더 + payload/<ch>[.<et>].schema.json (state 는 개체 타입까지)
  media-header-v1-*   media-header.v1.schema.json (과도기)
  media-header-*      media-header.schema.json
  detections-*        detections.schema.json
이름에 `-invalid` 가 있으면 **거부돼야** 하고, 없으면 통과해야 한다. 규약에 맞지 않는 이름은 실패다
(새 예제가 조용히 검증 밖에 남지 않게).

사용법:  python contracts/common/validate_examples.py   (server/ 에서, `pip install -e .` 뒤)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Callable, Optional

HERE = Path(__file__).resolve().parent
SERVER_ROOT = HERE.parents[1]
if str(SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVER_ROOT))

from backend.ingest import envelope  # noqa: E402  (위 sys.path 보정 뒤에 import)


def _contract(filename: str) -> Callable[[Any], None]:
    def check(message: Any) -> None:
        errors = list(envelope.contract_validator(filename).iter_errors(message))
        if errors:
            raise envelope.MessageInvalid("; ".join(e.message for e in errors))
    return check


def _payload(channel: str, entity_type: Optional[str]) -> Callable[[Any], None]:
    def check(message: Any) -> None:
        envelope.validate_envelope(message)
        if envelope.payload_validator(channel, entity_type) is None:
            raise LookupError("본문 규격이 없다: channel={} entity_type={}".format(channel, entity_type))
        envelope.validate_payload(channel, entity_type, message)
    return check


def checker_for(name: str) -> Callable[[Any], None]:
    if name.startswith("envelope-"):
        return envelope.validate_envelope
    if name.startswith("media-header-v1-"):
        return _contract("media-header.v1.schema.json")
    if name.startswith("media-header-"):
        return _contract("media-header.schema.json")
    if name.startswith("detections-"):
        return _contract("detections.schema.json")
    if name.startswith("payload-"):
        parts = name[len("payload-"):].split("-")
        channel = parts[0]
        entity_type = parts[1] if channel == "state" and len(parts) > 1 else None
        return _payload(channel, entity_type)
    raise ValueError("이름 규약에 없는 예제다(접두사로 규격을 정할 수 없다)")


def main() -> int:
    examples = sorted((HERE / "examples").glob("*.json"))
    if not examples:
        print("예제가 없다: {}".format(HERE / "examples"))
        return 1
    failures = 0
    for path in examples:
        expect_valid = "-invalid" not in path.stem
        try:
            check = checker_for(path.name)
            message = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            print("  [FAIL] {}: {}".format(path.name, exc))
            failures += 1
            continue
        try:
            check(message)
            ok, why = expect_valid, "통과했다"
        except envelope.MessageInvalid as exc:
            ok, why = not expect_valid, "거부됐다 — {}".format(str(exc)[:160])
        except LookupError as exc:
            ok, why = False, str(exc)
        print("  [{}] {} ({}): {}".format("ok" if ok else "FAIL", path.name,
                                          "양성" if expect_valid else "음성", why))
        failures += 0 if ok else 1
    print("\n{}건 중 실패 {}건".format(len(examples), failures))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
