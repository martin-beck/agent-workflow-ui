"""Small project-side Android registration and routing service core.

The HTTP/WebSocket adapter can wrap this core later; keeping identity and
replay rules here makes local, SSH, and Android transports share one contract.
State is JSON and atomically replaced so a development service can be moved
or supervised without losing revocation and sequence state.
"""
from __future__ import annotations

import hashlib
import json
import os
import secrets
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from .android import registration_qr, registration_request, validate_decision_message


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


class AndroidDeviceRegistry:
    """Authenticated one-time registration and revision-bound event registry."""

    def __init__(self, state_path: str | Path, *, clock: Callable[[], datetime] = _now) -> None:
        self.state_path = Path(state_path)
        self.clock = clock
        self.state = self._load()

    def _load(self) -> dict[str, Any]:
        if not self.state_path.exists():
            return {"bootstraps": {}, "devices": {}, "events": []}
        value = json.loads(self.state_path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError("Android service state must be an object")
        return value

    def _save(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix="android-service-", dir=self.state_path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(self.state, handle, sort_keys=True, separators=(",", ":"))
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.state_path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def create_bootstrap(self, *, project_id: str, endpoint: str, ttl_seconds: int = 300) -> dict[str, Any]:
        if not 30 <= ttl_seconds <= 900:
            raise ValueError("bootstrap TTL must be between 30 and 900 seconds")
        bootstrap_id = secrets.token_urlsafe(18)
        nonce = secrets.token_hex(24)
        expires = _iso(self.clock() + timedelta(seconds=ttl_seconds))
        payload = registration_qr(project_id=project_id, endpoint=endpoint,
                                  bootstrap_id=bootstrap_id, expires_at=expires, nonce=nonce)
        self.state["bootstraps"][bootstrap_id] = {"project_id": project_id,
            "nonce": nonce, "expires_at": expires, "redeemed": False}
        self._save()
        return payload

    def redeem(self, payload: dict[str, Any], *, device_public_key: str,
               capabilities: list[str]) -> dict[str, Any]:
        request = registration_request(payload, device_public_key=device_public_key,
                                       capabilities=capabilities)
        record = self.state["bootstraps"].get(request["bootstrap_id"])
        if not record or record["redeemed"]:
            raise ValueError("registration bootstrap is unknown or already redeemed")
        if _parse(record["expires_at"]) <= self.clock():
            raise ValueError("registration bootstrap has expired")
        if record["project_id"] != request["project_id"] or record["nonce"] != request["nonce"]:
            raise ValueError("registration bootstrap binding mismatch")
        device_id = "android-" + secrets.token_urlsafe(12)
        credential = secrets.token_urlsafe(32)
        self.state["bootstraps"][request["bootstrap_id"]]["redeemed"] = True
        self.state["devices"][device_id] = {"project_id": request["project_id"],
            "public_key": device_public_key, "capabilities": request["capabilities"],
            "credential_digest": hashlib.sha256(credential.encode()).hexdigest(),
            "revoked": False, "last_sequence": 0, "last_seen": _iso(self.clock())}
        self._save()
        return {"schema_version": "1.0", "kind": "android-registration-response",
                "project_id": request["project_id"], "device_id": device_id,
                "credential": credential, "expires_at": request["expires_at"]}

    def revoke(self, device_id: str) -> None:
        device = self.state["devices"].get(device_id)
        if not device:
            raise ValueError("unknown Android device")
        device["revoked"] = True
        self._save()

    def route_event(self, *, device_id: str, credential: str, message: dict[str, Any],
                    project_id: str, session_id: str, task_revision: int,
                    packet_digest: str) -> dict[str, Any]:
        device = self.state["devices"].get(device_id)
        if not device or device["revoked"] or device["project_id"] != project_id:
            raise ValueError("Android device is not registered for this project")
        digest = hashlib.sha256(credential.encode()).hexdigest()
        if not secrets.compare_digest(digest, device["credential_digest"]):
            raise ValueError("invalid Android device credential")
        validate_decision_message(message, project_id=project_id, session_id=session_id,
                                  task_revision=task_revision, packet_digest=packet_digest,
                                  device_id=device_id)
        if message["sequence"] <= device["last_sequence"]:
            raise ValueError("replayed Android event sequence")
        device["last_sequence"] = message["sequence"]
        device["last_seen"] = _iso(self.clock())
        self.state["events"].append({"device_id": device_id, "message": message})
        self._save()
        return {"schema_version": "1.0", "kind": "android-ack", "project_id": project_id,
                "device_id": device_id, "session_id": session_id,
                "task_revision": task_revision, "packet_digest": packet_digest,
                "sequence": message["sequence"]}
