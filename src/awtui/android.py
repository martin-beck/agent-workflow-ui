"""Protocol-neutral Android registration and decision bridge helpers.

The phone is another renderer, not an authority.  These helpers deliberately
keep QR bootstrap payloads capability-free: the one-time bootstrap id and
nonce are redeemed by the project service before a device credential exists.
"""
from __future__ import annotations

import re
from typing import Any

ANDROID_BRIDGE_VERSION = "1.0"
_DIGEST = re.compile(r"^sha256:[0-9a-fA-F]{64}$")


def registration_qr(*, project_id: str, endpoint: str, bootstrap_id: str,
                    expires_at: str, nonce: str) -> dict[str, Any]:
    if not project_id or not endpoint.startswith("https://"):
        raise ValueError("registration requires project id and HTTPS endpoint")
    if not re.fullmatch(r"[A-Za-z0-9_-]{16,128}", bootstrap_id):
        raise ValueError("bootstrap id has invalid shape")
    if not re.fullmatch(r"[A-Fa-f0-9]{32,128}", nonce):
        raise ValueError("registration nonce has invalid shape")
    return {"schema_version": ANDROID_BRIDGE_VERSION,
            "kind": "android-registration-qr", "project_id": project_id,
            "bootstrap_id": bootstrap_id, "endpoint": endpoint,
            "expires_at": expires_at, "nonce": nonce}


def registration_request(qr: dict[str, Any], *, device_public_key: str,
                         capabilities: list[str]) -> dict[str, Any]:
    if qr.get("kind") != "android-registration-qr":
        raise ValueError("not an Android registration QR payload")
    if not device_public_key or len(device_public_key) < 32:
        raise ValueError("device public key is required")
    return {**qr, "kind": "android-registration-request",
            "device_public_key": device_public_key,
            "capabilities": sorted(set(capabilities))}


def validate_decision_message(message: dict[str, Any], *, project_id: str,
                              session_id: str, task_revision: int,
                              packet_digest: str, device_id: str | None = None) -> None:
    """Fail closed unless a phone message is bound to the active revision."""
    required = ("schema_version", "kind", "project_id", "session_id",
                "task_revision", "packet_digest", "sequence")
    if any(key not in message for key in required):
        raise ValueError("Android message is missing a required binding")
    if message["schema_version"] != ANDROID_BRIDGE_VERSION:
        raise ValueError("unsupported Android bridge version")
    if message["kind"] not in {"android-decision-request", "android-decision-event", "android-ack"}:
        raise ValueError("invalid Android bridge message kind")
    if message["project_id"] != project_id or message["session_id"] != session_id:
        raise ValueError("Android message crosses project or session boundary")
    if message["task_revision"] != task_revision or message["packet_digest"] != packet_digest:
        raise ValueError("stale Android decision message")
    if not isinstance(message["sequence"], int) or message["sequence"] < 1:
        raise ValueError("Android message sequence must be positive")
    if device_id is not None and message.get("device_id") != device_id:
        raise ValueError("Android message comes from an unexpected device")
    if not _DIGEST.fullmatch(message["packet_digest"]):
        raise ValueError("invalid packet digest")
