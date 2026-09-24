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
import time
from contextlib import contextmanager
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
    consumed_at: str = ""

    def as_dict(self) -> dict[str, Any]:
        value = asdict(self)
        if not value["consumed_at"]:
            value.pop("consumed_at")
        return value


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


def issue_for_batch(
    store_path: str | Path,
    request: dict[str, Any],
    *,
    session_file: str,
    event_file: str,
    ssh_host: str,
    ttl_seconds: int = 900,
    now: datetime | None = None,
) -> str:
    """Issue one token for a complete Coordinator decision batch."""
    if not isinstance(request, dict):
        raise TokenError("decision batch must be an object")
    project_id = request.get("project_id")
    session_id = request.get("session_id")
    ar = request.get("ar") if isinstance(request.get("ar"), dict) else {}
    task_revision = ar.get("task_revision", request.get("task_revision"))
    packet_digest = request.get("packet_digest")
    decisions = request.get("decisions")
    if decisions is None:
        decisions = request.get("batch")
    if decisions is None and request.get("guidance_request") is not None:
        decisions = [request["guidance_request"]]
    if not isinstance(decisions, list) or not decisions:
        raise TokenError("decision batch must contain at least one decision")
    if not isinstance(task_revision, int) or isinstance(task_revision, bool) or task_revision < 1:
        raise TokenError("decision batch task_revision must be a positive integer")
    if not isinstance(packet_digest, str) or not packet_digest.startswith("sha256:"):
        raise TokenError("decision batch packet_digest must be canonical")
    for name, value in (("project_id", project_id), ("session_id", session_id),
                        ("packet_digest", packet_digest), ("session_file", session_file),
                        ("event_file", event_file), ("ssh_host", ssh_host)):
        _validate_text(name, value)
    if not isinstance(ttl_seconds, int) or isinstance(ttl_seconds, bool) or not 1 <= ttl_seconds <= 86400:
        raise TokenError("ttl_seconds must be between 1 and 86400")
    return TokenStore(store_path).issue(
        project_id=project_id,
        session_id=session_id,
        task_revision=task_revision,
        packet_digest=packet_digest,
        session_file=session_file,
        event_file=event_file,
        ssh_host=ssh_host,
        ttl_seconds=ttl_seconds,
        now=now,
    )


