"""Protobuf binding of the physical-command lifecycle onto the HW wire contract.

The bytes this provider produces and accepts are defined by the single
canonical schema ``hardware/schema/physical_command.proto`` (package
``physical``) — the schema the robot/drone nodes decode downlink commands
with (``hardware/pi/common/physical_command.py``). The generated module
``contracts/proto/physical_command_pb2.py`` is regenerated from that file and
checked for drift by ``scripts/check_contracts.py`` at the repository root.

The in-process Core Contract (``contracts/physical_command.py``) is richer
than the wire, so this module is a translation layer, not a 1:1 dump:

==========================  =============================================
in-process (dataclass)      wire (``physical.*``)
==========================  =============================================
Command.parameters          ``map<string, double>`` — numbers/bools only;
                            a string or nested value raises ValueError
Command.deadline (epoch s)  ``deadline_unix_ms`` (int64, 0 = none)
Command.correlation_id      ``traceparent`` (only when it is a valid W3C
                            traceparent; anything else stays local)
CommandAcceptance           ``accepted_at`` is not on the wire; decode
  .accepted_at              fills it with the local receive time
CommandStatus.status        ``state`` (free string, e.g. "EXECUTING");
  .observed_at              receive time on decode; ``detail`` passes through
CommandResult.status        ``TerminalStatus`` enum (SUCCEEDED/ABORTED/CANCELED)
  .completed_at             receive time on decode
CommandResult.result        ``map<string, double>``
CancelCommandResponse       ``reason`` is not on the wire (dropped)
Capability (one action)     ``Capability{device_id, actions[]}`` — the wire
                            announces a device's whole action list; decode
                            yields ``{"device_id", "actions"}``
==========================  =============================================
"""

from __future__ import annotations

import math
import re
import time
from dataclasses import asdict, is_dataclass
from enum import Enum
from typing import Any

from perception_framework.contracts.proto import physical_command_pb2 as pb


_CLASS_TYPES = {
    "Command": "command",
    "CommandAcceptance": "acceptance",
    "CommandResult": "result",
    "CommandStatus": "status",
    "CancelCommandRequest": "cancel_request",
    "CancelCommandResponse": "cancel_response",
    "Capability": "capability",
}
_TERMINAL = {"SUCCEEDED", "ABORTED", "CANCELED"}
_TRACEPARENT = re.compile(r"^[0-9a-f]{2}-[0-9a-f]{32}-[0-9a-f]{16}-[0-9a-f]{2}$")


