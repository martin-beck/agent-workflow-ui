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
import threading
from functools import wraps
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from .android import (registration_qr, registration_request, ssh_public_key_fingerprint,
                      validate_decision_message, verify_ecdsa_signature)


def _valid_digest(value: str) -> bool:
    return len(value) == 71 and value.startswith("sha256:") and all(
        character in "0123456789abcdefABCDEF" for character in value[7:])


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _event_digest(message: dict[str, Any]) -> str:
    """Digest the complete canonical event for idempotent retries."""
    encoded = json.dumps(message, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _synchronized(method):
    """Serialize state transitions when the HTTPS adapter handles requests concurrently."""
    @wraps(method)
    def guarded(self, *args, **kwargs):
        with self._lock:
            return method(self, *args, **kwargs)
    return guarded


class AndroidDeviceRegistry:
    """Authenticated one-time registration and revision-bound event registry."""

    def __init__(self, state_path: str | Path, *, clock: Callable[[], datetime] = _now) -> None:
        self.state_path = Path(state_path)
        self.clock = clock
        self._lock = threading.RLock()
        self.state = self._load()
        self.ssh_service_alias: str | None = self.state.get("ssh_service_alias")
        self.ssh_key_installer: Callable[..., None] | None = None

    def configure_ssh_rendezvous(self, *, metadata: dict[str, Any], service_alias: str,
                                 installer: Callable[..., None]) -> None:
        if not service_alias:
            raise ValueError("service-side SSH config alias is required")
        registration_qr(project_id="configure", endpoint="https://localhost",
                        bootstrap_id="configure_12345678", expires_at=_iso(self.clock() + timedelta(minutes=1)),
                        nonce="a" * 32, ssh_rendezvous=metadata)
        self.state["ssh_rendezvous"] = dict(metadata)
        self.state["ssh_service_alias"] = service_alias
        self.ssh_service_alias = service_alias
        self.ssh_key_installer = installer
        self._save()

    def _load(self) -> dict[str, Any]:
        if not self.state_path.exists():
            return {"bootstraps": {}, "devices": {}, "events": [], "batches": {}}
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

    @_synchronized
    def create_bootstrap(self, *, project_id: str, endpoint: str, ttl_seconds: int = 300,
                         ssh_rendezvous: dict[str, Any] | None = None) -> dict[str, Any]:
        if not 30 <= ttl_seconds <= 900:
            raise ValueError("bootstrap TTL must be between 30 and 900 seconds")
        bootstrap_id = secrets.token_urlsafe(18)
        nonce = secrets.token_hex(24)
        expires = _iso(self.clock() + timedelta(seconds=ttl_seconds))
        payload = registration_qr(project_id=project_id, endpoint=endpoint,
                                  bootstrap_id=bootstrap_id, expires_at=expires, nonce=nonce,
                                  ssh_rendezvous=ssh_rendezvous or self.state.get("ssh_rendezvous"))
        self.state["bootstraps"][bootstrap_id] = {"project_id": project_id,
            "nonce": nonce, "expires_at": expires, "redeemed": False}
        self._save()
        return payload

    @_synchronized
    def redeem(self, payload: dict[str, Any], *, device_public_key: str,
               capabilities: list[str], proof_signature: str, consent: bool) -> dict[str, Any]:
        request = registration_request(payload, device_public_key=device_public_key,
                                       capabilities=capabilities,
                                       proof_signature=proof_signature, consent=consent)
        record = self.state["bootstraps"].get(request["bootstrap_id"])
        if not record or record["redeemed"]:
            raise ValueError("registration bootstrap is unknown or already redeemed")
        if _parse(record["expires_at"]) <= self.clock():
            raise ValueError("registration bootstrap has expired")
        if record["project_id"] != request["project_id"] or record["nonce"] != request["nonce"]:
            raise ValueError("registration bootstrap binding mismatch")
        device_id = "android-" + secrets.token_urlsafe(12)
        credential_expires = _iso(self.clock() + timedelta(days=30))
        key_record = None
        if request.get("ssh_rendezvous"):
            if not self.ssh_service_alias or self.ssh_key_installer is None:
                raise ValueError("SSH device enrollment is unavailable; the service tunnel is not configured")
            from .android_ssh import authorized_key_record
            key_record = authorized_key_record(device_public_key, device_id,
                                               request["ssh_rendezvous"]["forward_port"],
                                               expires_at=credential_expires)
            # This installer uses the configured service SSH identity. Its
            # only authorization input is the user's explicit app approval,
            # the expiring QR nonce, and a verified Keystore signature.
            self.ssh_key_installer("install", self.ssh_service_alias, device_id, key_record)
            self.state.setdefault("credential_master", secrets.token_hex(32))
            credential = self._ssh_credential(device_id, credential_expires)
        else:
            credential = secrets.token_urlsafe(32)
        self.state["bootstraps"][request["bootstrap_id"]]["redeemed"] = True
        public_key_fingerprint = ssh_public_key_fingerprint(device_public_key)
        self.state["devices"][device_id] = {"project_id": request["project_id"],
            "public_key": device_public_key, "capabilities": request["capabilities"],
            "public_key_fingerprint": public_key_fingerprint,
            "ssh_rendezvous": request.get("ssh_rendezvous"),
            "authorized_key_record": key_record,
            "authorized_key_options": self._authorized_key_options(request),
            "enrollment_proof_digest": hashlib.sha256(proof_signature.encode()).hexdigest(),
            "credential_digest": hashlib.sha256(credential.encode()).hexdigest(),
            "revoked": False, "last_sequence": 0, "sessions": {},
            "last_seen": _iso(self.clock()),
            "credential_expires_at": credential_expires}
        self._save()
        response = {"schema_version": "1.0", "kind": "android-registration-response",
                "project_id": request["project_id"], "device_id": device_id,
                "public_key_fingerprint": public_key_fingerprint,
                "expires_at": credential_expires}
        if request.get("ssh_rendezvous"):
            response["credential_pending"] = True
        else:
            response["credential"] = credential
        return response

    def _ssh_credential(self, device_id: str, expires_at: str) -> str:
        import base64
        import hmac
        master = bytes.fromhex(self.state["credential_master"])
        message = f"awui-android-ssh-credential-v1\0{device_id}\0{expires_at}".encode()
        return base64.urlsafe_b64encode(hmac.new(master, message, hashlib.sha256).digest()).decode().rstrip("=")

    @_synchronized
    def create_ssh_challenge(self, device_id: str) -> dict[str, str]:
        device = self.state["devices"].get(device_id)
        if not device or device.get("revoked") or not device.get("ssh_rendezvous"):
            raise ValueError("Android device has no active SSH registration")
        challenge_id, nonce = secrets.token_urlsafe(18), secrets.token_hex(24)
        expires = _iso(self.clock() + timedelta(seconds=60))
        device.setdefault("ssh_challenges", {})[challenge_id] = {"nonce": nonce, "expires_at": expires}
        self._save()
        return {"schema_version": "1.0", "kind": "android-ssh-auth-challenge",
                "project_id": device["project_id"], "device_id": device_id,
                "challenge_id": challenge_id, "nonce": nonce, "expires_at": expires}

    @_synchronized
    def release_ssh_credential(self, *, device_id: str, challenge_id: str,
                               nonce: str, expires_at: str, signature: str) -> dict[str, str]:
        device = self.state["devices"].get(device_id)
        if not device or device.get("revoked") or not device.get("ssh_rendezvous"):
            raise ValueError("Android device has no active SSH registration")
        challenge = device.get("ssh_challenges", {}).get(challenge_id)
        if (not challenge or challenge["nonce"] != nonce or challenge["expires_at"] != expires_at
                or _parse(expires_at) <= self.clock()):
            raise ValueError("SSH authentication challenge is stale or unknown")
        message = ("awui-android-session-v1\n" + "\n".join((device["project_id"], device_id,
                   challenge_id, nonce, expires_at))).encode()
        verify_ecdsa_signature(device["public_key"], message, signature)
        del device["ssh_challenges"][challenge_id]
        credential = self._ssh_credential(device_id, device["credential_expires_at"])
        self._save()
        return {"schema_version": "1.0", "kind": "android-ssh-credential",
                "project_id": device["project_id"], "device_id": device_id,
                "credential": credential, "expires_at": device["credential_expires_at"]}

    @staticmethod
    def _authorized_key_options(request: dict[str, Any]) -> list[str]:
        """Return the least-privilege OpenSSH options for the enrolled key.

        The enrolling callback installs it only after consent and key proof.
        """
        options = ["restrict", "port-forwarding"]
        rendezvous = request.get("ssh_rendezvous")
        if rendezvous:
            options.extend((f'permitopen="127.0.0.1:{rendezvous["forward_port"]}"',
                            'command="/usr/bin/false"'))
        return options

    @_synchronized
    def authorized_key_record(self, device_id: str) -> str:
        """Return an attributable restricted authorized_keys record for an approved device."""
        device = self.state["devices"].get(device_id)
        if not device or device.get("revoked"):
            raise ValueError("unknown or revoked Android device")
        if not device.get("authorized_key_record"):
            raise ValueError("Android device has no SSH enrollment")
        return device["authorized_key_record"]

    @_synchronized
    def revoke(self, device_id: str) -> None:
        device = self.state["devices"].get(device_id)
        if not device:
            raise ValueError("unknown Android device")
        device["revoked"] = True
        device["revoked_at"] = _iso(self.clock())
        self._save()
        if device.get("ssh_rendezvous") and self.ssh_key_installer and self.ssh_service_alias:
            self.ssh_key_installer("revoke", self.ssh_service_alias, device_id,
                                   device.get("authorized_key_record") or "")

    @_synchronized
    def publish_batch(self, *, project_id: str, batch: dict[str, Any]) -> None:
        """Publish the authoritative pending batch for registered Android clients.

        The coordinator calls this after generating the same revision-bound packet
        used by the desktop UI.  The service stores the complete Markdown and
        decision payload, never inventing or rewriting decisions.
        """
        required = ("session_id", "task_revision", "packet_digest", "decisions",
                    "design_markdown", "workplan_markdown")
        missing = [key for key in required if key not in batch]
        if missing:
            raise ValueError("batch missing required fields: " + ", ".join(missing))
        if not isinstance(batch["decisions"], list):
            raise ValueError("batch decisions must be a list")
        if not isinstance(batch["session_id"], str) or not batch["session_id"]:
            raise ValueError("batch session_id must be a non-empty string")
        if not isinstance(batch["task_revision"], int) or batch["task_revision"] < 1:
            raise ValueError("batch task_revision must be a positive integer")
        if not isinstance(batch["packet_digest"], str) or not _valid_digest(batch["packet_digest"]):
            raise ValueError("batch packet_digest is invalid")
        if not all(isinstance(batch[key], str) for key in ("design_markdown", "workplan_markdown")):
            raise ValueError("batch documents must be Markdown strings")
        for decision in batch["decisions"]:
            if not isinstance(decision, dict) or not decision.get("id"):
                raise ValueError("batch contains an invalid decision")
            if not isinstance(decision.get("proposals", []), list):
                raise ValueError("decision proposals must be a list")
        self.state.setdefault("batches", {})[project_id] = json.loads(json.dumps(batch))
        self._save()

    @_synchronized
    def get_batch(self, *, device_id: str, credential: str) -> dict[str, Any] | None:
        device = self.state["devices"].get(device_id)
        if not device or device["revoked"]:
            raise ValueError("Android device is not registered")
        if _parse(device.get("credential_expires_at", "9999-12-31T00:00:00Z")) <= self.clock():
            raise ValueError("Android device credential has expired")
        digest = hashlib.sha256(credential.encode()).hexdigest()
        if not secrets.compare_digest(digest, device["credential_digest"]):
            raise ValueError("invalid Android device credential")
        device["last_seen"] = _iso(self.clock())
        self._save()
        return self.state.setdefault("batches", {}).get(device["project_id"])

    @_synchronized
    def route_event(self, *, device_id: str, credential: str, message: dict[str, Any],
                    project_id: str, session_id: str, task_revision: int,
                    packet_digest: str) -> dict[str, Any]:
        device = self.state["devices"].get(device_id)
        if not device or device["revoked"] or device["project_id"] != project_id:
            raise ValueError("Android device is not registered for this project")
        if _parse(device.get("credential_expires_at", "9999-12-31T00:00:00Z")) <= self.clock():
            raise ValueError("Android device credential has expired")
        digest = hashlib.sha256(credential.encode()).hexdigest()
        if not secrets.compare_digest(digest, device["credential_digest"]):
            raise ValueError("invalid Android device credential")
        validate_decision_message(message, project_id=project_id, session_id=session_id,
                                  task_revision=task_revision, packet_digest=packet_digest,
                                  device_id=device_id)
        # Sequence numbers are monotonic within a session, not tied to the
        # decision's array index.  Persist the accepted message digest so a
        # lost acknowledgement can be retried safely without duplicating the
        # Coordinator event.  A reused sequence with different content is a
        # fail-closed collision.
        sessions = device.setdefault("sessions", {})
        session = sessions.setdefault(session_id, {"last_sequence": 0, "events": {}})
        sequence = message["sequence"]
        digest = _event_digest(message)
        previous = session["events"].get(str(sequence))
        if previous is not None:
            if previous != digest:
                raise ValueError("Android event sequence collision")
            device["last_seen"] = _iso(self.clock())
            self._save()
            return {"schema_version": "1.0", "kind": "android-ack", "project_id": project_id,
                    "device_id": device_id, "session_id": session_id,
                    "task_revision": task_revision, "packet_digest": packet_digest,
                    "sequence": sequence, "idempotent": True}
        if sequence <= session["last_sequence"]:
            raise ValueError("replayed Android event sequence")
        session["last_sequence"] = sequence
        session["events"][str(sequence)] = digest
        # Retain the legacy aggregate for older state readers and diagnostics.
        device["last_sequence"] = max(device.get("last_sequence", 0), sequence)
        device["last_seen"] = _iso(self.clock())
        self.state["events"].append({"device_id": device_id, "message": message})
        self._save()
        return {"schema_version": "1.0", "kind": "android-ack", "project_id": project_id,
                "device_id": device_id, "session_id": session_id,
                "task_revision": task_revision, "packet_digest": packet_digest,
                "sequence": message["sequence"], "idempotent": False}
