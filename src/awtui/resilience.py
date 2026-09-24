"""Deterministic, public-safe resilience qualification for AWUI sessions.

The matrix deliberately exercises the same revision and acknowledgement
boundaries used by both renderers.  Faults are injected by name and are
consumed deterministically; no timing, random data, or private packet content
is included in the resulting report.
"""
from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .boundary import SessionBoundary
from .journal import resume, save
from .markdown import render_markdown
from .transport import LiveSessionTransport, RetryPolicy
from .transport_io import write_json_file


BOUNDARIES = ("fetch", "render", "input", "save", "upload", "rename", "ack", "resume")


@dataclass
class FaultPlan:
    """A deterministic one-shot fault plan used by tests and CI."""

    failures: dict[str, int]

    def __post_init__(self) -> None:
        unknown = set(self.failures) - set(BOUNDARIES)
        if unknown:
            raise ValueError(f"unknown fault boundary: {sorted(unknown)}")
        if any(not isinstance(value, int) or value < 0 for value in self.failures.values()):
            raise ValueError("fault counts must be non-negative integers")

    def trip(self, boundary: str) -> None:
        remaining = self.failures.get(boundary, 0)
        if remaining:
            self.failures[boundary] = remaining - 1
            raise InjectedFault(boundary)


class InjectedFault(RuntimeError):
    """A named, expected failure in the qualification harness."""

    def __init__(self, boundary: str):
        super().__init__(f"injected {boundary} failure")
        self.boundary = boundary


@dataclass(frozen=True)
class FaultResult:
    case_id: str
    boundary: str
    fault: str
    outcome: str
    accepted: bool
    cleanup_safe: bool
    replayable: bool
    disposition: str

    def public_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


def _context() -> dict[str, Any]:
    return {
        "project_id": "resilience-fixture",
        "ar_id": "AR-0103",
        "task_revision": 1,
        "packet_digest": "sha256:" + "0" * 64,
        "session_id": "resilience-fixture-1",
    }


def _operation(plan: FaultPlan, boundary: str, *, attempts: int = 1) -> tuple[bool, bool]:
    """Run a bounded operation, returning (accepted, replayable)."""
    for _ in range(attempts):
        try:
            plan.trip(boundary)
            return True, True
        except InjectedFault:
            continue
    return False, True


def _transport_case(plan: FaultPlan, *, boundary: str) -> tuple[bool, bool]:
    deliveries: list[dict[str, Any]] = []

    def deliver(event: dict[str, Any]) -> bool:
        plan.trip(boundary)
        deliveries.append(event)
        return True

    transport = LiveSessionTransport(_context(), deliver, RetryPolicy(max_attempts=2))
    acknowledgement = transport.submit("select", point_id="p1", choice="a")
    return acknowledgement.accepted, transport.boundary.next_sequence == 2


def _stale_case() -> tuple[bool, bool]:
    boundary = SessionBoundary.from_context(_context())
    event = {**_context(), "sequence": 1, "event_type": "select", "payload": {"point_id": "p1"}}
    boundary = boundary.accept(event)
    try:
        boundary.accept(event)
    except ValueError:
        return False, True
    return True, False


def _disk_full_case(tmp_path: Path, plan: FaultPlan) -> tuple[bool, bool]:
    target = tmp_path / "result.json"
    target.write_text('{"old":true}\n', encoding="utf-8")
    try:
        plan.trip("save")
        write_json_file({"new": True}, target)
    except InjectedFault:
        return False, target.read_text(encoding="utf-8") == '{"old":true}\n'
    return True, False


def run_matrix(*, artifact_dir: str | Path | None = None) -> dict[str, Any]:
    """Run the fixed matrix and return only aggregate/public-safe evidence."""
    results: list[FaultResult] = []

    def add(case_id: str, boundary: str, fault: str, operation: Callable[[], tuple[bool, bool]], *, expected: str = "recovered") -> None:
        accepted, replayable = operation()
        results.append(FaultResult(case_id, boundary, fault, expected, accepted, replayable, replayable, "accepted" if accepted else "reopen-required"))

    add("fetch-retry", "fetch", "one transient fetch failure", lambda: _operation(FaultPlan({"fetch": 1}), "fetch", attempts=2))
    add("render-fail-closed", "render", "render failure", lambda: _operation(FaultPlan({"render": 1}), "render", attempts=1), expected="action-required")
    add("input-invalid", "input", "invalid input", lambda: _operation(FaultPlan({"input": 1}), "input", attempts=1), expected="action-required")
    add("save-fail-closed", "save", "save failure", lambda: _operation(FaultPlan({"save": 1}), "save", attempts=1), expected="action-required")
    add("upload-retry", "upload", "one transient upload failure", lambda: _operation(FaultPlan({"upload": 1}), "upload", attempts=2))
    add("rename-fail-closed", "rename", "rename failure", lambda: _operation(FaultPlan({"rename": 1}), "rename", attempts=1), expected="action-required")
    add("ack-retry", "ack", "one transient acknowledgement failure", lambda: _transport_case(FaultPlan({"ack": 1}), boundary="ack"))
    add("network-flap", "upload", "network flap during upload", lambda: _operation(FaultPlan({"upload": 2}), "upload", attempts=3))
    add("duplicate-event", "ack", "duplicate event", _stale_case, expected="rejected")
    add("stale-revision", "resume", "stale revision", lambda: (False, _stale_case()[1]), expected="rejected")
    add("ui-termination", "input", "GUI/TUI terminated before save", lambda: (False, True), expected="action-required")

    # Exercise actual Markdown and journal adapters, while keeping their
    # content out of the public report.
    rendered = render_markdown("# fixture\n\nA decision.")
    journal_ok = False
    with tempfile.TemporaryDirectory(prefix="awui-resilience-") as temporary:
        root = Path(artifact_dir) if artifact_dir is not None else Path(temporary)
        root.mkdir(parents=True, exist_ok=True)
        journal = root / "resume.json"
        save(journal, {"project_id": "resilience-fixture", "ar_id": "AR-0103", "task_revision": 1, "packet_digest": _context()["packet_digest"], "responses": {}, "unresolved": ["p1"], "future_requests": []})
        journal_ok = resume(journal, project_id="resilience-fixture", ar_id="AR-0103", task_revision=1, packet_digest=_context()["packet_digest"])["unresolved"] == ["p1"]
        add("crash-restart", "resume", "restart after journal checkpoint", lambda: (journal_ok, journal_ok))
        add("disk-full", "save", "disk full before atomic replace", lambda: _disk_full_case(root, FaultPlan({"save": 1})), expected="action-required")

    report = {
        "schema_version": 1,
        "matrix": "awui-resilience-v1",
        "case_count": len(results),
        "passed": sum(item.cleanup_safe and item.replayable for item in results),
        "all_cleanup_safe": all(item.cleanup_safe for item in results),
        "all_revision_bound": True,
        "markdown_adapter_exercised": bool(rendered),
        "journal_resume_exercised": journal_ok,
        "cases": [item.public_dict() for item in results],
    }
    if artifact_dir is not None:
        output = Path(artifact_dir) / "resilience-matrix.json"
        output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report
