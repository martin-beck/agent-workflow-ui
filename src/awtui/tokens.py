"""Revision-bound short tokens for human decision batches.

The Coordinator owns the token registry.  The UI only receives a short
opaque token and uses the resolved record to locate the authoritative session
request.  Registry files contain digests, never usable token values.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

TOKEN_SCHEMA_VERSION = "1.0"
TOKEN_LENGTH = 8
_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


class TokenError(ValueError):
    """Raised when a token is malformed, stale, revoked, or mismatched."""


@dataclass(frozen=True)
class BatchToken:
    project_id: str
    session_id: str
    task_revision: int
    packet_digest: str
    session_file: str
    event_file: str
    ssh_host: str
    issued_at: str
    expires_at: str
    token_digest: str
    status: str = "active"

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _utc(value: datetime | None = None) -> datetime:
    value = value or datetime.now(timezone.utc)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _stamp(value: datetime) -> str:
    return _utc(value).isoformat().replace("+00:00", "Z")


def _parse_stamp(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except (TypeError, ValueError) as exc:
        raise TokenError("invalid token expiry") from exc


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def _validate_text(name: str, value: str) -> None:
    if not isinstance(value, str) or not value or any(ord(char) < 32 for char in value):
        raise TokenError(f"invalid {name}")


class TokenStore:
    """Small atomic JSON registry for short batch tokens.

    A token is bound to project, session, revision, and packet digest.  A
    caller must provide the same identity when resolving it; this prevents a
    copied token from selecting another project's request or a newer revision.
    """

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def issue(
        self,
        *,
        project_id: str,
        session_id: str,
        task_revision: int,
        packet_digest: str,
        session_file: str,
        event_file: str,
        ssh_host: str,
        ttl_seconds: int = 900,
        now: datetime | None = None,
    ) -> str:
        for name, value in (("project_id", project_id), ("session_id", session_id), ("packet_digest", packet_digest), ("session_file", session_file), ("event_file", event_file), ("ssh_host", ssh_host)):
            _validate_text(name, value)
        if not isinstance(task_revision, int) or isinstance(task_revision, bool) or task_revision < 1:
            raise TokenError("task_revision must be a positive integer")
        if not isinstance(ttl_seconds, int) or isinstance(ttl_seconds, bool) or not 1 <= ttl_seconds <= 86400:
            raise TokenError("ttl_seconds must be between 1 and 86400")
        current = _utc(now)
        for _ in range(10):
            token = "".join(secrets.choice(_ALPHABET) for _ in range(TOKEN_LENGTH))
            values = self._read()
            if not any(hmac.compare_digest(item.get("token_digest", ""), _digest(token)) for item in values):
                break
        else:
            raise TokenError("could not allocate unique batch token")
        values.append(BatchToken(project_id, session_id, task_revision, packet_digest, session_file, event_file, ssh_host, _stamp(current), _stamp(current + timedelta(seconds=ttl_seconds)), _digest(token)).as_dict())
        self._write(values)
        return token

    def resolve(
        self,
        token: str,
        *,
        project_id: str | None = None,
        session_id: str | None = None,
        task_revision: int | None = None,
        packet_digest: str | None = None,
        ssh_host: str | None = None,
        now: datetime | None = None,
    ) -> BatchToken:
        if not isinstance(token, str) or len(token) != TOKEN_LENGTH or any(char not in _ALPHABET for char in token):
            raise TokenError("invalid batch token")
        digest = _digest(token)
        value = next((item for item in self._read() if hmac.compare_digest(item.get("token_digest", ""), digest)), None)
        if value is None:
            raise TokenError("unknown batch token")
        record = BatchToken(**value)
        if record.status != "active":
            raise TokenError("batch token is no longer active")
        if _utc(now) >= _parse_stamp(record.expires_at):
            raise TokenError("batch token has expired")
        expected = (("project_id", project_id), ("session_id", session_id), ("task_revision", task_revision), ("packet_digest", packet_digest), ("ssh_host", ssh_host))
        for name, wanted in expected:
            if wanted is not None and getattr(record, name) != wanted:
                raise TokenError(f"batch token {name} mismatch")
        return record

    def revoke(self, token: str) -> None:
        record = self.resolve(token)
        values = self._read()
        for item in values:
            if hmac.compare_digest(item.get("token_digest", ""), record.token_digest):
                item["status"] = "revoked"
        self._write(values)

    def _read(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        value = json.loads(self.path.read_text(encoding="utf-8"))
        if value.get("schema_version") != TOKEN_SCHEMA_VERSION or not isinstance(value.get("tokens"), list):
            raise TokenError("invalid batch-token registry")
        return value["tokens"]

    def _write(self, values: list[dict[str, Any]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps({"schema_version": TOKEN_SCHEMA_VERSION, "tokens": values}, sort_keys=True, indent=2) + "\n"
        descriptor, temporary_name = tempfile.mkstemp(prefix=f".{self.path.name}.", dir=self.path.parent)
        try:
            os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_name, self.path)
        finally:
            if os.path.exists(temporary_name):
                os.unlink(temporary_name)


def resolve_batch_token(store_path: str | Path, token: str, *, ssh_host: str | None = None, now: datetime | None = None) -> BatchToken:
    """Resolve a launcher token and return its authoritative paths.

    Launchers should pass the SSH alias they intend to use.  Supplying it
    binds resolution to the same host that issued the batch and prevents a
    token copied into another host configuration from being misrouted.
    """
    return TokenStore(store_path).resolve(token, ssh_host=ssh_host, now=now)