def _plain(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return {key: _plain(item) for key, item in asdict(value).items() if item is not None}
    if isinstance(value, dict):
        return {str(key): _plain(item) for key, item in value.items() if item is not None}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def _fill_numeric_map(target, values: dict | None, field: str) -> None:
    """The wire only carries ``map<string, double>``; refuse anything that
    would be silently lost instead of guessing an encoding for it."""
    for key, value in (values or {}).items():
        if isinstance(value, bool):
            number = 1.0 if value else 0.0
        elif isinstance(value, (int, float)):
            number = float(value)
        else:
            raise ValueError(
                f"{field}[{key!r}] = {value!r}: the physical wire contract only carries numbers "
                "(map<string, double>, hardware/schema/physical_command.proto)"
            )
        if not math.isfinite(number):
            raise ValueError(f"{field}[{key!r}] must be finite")
        target[str(key)] = number


def _encode_body(envelope, message_type: str, p: dict) -> None:
    if message_type == "command":
        c = envelope.command
        c.command_id = p["command_id"]
        c.target = p.get("target", "")
        c.action = p["action"]
        _fill_numeric_map(c.parameters, p.get("parameters"), "parameters")
        if p.get("deadline") is not None:
            c.deadline_unix_ms = int(round(float(p["deadline"]) * 1000))
        traceparent = p.get("traceparent") or p.get("correlation_id")
        if traceparent and _TRACEPARENT.match(str(traceparent)):
            c.traceparent = str(traceparent)
    elif message_type == "cancel_request":
        envelope.cancel_request.command_id = p["command_id"]
    elif message_type == "acceptance":
        a = envelope.acceptance
        a.command_id = p["command_id"]
        a.accepted = bool(p["accepted"])
        if p.get("rejection"):
            a.rejection.code = str(p["rejection"].get("code", ""))
            a.rejection.message = str(p["rejection"].get("message", ""))
    elif message_type == "status":
        s = envelope.status
        s.command_id = p["command_id"]
        s.state = str(p.get("state") or p.get("status") or "")
        s.detail = str(p.get("detail") or "")
    elif message_type == "result":
        r = envelope.result
        r.command_id = p["command_id"]
        status = str(p["status"])
        if status not in _TERMINAL:
            raise ValueError(f"CommandResult.status must be one of {sorted(_TERMINAL)}, got {status}")
        r.status = pb.TerminalStatus.Value(status)
        _fill_numeric_map(r.result, p.get("result"), "result")
        if p.get("failure"):
            r.failure.code = str(p["failure"].get("code", ""))
            r.failure.message = str(p["failure"].get("message", ""))
    elif message_type == "cancel_response":
        envelope.cancel_response.command_id = p["command_id"]
        envelope.cancel_response.accepted = bool(p["accepted"])
    elif message_type == "capability":
        cap = envelope.capability
        cap.device_id = str(p.get("device_id", ""))
        if "actions" in p:
            cap.actions.extend(str(action) for action in p["actions"])
        else:  # one in-process Capability = one declared action
            cap.actions.append(str(p["name"]))
    else:
        raise ValueError(f"unsupported physical message type: {message_type}")


def _decode_body(field: str, message, received_at: float) -> dict[str, Any]:
    if field == "command":
        body: dict[str, Any] = {
            "command_id": message.command_id, "target": message.target, "action": message.action,
            "parameters": dict(message.parameters),
        }
        if message.deadline_unix_ms:
            body["deadline"] = message.deadline_unix_ms / 1000.0
        if message.traceparent:
            body["correlation_id"] = message.traceparent
        return body
    if field == "cancel_request":
        return {"command_id": message.command_id}
    if field == "acceptance":
        body = {"command_id": message.command_id, "accepted": message.accepted, "accepted_at": received_at}
        if not message.accepted:
            # The device fills rejection only when accepted=false; keep the
            # in-process invariant (rejected => has a rejection) even if it did not.
            body["rejection"] = {
                "code": message.rejection.code or "UNKNOWN", "message": message.rejection.message,
            }
        return body
    if field == "status":
        return {
            "command_id": message.command_id, "status": message.state, "detail": message.detail,
            "observed_at": received_at,
        }
    if field == "result":
        body = {
            "command_id": message.command_id, "status": pb.TerminalStatus.Name(message.status),
            "completed_at": received_at, "result": dict(message.result),
        }
        if message.HasField("failure"):
            body["failure"] = {"code": message.failure.code, "message": message.failure.message}
        return body
    if field == "cancel_response":
        return {"command_id": message.command_id, "accepted": message.accepted}
    if field == "capability":
        return {"device_id": message.device_id, "actions": list(message.actions)}
    raise ValueError(f"unsupported physical message type: {field}")


class PhysicalCommandProtobufSerializerProvider:
    """Serialize one physical lifecycle message as a ``physical.PhysicalCommandEnvelope``."""

    # Registry key kept stable for existing configuration; the bytes follow
    # hardware/schema/physical_command.proto (package ``physical``).
    format_id = "physical_command_protobuf_v1"
    human_readable = False

    def encode(self, obj: Any) -> bytes:
        if is_dataclass(obj):
            message_type = _CLASS_TYPES.get(type(obj).__name__)
            payload = _plain(obj)
        elif isinstance(obj, dict):
            message_type = obj.get("message_type")
            payload = _plain(obj.get("payload", {}))
        else:
            raise TypeError("physical command protobuf requires a contract dataclass or envelope dict")
        if message_type is None:
            raise ValueError(f"unsupported physical message type: {type(obj).__name__}")
        envelope = pb.PhysicalCommandEnvelope()
        _encode_body(envelope, str(message_type), payload)
        return envelope.SerializeToString(deterministic=True)

    def decode(self, payload: bytes, schema_hint: str | None = None) -> dict[str, Any]:
        envelope = pb.PhysicalCommandEnvelope()
        envelope.ParseFromString(payload)
        field = envelope.WhichOneof("body")
        if field is None:
            raise ValueError("physical command protobuf envelope has no body")
        return {"message_type": field, "payload": _decode_body(field, getattr(envelope, field), time.time())}
