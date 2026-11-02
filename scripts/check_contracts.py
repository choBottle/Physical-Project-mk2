#!/usr/bin/env python3
"""Cross-part contract drift check.

One canonical source per contract:

* physical command wire schema — ``hardware/schema/physical_command.proto``
  (the schema the robot/drone nodes decode downlink commands with);
* common message envelope / frame reference — ``server/contracts/common/``.

This script fails when anything drifts from those sources:

1. a second ``physical_command.proto`` exists anywhere and differs from the
   canonical one (there should be none — generate from the canonical file);
2. a committed ``physical_command_pb2.py`` differs from what ``grpc_tools.protoc``
   generates from the canonical schema (the ``Protobuf Python Version`` header
   and the runtime-version guard are ignored, so a newer protoc does not fail);
3. the golden wire bytes in ``hardware/schema/golden/physical_command.golden.json``
   no longer match what the canonical schema encodes (``--write-golden`` rewrites
   the file); the viz encoder is compared against the same file by
   ``visualization/viz-debugger/scripts/verify-command-encode.mjs``;
4. real device captures kept as viz fixtures do not decode/re-encode losslessly
   with the canonical schema;
5. AI example messages do not validate against the server common envelope
   (and, through ``$ref``, the current frame-reference shape) plus AI's own
   channel schemas; viz drone fixtures (needs ``node``) do not validate against
   the server common envelope + payload schemas;
6. the viz ``protocol.js`` differs from ``pbjs`` output for the canonical schema
   (only when ``visualization/viz-debugger/node_modules`` is installed; skipped
   otherwise).

Run from anywhere::

    pip install jsonschema grpcio-tools==1.83.1
    python -I scripts/check_contracts.py

Exit status 0 = no drift, 1 = drift (each problem is printed).
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CANONICAL_PROTO = ROOT / "hardware" / "schema" / "physical_command.proto"
GOLDEN = ROOT / "hardware" / "schema" / "golden" / "physical_command.golden.json"
COMMITTED_PB2 = (
    ROOT / "hardware" / "pi" / "common" / "physical_command_pb2.py",
    ROOT / "ai" / "perception-framework" / "perception_framework" / "contracts" / "proto" / "physical_command_pb2.py",
)
COMMON = ROOT / "server" / "contracts" / "common"
AI_CONTRACTS = ROOT / "ai" / "perception-framework" / "contracts" / "ai"
VIZ = ROOT / "visualization" / "viz-debugger"
SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build", ".claude"}

# Fixed inputs for the golden bytes. Map keys are listed in sorted order on
# purpose: Python's deterministic serialization sorts map keys, and the viz
# encoder sorts them too, so both sides produce the same bytes.
GOLDEN_CASES = [
    ("ping", {"command": {"command_id": "cmd-00000001", "target": "go1-001", "action": "ping"}}),
    ("scan_mission", {"command": {
        "command_id": "cmd-00000001", "target": "go1-001", "action": "scan_mission",
        "parameters": {"forward_m": 1.0, "steps": 8.0},
    }}),
    ("move_forward_traced", {"command": {
        "command_id": "cmd-0000002a", "target": "go1-001", "action": "move_forward",
        "parameters": {"distance_m": 4.2},
        "deadline_unix_ms": "1790000000000",
        "traceparent": "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01",
    }}),
    ("cancel_request", {"cancel_request": {"command_id": "cmd-0000002a"}}),
    ("acceptance_rejected", {"acceptance": {
        "command_id": "cmd-0000002b", "accepted": False,
        "rejection": {"code": "UNIMPLEMENTED", "message": "action not supported"},
    }}),
    ("status_executing", {"status": {
        "command_id": "cmd-0000002a", "state": "EXECUTING",
        "detail": "{\"ack\":1,\"of\":3,\"event\":\"forward\"}",
    }}),
    ("result_aborted", {"result": {
        "command_id": "cmd-0000002a", "status": "ABORTED", "result": {"odo_m": 1.5},
        "failure": {"code": "INTERNAL", "message": "robot_state_lost"},
    }}),
    ("cancel_response", {"cancel_response": {"command_id": "cmd-0000002a", "accepted": True}}),
    ("capability", {"capability": {"device_id": "go1-001", "actions": ["ping", "scan_mission"]}}),
]

problems: list[str] = []
notes: list[str] = []


def fail(message: str) -> None:
    problems.append(message)


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


# ---------------------------------------------------------------- 1. proto copies
def check_proto_copies() -> None:
    canonical = CANONICAL_PROTO.read_bytes()
    for path in ROOT.rglob("physical_command.proto"):
        if SKIP_DIRS.intersection(path.relative_to(ROOT).parts) or path == CANONICAL_PROTO:
            continue
        if path.read_bytes() != canonical:
            fail(f"{rel(path)} differs from canonical {rel(CANONICAL_PROTO)} - delete it and generate from the canonical file")
        else:
            notes.append(f"{rel(path)} is an identical copy (consider deleting it)")


# ---------------------------------------------------------------- 2. pb2 drift
_VERSION_HEADER = re.compile(r"^# Protobuf Python Version: .*$", re.M)
_RUNTIME_GUARD = re.compile(r"_runtime_version\.ValidateProtobufRuntimeVersion\([^)]*\)\n", re.S)


def _normalize_pb2(text: str) -> str:
    text = text.replace("\r\n", "\n")
    return _RUNTIME_GUARD.sub("", _VERSION_HEADER.sub("", text))


def generate_pb2(out_dir: Path) -> Path:
    try:
        from grpc_tools import protoc
    except ImportError:
        sys.exit("grpcio-tools is required: pip install grpcio-tools==1.83.1")
    args = ["protoc", f"-I{CANONICAL_PROTO.parent}", f"--python_out={out_dir}", str(CANONICAL_PROTO)]
    if protoc.main(args) != 0:
        sys.exit("protoc failed on the canonical schema")
    return out_dir / "physical_command_pb2.py"


def check_pb2(generated: Path) -> None:
    expected = _normalize_pb2(generated.read_text(encoding="utf-8"))
    for path in COMMITTED_PB2:
        if not path.is_file():
            fail(f"{rel(path)} is missing")
        elif _normalize_pb2(path.read_text(encoding="utf-8")) != expected:
            fail(f"{rel(path)} is stale - regenerate: python -m grpc_tools.protoc -I hardware/schema "
                 f"--python_out={rel(path.parent)} hardware/schema/physical_command.proto")


def load_pb2(generated: Path):
    spec = importlib.util.spec_from_file_location("physical_command_pb2", generated)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------- 3. golden bytes
def golden_document(pb) -> dict:
    from google.protobuf.json_format import ParseDict

    cases = []
    for name, message in GOLDEN_CASES:
        envelope = ParseDict(message, pb.PhysicalCommandEnvelope())
        cases.append({"name": name, "message": message,
                      "hex": envelope.SerializeToString(deterministic=True).hex()})
    return {
        "_comment": (
            "Golden wire bytes of physical.PhysicalCommandEnvelope, encoded with the canonical "
            "hardware/schema/physical_command.proto (deterministic: map keys sorted). Generated by "
            "`python -I scripts/check_contracts.py --write-golden`; verified by the same script and by "
            "visualization/viz-debugger `npm run verify:command-encode`. `message` uses proto field names."
        ),
        "cases": cases,
    }


def check_golden(pb, write: bool) -> None:
    document = golden_document(pb)
    text = json.dumps(document, indent=2, ensure_ascii=False) + "\n"
    if write:
        GOLDEN.parent.mkdir(parents=True, exist_ok=True)
        GOLDEN.write_text(text, encoding="utf-8", newline="\n")
        notes.append(f"wrote {rel(GOLDEN)}")
        return
    if not GOLDEN.is_file():
        fail(f"{rel(GOLDEN)} is missing - run with --write-golden")
        return
    committed = json.loads(GOLDEN.read_text(encoding="utf-8"))
    if committed != document:
        fail(f"{rel(GOLDEN)} does not match the canonical schema's encoding - the wire changed? "
             "If intended, rerun with --write-golden and re-verify the viz encoder")


# ---------------------------------------------------------------- 4. device captures
def check_device_captures(pb) -> None:
    fixtures = VIZ / "scripts" / "lib" / "droneFixtures.mjs"
    if not fixtures.is_file():
        notes.append(f"{rel(fixtures)} not found - skipped device capture check")
        return
    hexes = re.findall(r"'([0-9a-f]{16,})'", fixtures.read_text(encoding="utf-8"))
    if not hexes:
        fail(f"no captured hex found in {rel(fixtures)}")
    for value in hexes:
        envelope = pb.PhysicalCommandEnvelope()
        try:
            envelope.ParseFromString(bytes.fromhex(value))
        except Exception as error:  # noqa: BLE001 - any parse error is drift
            fail(f"device capture {value[:24]}... does not parse with the canonical schema: {error}")
            continue
        if envelope.WhichOneof("body") is None:
            fail(f"device capture {value[:24]}... has no known body")
        # A field the device sends but the canonical schema lacks survives as an
        # unknown field; dropping unknowns then changes the (deterministic) bytes.
        with_unknown = envelope.SerializeToString(deterministic=True)
        envelope.DiscardUnknownFields()
        if envelope.SerializeToString(deterministic=True) != with_unknown:
            fail(f"device capture {value[:24]}... carries fields the canonical schema does not define")


# ---------------------------------------------------------------- 5. JSON payloads
def _registry(*directories: Path):
    from referencing import Registry, Resource

    registry = Registry()
    for directory in directories:
        for path in sorted(directory.rglob("*.schema.json")):
            schema = json.loads(path.read_text(encoding="utf-8"))
            if "$id" in schema:
                registry = registry.with_resource(schema["$id"], Resource.from_contents(schema))
    return registry


def _validator(schema_path: Path, registry):
    from jsonschema import Draft202012Validator, FormatChecker

    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    return Draft202012Validator(schema, registry=registry, format_checker=FormatChecker())


def _errors(validator, instance) -> list[str]:
    return [f"{'/'.join(map(str, e.absolute_path)) or '<root>'}: {e.message}" for e in validator.iter_errors(instance)]


def check_ai_examples() -> None:
    registry = _registry(COMMON, AI_CONTRACTS)
    envelope = _validator(COMMON / "message.schema.json", registry)
    ai_message = _validator(AI_CONTRACTS / "message.schema.json", registry)
    examples = sorted((AI_CONTRACTS / "examples").glob("*.json"))
    if not examples:
        fail(f"no AI examples under {rel(AI_CONTRACTS / 'examples')}")
    for path in examples:
        message = json.loads(path.read_text(encoding="utf-8"))
        for label, validator in (("server common envelope", envelope), ("AI channel contract", ai_message)):
            for error in _errors(validator, message):
                fail(f"{rel(path)} vs {label}: {error}")


_VIZ_DUMP = """
const m = await import(process.argv[1]);
const out = {};
for (const name of ['statusBody', 'stateBody', 'liveStateBody', 'droneStateEnvelope', 'droneStateEnvelopeV2']) {
  if (typeof m[name] === 'function') out[name] = m[name]();
}
process.stdout.write(JSON.stringify(out));
"""


def check_viz_examples() -> None:
    node = shutil.which("node")
    fixtures = VIZ / "scripts" / "lib" / "droneFixtures.mjs"
    if node is None or not fixtures.is_file():
        notes.append("node or viz drone fixtures not available - skipped viz payload check")
        return
    result = subprocess.run(
        [node, "--input-type=module", "-e", _VIZ_DUMP, fixtures.as_uri()],
        capture_output=True, text=True, encoding="utf-8", check=False,
    )
    if result.returncode != 0:
        fail(f"could not load viz fixtures: {result.stderr.strip()[:400]}")
        return
    registry = _registry(COMMON)
    envelope = _validator(COMMON / "message.schema.json", registry)
    for name, message in json.loads(result.stdout).items():
        # droneStateEnvelope*() is the backend->web /state wrapper (its own contract);
        # the device message the server ingested is its `payload`.
        body = message
        if isinstance(message, dict) and "schema_version" not in message and isinstance(message.get("payload"), dict):
            body = message["payload"]
        for error in _errors(envelope, body):
            fail(f"viz fixture {name}() vs server common envelope: {error}")
        channel = body.get("channel") if isinstance(body, dict) else None
        payload_schema = None
        if channel in ("status", "heartbeat"):
            payload_schema = COMMON / "payload" / f"{channel}.schema.json"
        elif channel == "state":
            payload_schema = COMMON / "payload" / "state.drone.schema.json"
        if payload_schema is not None and payload_schema.is_file():
            for error in _errors(_validator(payload_schema, registry), body):
                fail(f"viz fixture {name}() vs {rel(payload_schema)}: {error}")


# ---------------------------------------------------------------- 6. viz protocol.js
def check_viz_protocol(tmp: Path) -> None:
    node = shutil.which("node")
    pbjs = VIZ / "node_modules" / "protobufjs-cli" / "bin" / "pbjs"
    committed = VIZ / "src" / "physical" / "protocol.js"
    if node is None or not pbjs.is_file():
        notes.append("viz node_modules not installed - skipped protocol.js regeneration check "
                     "(verify:command-encode still compares its bytes to the golden file)")
        return
    out = tmp / "protocol.js"
    subprocess.run([node, str(pbjs), "-t", "static-module", "-w", "es6", "--es6", "-o", str(out), str(CANONICAL_PROTO)],
                   check=True, cwd=VIZ)
    if out.read_text(encoding="utf-8").replace("\r\n", "\n") != committed.read_text(encoding="utf-8").replace("\r\n", "\n"):
        fail(f"{rel(committed)} is stale - run `npm run schema:pull` in visualization/viz-debugger")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--write-golden", action="store_true", help="rewrite the golden wire-bytes fixture")
    args = parser.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="backslashreplace")

    check_proto_copies()
    with tempfile.TemporaryDirectory() as tmp_name:
        tmp = Path(tmp_name)
        generated = generate_pb2(tmp)
        check_pb2(generated)
        pb = load_pb2(generated)
        check_golden(pb, args.write_golden)
        check_device_captures(pb)
        check_viz_protocol(tmp)
    check_ai_examples()
    check_viz_examples()

    for note in notes:
        print(f"note: {note}")
    if problems:
        print(f"\ncontract drift: {len(problems)} problem(s)")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    print("contracts OK - one canonical physical_command.proto, pb2/protocol.js/golden bytes in sync, "
          "example payloads valid against server/contracts/common")
    return 0


if __name__ == "__main__":
    sys.exit(main())
