"""implements: AI-C-01, AI-C-07, AI-C-14
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource


CONTRACT_DIR = Path(__file__).parents[1] / "contracts" / "ai"
# Single source of the common envelope / frame reference (monorepo-relative).
COMMON_CONTRACT_DIR = Path(__file__).resolve().parents[3] / "server" / "contracts" / "common"
EXAMPLE_DIR = CONTRACT_DIR / "examples"


def contract_validator() -> Draft202012Validator:
    # AI channel schemas layer on the backend's common envelope and frame
    # reference; those are loaded from their single source, never copied.
    registry = Registry()
    schemas = []
    for path in [*sorted(CONTRACT_DIR.glob("*.schema.json")), *sorted(COMMON_CONTRACT_DIR.rglob("*.schema.json"))]:
        schema = json.loads(path.read_text(encoding="utf-8"))
        schemas.append(schema)
        registry = registry.with_resource(schema["$id"], Resource.from_contents(schema))
    message_schema = next(schema for schema in schemas if schema["$id"].endswith("/contracts/ai/message.schema.json"))
    return Draft202012Validator(message_schema, registry=registry, format_checker=FormatChecker())


@pytest.mark.parametrize(
    "example_path",
    sorted(EXAMPLE_DIR.glob("*.json")),
    ids=lambda path: path.stem,
)
def test_every_shared_example_satisfies_the_message_contract(example_path: Path):
    message = json.loads(example_path.read_text(encoding="utf-8"))

    contract_validator().validate(message)


def test_detection_contract_rejects_numeric_frame_reference():
    message = json.loads((EXAMPLE_DIR / "detections.json").read_text(encoding="utf-8"))
    message["payload"]["frame_ref"] = 1042

    with pytest.raises(Exception):
        contract_validator().validate(message)


def test_detection_contract_rejects_ambiguous_bbox_array():
    message = json.loads((EXAMPLE_DIR / "detections.json").read_text(encoding="utf-8"))
    message["payload"]["detections"][0]["bbox"] = [120, 80, 210, 290]

    with pytest.raises(Exception):
        contract_validator().validate(message)


def test_channel_and_payload_schema_must_match():
    message = json.loads((EXAMPLE_DIR / "risk-state.json").read_text(encoding="utf-8"))
    message["channel"] = "ai_failure"

    with pytest.raises(Exception):
        contract_validator().validate(message)


def test_unknown_top_level_fields_are_rejected():
    message = json.loads((EXAMPLE_DIR / "capability-status.json").read_text(encoding="utf-8"))
    mutated = copy.deepcopy(message)
    mutated["topic"] = "mqtt/internal/topic"

    with pytest.raises(Exception):
        contract_validator().validate(mutated)


def test_old_frame_reference_shape_is_rejected():
    """AI emits the common frame reference v2 (camera_id/sequence_id/timestamp)."""
    message = json.loads((EXAMPLE_DIR / "detections.json").read_text(encoding="utf-8"))
    message["payload"]["frame_ref"] = {
        "source_id": "camera-01", "capture_timestamp": "2026-08-25T11:59:59.800Z", "sequence_id": 1042,
    }

    with pytest.raises(Exception):
        contract_validator().validate(message)


def test_null_correlation_id_is_rejected_by_the_common_envelope():
    message = json.loads((EXAMPLE_DIR / "risk-state.json").read_text(encoding="utf-8"))
    message["correlation_id"] = None

    with pytest.raises(Exception):
        contract_validator().validate(message)
