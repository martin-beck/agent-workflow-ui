#!/usr/bin/env python3
"""Validate the deterministic synthetic TUI scenario corpus."""
from __future__ import annotations
import json
import re
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1] / "src"))
from awtui.live import RECORDED_CONTROLS, dispatch_recorded_input

ALLOWED = {"enter", "r", "c", "m", "a", "s", "o", "q", "escape", "up", "down", "left", "right", "tab", "workplan", "design", "page-up", "page-down", "dashboard", "drill-down", "drill-up", "directive", "pause", "resume"}
HEX_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")

def validate(path: Path) -> list[str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    scenarios = data.get("scenarios", [])
    errors = []
    if data.get("schema_version") != 1 or len(scenarios) < 15:
        errors.append("corpus must be schema version 1 with at least 15 scenarios")
    ids = [item.get("id") for item in scenarios]
    if len(ids) != len(set(ids)):
        errors.append("scenario ids must be unique")
    covered_events = {event for item in scenarios for event in item.get("expected_events", [])}
    missing_events = set(RECORDED_CONTROLS.values()) - covered_events
    if missing_events:
        errors.append("corpus lacks scenarios for controls: " + ", ".join(sorted(missing_events)))
    for item in scenarios:
        if not item.get("id") or not item.get("title") or not item.get("actions"):
            errors.append(f"incomplete scenario: {item.get('id')}")
        if any(action not in ALLOWED for action in item.get("actions", [])):
            errors.append(f"unknown action: {item.get('id')}")
        context = item.get("context", {})
        for key in ("project_id", "ar_id", "task_revision", "packet_digest", "session_id"):
            if key not in context:
                errors.append(f"{item.get('id')} missing context {key}")
        for key in ("project_id", "ar_id", "session_id"):
            if key in context and (not isinstance(context[key], str) or not SAFE_ID.fullmatch(context[key])):
                errors.append(f"{item.get('id')} invalid context {key}")
        if not isinstance(context.get("task_revision"), int) or context.get("task_revision", 0) < 1:
            errors.append(f"{item.get('id')} task_revision must be a positive integer")
        if not isinstance(context.get("packet_digest"), str) or not HEX_DIGEST.fullmatch(context["packet_digest"]):
            errors.append(f"{item.get('id')} packet_digest must be sha256 plus 64 lowercase hex digits")
        if len(item.get("actions", [])) > 32:
            errors.append(f"{item.get('id')} action trace is unbounded")
        # Navigation actions are exercised by the live replay; only controls
        # emit lifecycle events in this compact event-trace projection.
        replayed = dispatch_recorded_input("".join("\n" if a == "enter" else "\x1b" if a == "escape" else a for a in item.get("actions", []) if a not in {"up", "down", "left", "right", "tab", "workplan", "design", "page-up", "page-down", "dashboard", "drill-down", "drill-up", "resume"}), lambda _event: None)
        replayed.extend({"dashboard": "dashboard", "drill-down": "board-drill-down", "drill-up": "board-drill-up", "resume": "resume"}[action] for action in item.get("actions", []) if action in {"dashboard", "drill-down", "drill-up", "resume"})
        # Board actions are emitted in input order; preserve the order when a
        # scenario combines ordinary controls with hierarchy navigation.
        if item.get("flow") in {"dashboard", "drill-down", "pause-resume"}:
            replayed = ["dashboard" if action == "dashboard" else "board-drill-down" if action == "drill-down" else "board-drill-up" if action == "drill-up" else "resume" if action == "resume" else event for action, event in zip(item.get("actions", []), replayed)]
        if replayed != item.get("expected_events", []):
            errors.append(f"{item.get('id')} expected_events do not match live control replay")
    return errors

if __name__ == "__main__":
    problems = validate(Path(sys.argv[1] if len(sys.argv) > 1 else "scenarios/corpus.json"))
    if problems:
        print("\n".join(problems), file=sys.stderr)
        raise SystemExit(1)
    print("scenario corpus valid")
