"""Revision-bound, privacy-safe operator audit controls.

The audit stream is deliberately separate from the decision event journal.  It
contains operational facts (what happened, when, and whether it was accepted)
but never copies proposal text, Markdown, prompts, host paths, or credentials.
Exports are deterministic and can therefore be attached to a support report
without turning the report into a private decision packet.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import hashlib
import json
from typing import Any, Iterable


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _digest(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    return "sha256:" + hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True)
class AuditContext:
    project_id: str
    ar_id: str
    task_revision: int
    packet_digest: str
    session_id: str

    def __post_init__(self) -> None:
        if not all(isinstance(value, str) and value for value in (self.project_id, self.ar_id, self.packet_digest, self.session_id)):
            raise ValueError("audit context identity fields are required")
        if not isinstance(self.task_revision, int) or self.task_revision < 1:
            raise ValueError("audit task_revision must be positive")
        if not self.packet_digest.startswith("sha256:"):
            raise ValueError("audit packet_digest must be sha256-bound")

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> "AuditContext":
        return cls(value["project_id"], value.get("ar_id") or value.get("ar", {}).get("ar_id", ""),
                   int(value.get("task_revision") or value.get("ar", {}).get("task_revision", 0)),
                   value["packet_digest"], value["session_id"])

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AuditEntry:
    timestamp: str
    event_type: str
    accepted: bool
    sequence: int | None
    detail: str
    payload_digest: str | None = None


class AuditControl:
    """Bounded audit view/export policy shared by GUI and TUI clients."""

    def __init__(self, context: AuditContext, *, max_entries: int = 500,
                 retention_seconds: int | None = None) -> None:
        if max_entries < 1:
            raise ValueError("max_entries must be positive")
        if retention_seconds is not None and retention_seconds < 1:
            raise ValueError("retention_seconds must be positive")
        self.context = context
        self.max_entries = max_entries
        self.retention_seconds = retention_seconds
        self._entries: list[AuditEntry] = []

    def record(self, event_type: str, *, accepted: bool = True, sequence: int | None = None,
               detail: str = "", payload: Any = None, timestamp: str | None = None) -> AuditEntry:
        """Record only metadata; payload is represented by a digest."""
        if not event_type or not isinstance(event_type, str):
            raise ValueError("audit event_type is required")
        entry = AuditEntry(timestamp or _now(), event_type, bool(accepted), sequence,
                           detail[:240], _digest(payload) if payload is not None else None)
        self._entries.append(entry)
        self._trim(now=entry.timestamp)
        return entry

    def _trim(self, *, now: str | None = None) -> None:
        self._entries = self._entries[-self.max_entries:]
        if self.retention_seconds is None or not self._entries:
            return
        current = datetime.fromisoformat((now or _now()).replace("Z", "+00:00"))
        kept: list[AuditEntry] = []
        for entry in self._entries:
            try:
                age = (current - datetime.fromisoformat(entry.timestamp.replace("Z", "+00:00"))).total_seconds()
            except ValueError:
                continue
            if age <= self.retention_seconds:
                kept.append(entry)
        self._entries = kept

    def entries(self) -> tuple[AuditEntry, ...]:
        self._trim()
        return tuple(self._entries)

    def dry_run(self, event_type: str, *, sequence: int | None = None,
                payload: Any = None) -> dict[str, Any]:
        """Validate a prospective operation without recording or submitting it."""
        if not event_type:
            raise ValueError("audit event_type is required")
        if sequence is not None and (not isinstance(sequence, int) or sequence < 1):
            raise ValueError("audit sequence must be positive")
        return {"dry_run": True, "allowed": True, "event_type": event_type,
                "sequence": sequence, "payload_digest": _digest(payload) if payload is not None else None,
                "context": self.context.as_dict()}

    def render(self) -> str:
        lines = [f"Audit / privacy control  {self.context.ar_id} r{self.context.task_revision}",
                 f"session: {self.context.session_id}", f"entries: {len(self.entries())}/{self.max_entries}",
                 f"retention: {self.retention_seconds or 'session'} seconds", ""]
        for entry in self.entries():
            result = "accepted" if entry.accepted else "rejected"
            sequence = f" seq={entry.sequence}" if entry.sequence is not None else ""
            lines.append(f"{entry.timestamp}  {entry.event_type}  {result}{sequence}  {entry.detail}".rstrip())
        if len(lines) == 5:
            lines.append("No operator events recorded.")
        return "\n".join(lines)

    def export(self, *, redact: bool = True) -> dict[str, Any]:
        """Return a support-safe export; private event payloads are never included."""
        if not redact:
            raise ValueError("unredacted audit export is not permitted")
        return {"schema_version": 1, "kind": "awui-audit-export", "redacted": True,
                "context": self.context.as_dict(),
                "entries": [asdict(entry) for entry in self.entries()]}

    def export_json(self) -> str:
        return json.dumps(self.export(), sort_keys=True, indent=2) + "\n"


def audit_from_context(context: dict[str, Any], **kwargs: Any) -> AuditControl:
    """Construct the control plane from the same Coordinator context as a UI."""
    return AuditControl(AuditContext.from_mapping(context), **kwargs)
