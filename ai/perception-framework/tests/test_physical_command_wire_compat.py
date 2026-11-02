"""implements: AI-C-07, AI-C-20
covers: AI's physical-command bytes are the HW wire contract — encoding a
        command gives exactly the golden bytes produced with the canonical
        hardware/schema/physical_command.proto, and real device captures
        decode into the in-process lifecycle.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from perception_framework.contracts.physical_command import (
    CancelCommandRequest,
    Command,
    CommandAcceptance,
    CommandResult,
    ExecutionStatus,
)
from perception_framework.contracts.proto import physical_command_pb2 as pb
from perception_framework.execution.physical_command_gateway import PhysicalCommandGateway, uplink_topic
from perception_framework.providers.fakes import InMemoryTransportProvider
from perception_framework.providers.physical_command_protobuf import PhysicalCommandProtobufSerializerProvider


REPO = Path(__file__).resolve().parents[3]
GOLDEN = json.loads((REPO / "hardware" / "schema" / "golden" / "physical_command.golden.json").read_text(encoding="utf-8"))
CASES = {case["name"]: bytes.fromhex(case["hex"]) for case in GOLDEN["cases"]}
TRACEPARENT = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"

# Bytes captured from a real device (pi3 drone node) on the broker —
# visualization/viz-debugger/scripts/lib/droneFixtures.mjs.
CAPTURED_ACCEPT = bytes.fromhex("1a0f0a0b6c6976652d70696e672d311001")
CAPTURED_STATUS = bytes.fromhex("22180a0b6c6976652d70696e672d311209455845435554494e47")
CAPTURED_RESULT = bytes.fromhex(
    "2a380a0b6c6976652d70696e672d3110011a130a08757074696d655f73116666666666660e401a120a0766635f6c696e6b110000000000000000"
)
CAPTURED_REJECT = bytes.fromhex(
    "1a330a0a6c6976652d61726d2d311a250a0d554e494d504c454d454e5445441214616374696f6e206e6f7420737570706f72746564"
)
CAPTURED_CAPABILITY = bytes.fromhex("3a100a08783530302d303031120470696e67")


def test_generated_module_is_the_hardware_package():
    assert pb.DESCRIPTOR.package == "physical"
    assert set(pb.Command.DESCRIPTOR.fields_by_name) >= {
        "command_id", "target", "action", "parameters", "deadline_unix_ms", "traceparent",
    }


@pytest.mark.parametrize(
    ("name", "obj"),
    [
        ("ping", Command("cmd-00000001", "go1-001", "ping")),
        ("scan_mission", Command("cmd-00000001", "go1-001", "scan_mission", {"steps": 8, "forward_m": 1.0})),
        ("move_forward_traced", Command(
            "cmd-0000002a", "go1-001", "move_forward", {"distance_m": 4.2},
            correlation_id=TRACEPARENT, deadline=1790000000.0,
        )),
        ("cancel_request", CancelCommandRequest("cmd-0000002a")),
    ],
)
def test_downlink_bytes_equal_the_canonical_golden_bytes(name, obj):
    assert PhysicalCommandProtobufSerializerProvider().encode(obj) == CASES[name]


def test_golden_lengths_match_what_hardware_measured():
    assert len(CASES["ping"]) == 31
    assert len(CASES["scan_mission"]) == 79


def test_string_parameters_are_refused_instead_of_silently_dropped():
    with pytest.raises(ValueError, match="only carries numbers"):
        PhysicalCommandProtobufSerializerProvider().encode(Command("c", "go1-001", "say", {"text": "hi"}))


def test_golden_uplink_messages_decode_into_the_lifecycle():
    serializer = PhysicalCommandProtobufSerializerProvider()
    rejected = serializer.decode(CASES["acceptance_rejected"])["payload"]
    assert rejected["accepted"] is False and rejected["rejection"]["code"] == "UNIMPLEMENTED"
    aborted = serializer.decode(CASES["result_aborted"])["payload"]
    assert aborted["status"] == "ABORTED" and aborted["failure"]["message"] == "robot_state_lost"
    assert serializer.decode(CASES["capability"])["payload"] == {
        "device_id": "go1-001", "actions": ["ping", "scan_mission"],
    }


def test_real_device_captures_drive_the_gateway():
    transport = InMemoryTransportProvider()
    gateway = PhysicalCommandGateway(transport, PhysicalCommandProtobufSerializerProvider())
    gateway.attach("x500-001")

    for payload in (CAPTURED_CAPABILITY, CAPTURED_ACCEPT, CAPTURED_STATUS, CAPTURED_RESULT, CAPTURED_REJECT):
        transport.publish(uplink_topic("x500-001"), payload)

    assert [c.name for c in gateway.known_capabilities("x500-001")] == ["ping"]
    assert gateway.get_acceptance("live-ping-1").accepted is True
    result = gateway.wait_for_result("live-ping-1", timeout=1.0)
    assert result.status is ExecutionStatus.SUCCEEDED
    assert result.result == {"uptime_s": pytest.approx(3.8), "fc_link": 0.0}
    rejection = gateway.get_acceptance("live-arm-1")
    assert rejection.accepted is False and rejection.rejection.code == "UNIMPLEMENTED"


def test_device_side_round_trip_of_ai_shaped_replies():
    serializer = PhysicalCommandProtobufSerializerProvider()
    acceptance = serializer.decode(serializer.encode(CommandAcceptance("c-1", True, 100.0)))["payload"]
    assert acceptance["command_id"] == "c-1" and acceptance["accepted"] is True
    result = serializer.decode(serializer.encode(
        CommandResult("c-1", ExecutionStatus.CANCELED, 101.0, result={"odo_m": 0.5})))["payload"]
    assert result["status"] == "CANCELED" and result["result"] == {"odo_m": 0.5}
