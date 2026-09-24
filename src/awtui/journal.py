"""Atomic, revision-bound public session journal."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def _paused_record(record: dict[str, Any]) -> dict[str, Any]:
    """Validate the public, non-secret fields used by a paused-session card."""
    required = {"session_id", "project_id", "ar_id", "task_revision", "packet_digest", "session_file", "unresolved"}
    if not required.issubset(record) or not all(isinstance(record.get(key), str) and record[key] for key in ("session_id", "project_id", "ar_id", "packet_digest", "session_file")):
        raise ValueError("paused session record is incomplete")
    if not isinstance(record["task_revision"], int) or record["task_revision"] < 1:
        raise ValueError("paused session task_revision must be positive")
    if not isinstance(record["unresolved"], list) or any(not isinstance(item, str) or not item for item in record["unresolved"]):
        raise ValueError("paused session unresolved points must be strings")
    return record


def render_paused_cards(records: list[dict[str, Any]], *, selected: int = 0) -> str:
    """Render bounded, privacy-safe cards for sessions awaiting resumption."""
    if not records:
        return "Paused sessions\nnone"
    lines = [f"Paused sessions ({len(records)})"]
    for index, raw in enumerate(records):
        record = _paused_record(raw)
        marker = "▶" if index == selected else " "
        unresolved = ", ".join(record["unresolved"]) or "none"
        lines.extend((
            f"{marker} {record['session_id']}  {record['ar_id']} r{record['task_revision']}",
            f"    unresolved: {unresolved}",
            f"    resume: awtui-live --session-file {record['session_file']}",
        ))
    return "\n".join(lines)


def resume_event(record: dict[str, Any]) -> dict[str, Any]:
    """Create the host-transport event used to request a paused-session resume."""
    value = _paused_record(record)
    return {"event_type": "resume", "session_id": value["session_id"], "task_revision": value["task_revision"],
            "packet_digest": value["packet_digest"], "payload": {"session_file": value["session_file"], "unresolved": list(value["unresolved"])}}


def save(path: Path, session: dict[str, Any]) -> None:
    required = {"project_id", "ar_id", "task_revision", "packet_digest", "responses", "unresolved", "future_requests"}
    if set(session) != required or not isinstance(session["responses"], dict) or not isinstance(session["unresolved"], list) or not isinstance(session["future_requests"], list):
        raise ValueError("incomplete public session journal")
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(session, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def resume(path: Path, *, project_id: str, ar_id: str, task_revision: int, packet_digest: str) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    for key, expected in (("project_id", project_id), ("ar_id", ar_id), ("task_revision", task_revision), ("packet_digest", packet_digest)):
        if value.get(key) != expected:
            raise ValueError(f"stale journal {key}")
    return value


def render_history(session: dict[str, Any]) -> str:
    """Render public journal state for the helper pane without private transcripts."""
    lines = [f"Journal {session['ar_id']} revision {session['task_revision']}"]
    lines.append(f"answered: {len(session['responses'])}")
    lines.append(f"unresolved: {', '.join(session['unresolved']) or 'none'}")
    requests = session["future_requests"]
    lines.append("future ARs: " + (", ".join(requests) if requests else "none"))
    return "\n".join(lines)
