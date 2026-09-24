#!/usr/bin/env python3
"""Dependency-free structural validation for AR/TUI envelopes."""
import json
import re
import sys
from pathlib import Path

AR = re.compile(r"^AR-[0-9]{4}$")
DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
EVENTS = {"acknowledge", "directive", "clarify", "select", "reject", "request-more-evidence", "add-proposal", "safe-exit", "reopen", "reconciled"}


def check_context(value):
    required = {"project_id", "ar_id", "task_revision", "packet_digest", "contract_versions", "session_id"}
    if set(value) - required - {"predecessor_events"} or not required <= set(value):
        return False
    return isinstance(value["project_id"], str) and bool(value["project_id"]) and bool(AR.fullmatch(value["ar_id"])) and isinstance(value["task_revision"], int) and value["task_revision"] > 0 and bool(DIGEST.fullmatch(value["packet_digest"])) and isinstance(value["contract_versions"], dict) and bool(value["contract_versions"]) and isinstance(value["session_id"], str) and bool(value["session_id"])


def check_event(value):
    required = {"project_id", "ar_id", "task_revision", "packet_digest", "session_id", "sequence", "event_type", "payload"}
    if set(value) != required or not check_context({k: value[k] for k in ("project_id", "ar_id", "task_revision", "packet_digest", "session_id")} | {"contract_versions": {"tui": "1"}}):
        return False
    return value["sequence"] > 0 and value["event_type"] in EVENTS and isinstance(value["payload"], dict)


def main():
    value = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    kind = sys.argv[2]
    ok = check_context(value) if kind == "context" else check_event(value) if kind == "event" else False
    if not ok:
        print("AWT-ENVELOPE-FAIL", file=sys.stderr)
        return 1
    print("AWT-ENVELOPE-PASS: " + kind)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