def publish_batch(
    store_path: str | Path,
    request_path: str | Path,
    request: dict[str, Any],
    *,
    session_file: str,
    event_file: str,
    ssh_host: str,
    ttl_seconds: int = 900,
    now: datetime | None = None,
) -> str:
    """Publish an authoritative request and its token as one recoverable unit.

    JSON files cannot be replaced atomically as a pair.  The private journal
    therefore acts as a write-ahead transaction: it contains the complete
    request and registry projection, and is replayed before any subsequent
    read if the authority process stops between the two replacements.  The
    caller must print/use the returned token only after this function returns.
    """
    if not isinstance(request, dict):
        raise TokenError("decision batch must be an object")
    project_id = request.get("project_id")
    session_id = request.get("session_id")
    ar = request.get("ar") if isinstance(request.get("ar"), dict) else {}
    task_revision = ar.get("task_revision", request.get("task_revision"))
    packet_digest = request.get("packet_digest")
    decisions = request.get("decisions", request.get("batch"))
    if decisions is None and request.get("guidance_request") is not None:
        decisions = [request["guidance_request"]]
    if not isinstance(decisions, list) or not decisions:
        raise TokenError("decision batch must contain at least one decision")
    if not isinstance(task_revision, int) or isinstance(task_revision, bool) or task_revision < 1:
        raise TokenError("decision batch task_revision must be a positive integer")
    if not isinstance(packet_digest, str) or not packet_digest.startswith("sha256:"):
        raise TokenError("decision batch packet_digest must be canonical")
    for name, value in (("project_id", project_id), ("session_id", session_id),
                        ("packet_digest", packet_digest), ("session_file", session_file),
                        ("event_file", event_file), ("ssh_host", ssh_host)):
        _validate_text(name, value)
    if not isinstance(ttl_seconds, int) or isinstance(ttl_seconds, bool) or not 1 <= ttl_seconds <= 86400:
        raise TokenError("ttl_seconds must be between 1 and 86400")
    target = Path(request_path)
    store = TokenStore(store_path)
    if not target.is_absolute() or not store.path.is_absolute():
        raise TokenError("authoritative publication paths must be absolute")
    with store._exclusive():
        store._recover_publication()
        values = store._read_unrecovered()
        current = _utc(now)
        for _ in range(10):
            token = "".join(secrets.choice(_ALPHABET) for _ in range(TOKEN_LENGTH))
            if not any(hmac.compare_digest(item.get("token_digest", ""), _digest(token)) for item in values):
                break
        else:
            raise TokenError("could not allocate unique batch token")
        record = BatchToken(project_id, session_id, task_revision, packet_digest,
                            session_file, event_file, ssh_host, _stamp(current),
                            _stamp(current + timedelta(seconds=ttl_seconds)),
                            _digest(token)).as_dict()
        registry = {"schema_version": TOKEN_SCHEMA_VERSION, "tokens": [*values, record]}
        journal = store.path.with_name(f".{store.path.name}.publication.json")
        payload = {"schema_version": 1, "request_path": str(target),
                   "registry_path": str(store.path), "request": request,
                   "registry": registry}
        _write_private_json(journal, payload)
        try:
            _write_private_json(target, request)
            _write_private_json(store.path, registry)
            journal.unlink(missing_ok=True)
        except Exception as exc:
            # Keep the journal for the next authority operation to replay;
            # never let a possibly partial publication become a user command.
            raise TokenError("authoritative batch publication failed") from exc
        return token


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
        with self._exclusive():
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

    def consume(
        self,
        token: str,
        *,
        ssh_host: str | None = None,
        now: datetime | None = None,
    ) -> BatchToken:
        """Atomically mark an active token consumed and return its record.

        Consumption is deliberately separate from resolution.  A cancelled
        or failed UI session therefore remains retryable; callers invoke this
        only after the complete event journal has been durably accepted by
        the authoritative host.  The registry lock prevents two remote
        clients from both completing the same batch.
        """
        with self._exclusive():
            values = self._read()
            digest = _validated_digest(token)
            match = next((item for item in values if hmac.compare_digest(item.get("token_digest", ""), digest)), None)
            if match is None:
                raise TokenError("unknown batch token")
            record = BatchToken(**match)
            if record.status != "active":
                raise TokenError("batch token is no longer active")
            if _utc(now) >= _parse_stamp(record.expires_at):
                raise TokenError("batch token has expired")
            if ssh_host is not None and record.ssh_host != ssh_host:
                raise TokenError("batch token ssh_host mismatch")
            match["status"] = "consumed"
            match["consumed_at"] = _stamp(_utc(now))
            self._write(values)
            return BatchToken(**match)

    def revoke(self, token: str) -> None:
        with self._exclusive():
            digest = _validated_digest(token)
            values = self._read()
            matched = False
            for item in values:
                if hmac.compare_digest(item.get("token_digest", ""), digest):
                    item["status"] = "revoked"
                    matched = True
            if not matched:
                raise TokenError("unknown batch token")
            self._write(values)

    @contextmanager
    def _exclusive(self):
        """Serialize registry mutations on POSIX and Windows."""
        lock_path = self.path.with_name(f".{self.path.name}.lock")
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        handle = lock_path.open("a+b")
        try:
            os.chmod(lock_path, 0o600)
        except OSError:
            pass
        try:
            try:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
                unlock = lambda: fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            except ImportError:  # pragma: no cover - exercised on Windows CI
                import msvcrt
                handle.seek(0)
                handle.write(b"0")
                handle.flush()
                acquired = False
                deadline = time.monotonic() + 30
                while not acquired:
                    try:
                        handle.seek(0)
                        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                        acquired = True
                    except OSError:
                        if time.monotonic() >= deadline:
                            raise TokenError("timed out waiting for token registry")
                        time.sleep(0.05)
                unlock = lambda: (handle.seek(0), msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1))
            yield
        finally:
            try:
                unlock()
            except (UnboundLocalError, OSError):
                pass
            handle.close()

    def _read(self) -> list[dict[str, Any]]:
        self._recover_publication()
        return self._read_unrecovered()

    def _read_unrecovered(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        value = json.loads(self.path.read_text(encoding="utf-8"))
        if value.get("schema_version") != TOKEN_SCHEMA_VERSION or not isinstance(value.get("tokens"), list):
            raise TokenError("invalid batch-token registry")
        return value["tokens"]

    def _recover_publication(self) -> None:
        journal = self.path.with_name(f".{self.path.name}.publication.json")
        if not journal.exists():
            return
        try:
            value = json.loads(journal.read_text(encoding="utf-8"))
            if value.get("schema_version") != 1 or value.get("registry_path") != str(self.path):
                raise TokenError("invalid authoritative publication journal")
            request_path = Path(value["request_path"])
            _write_private_json(request_path, value["request"])
            _write_private_json(self.path, value["registry"])
            journal.unlink(missing_ok=True)
        except (OSError, KeyError, TypeError, ValueError) as exc:
            raise TokenError("authoritative publication recovery failed") from exc

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


def _write_private_json(path: Path, value: dict[str, Any]) -> None:
    """Atomically write a private authority artifact and fsync its contents."""
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(path.parent, 0o700)
    except OSError:
        pass
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(value, handle, sort_keys=True, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
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


def _validated_digest(token: str) -> str:
    if not isinstance(token, str) or len(token) != TOKEN_LENGTH or any(char not in _ALPHABET for char in token):
        raise TokenError("invalid batch token")
    return _digest(token)
