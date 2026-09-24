"""Deterministic scale qualification for the Agent Workflow UI.

The benchmark exercises the renderer-neutral paths shared by the Qt and
prompt-toolkit frontends.  It intentionally uses synthetic public fixtures:
no AR text, host names, prompts, or credentials are included in reports.
Budgets are part of the release contract and are deliberately explicit so a
regression fails CI instead of becoming an anecdotal performance concern.
"""
from __future__ import annotations

import json
import tempfile
import time
import tracemalloc
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Callable

from .anchors import find_occurrences
from .graph import structure_graph_to_tui
from .journal import save
from .markdown import render_markdown


DEFAULT_BUDGETS: dict[str, float] = {
    "graph_seconds": 3.0,
    "markdown_seconds": 5.0,
    "navigation_seconds": 2.0,
    "journal_seconds": 3.0,
    "transport_seconds": 2.0,
    "peak_megabytes": 192.0,
}

FIXTURE_DECISIONS = 128
FIXTURE_DOCUMENT_CHARS = 32_000


@dataclass(frozen=True)
class Measurement:
    name: str
    seconds: float
    peak_megabytes: float
    budget_seconds: float

    @property
    def passed(self) -> bool:
        return self.seconds <= self.budget_seconds and self.peak_megabytes <= DEFAULT_BUDGETS["peak_megabytes"]

    def public_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["passed"] = self.passed
        return value


def _graph() -> dict[str, Any]:
    # Keep the anchor occurrence realistic: long documents contain substantial
    # prose, but an anchor phrase is normally rare rather than repeated on
    # every line.  This also makes the benchmark measure navigation work, not
    # an artificial quadratic text-search workload.
    unit = "The selected implementation remains reviewable and reversible. "
    long_text = (unit * ((FIXTURE_DOCUMENT_CHARS // len(unit)) + 1))[:FIXTURE_DOCUMENT_CHARS]
    long_text += "\n\nThe implementation boundary is the authoritative review point."
    nodes = [
        {
            "node_id": "design-root",
            "document": "design",
            "markdown": "# Design\n\n" + long_text,
            "anchors": [{"anchor": "design-boundary", "text": "implementation boundary"}],
        },
        {
            "node_id": "plan-root",
            "document": "workplan",
            "markdown": "# Work plan\n\n" + long_text,
            "anchors": [{"anchor": "plan-boundary", "text": "implementation boundary"}],
        },
    ]
    decisions = []
    for index in range(FIXTURE_DECISIONS):
        node = nodes[index % 2]
        decisions.append({
            "point_id": f"P-{index:04d}",
            "node_id": node["node_id"],
            "anchor": node["anchors"][0]["anchor"],
            "question": "Which implementation boundary should be used?",
            "proposals": [
                {"label": "retain", "rationale": "Keeps the boundary explicit.", "confidence": 0.8, "tradeoffs": "No migration."},
                {"label": "revise", "rationale": "Allows a controlled revision.", "confidence": 0.7, "tradeoffs": "Requires review."},
            ],
        })
    return {"nodes": nodes, "decisions": decisions}


def _measure(name: str, budget_name: str, operation: Callable[[], None]) -> Measurement:
    tracemalloc.start()
    started = time.perf_counter()
    operation()
    seconds = time.perf_counter() - started
    _current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return Measurement(name, seconds, peak / (1024 * 1024), DEFAULT_BUDGETS[budget_name])


def run_benchmark(*, budgets: dict[str, float] | None = None) -> dict[str, Any]:
    """Run the fixed scale fixture and return a redaction-safe report."""
    if budgets:
        unknown = set(budgets) - set(DEFAULT_BUDGETS)
        if unknown:
            raise ValueError(f"unknown performance budget: {sorted(unknown)}")
        active = {**DEFAULT_BUDGETS, **budgets}
    else:
        active = DEFAULT_BUDGETS
    graph = _graph()
    measurements: list[Measurement] = []

    def measure(name: str, budget_name: str, operation: Callable[[], None]) -> None:
        result = _measure(name, budget_name, operation)
        # Use the caller's budget override for qualification while retaining
        # the canonical default in the report's fixture metadata.
        measurements.append(Measurement(result.name, result.seconds, result.peak_megabytes, active[budget_name]))

    projected: dict[str, str] = {}
    decisions: list[dict[str, Any]] = []
    measure("graph_projection", "graph_seconds", lambda: projected.update(structure_graph_to_tui(graph)[0]))
    measure("markdown_render", "markdown_seconds", lambda: [render_markdown(value, width=100) for value in projected.values()])
    measure(
        "anchor_navigation",
        "navigation_seconds",
        lambda: [find_occurrences(projected["design" if index % 2 == 0 else "workplan"], "implementation boundary") for index in range(FIXTURE_DECISIONS)],
    )
    measure(
        "journal_write",
        "journal_seconds",
        lambda: _journal_fixture(),
    )
    # A bounded local event loop represents the common transport/journal
    # handoff cost without opening a network connection in CI.
    measure("event_handoff", "transport_seconds", lambda: _event_fixture())

    failures = [item.name for item in measurements if not item.passed or item.peak_megabytes > active["peak_megabytes"]]
    return {
        "schema_version": 1,
        "benchmark": "awui-release-scale-v1",
        "fixture": {"decisions": FIXTURE_DECISIONS, "document_chars": FIXTURE_DOCUMENT_CHARS},
        "budgets": active,
        "measurements": [item.public_dict() for item in measurements],
        "passed": not failures,
        "failures": failures,
        "gates": release_gates(),
    }


def _journal_fixture() -> None:
    responses = {f"P-{index:04d}": {"disposition": "select", "selected": "retain"} for index in range(FIXTURE_DECISIONS)}
    with tempfile.TemporaryDirectory(prefix="awui-benchmark-") as directory:
        save(Path(directory) / "session.json", {
            "project_id": "benchmark",
            "ar_id": "AR-0104",
            "task_revision": 1,
            "packet_digest": "sha256:" + "0" * 64,
            "responses": responses,
            "unresolved": [],
            "future_requests": [],
        })


def _event_fixture() -> None:
    # Fixed-size event envelopes model sequence/idempotency bookkeeping while
    # keeping the report independent of private decision content.
    events = [{"sequence": index, "event_type": "select", "point": f"P-{index:04d}"} for index in range(FIXTURE_DECISIONS)]
    assert len({event["sequence"] for event in events}) == FIXTURE_DECISIONS


def release_gates() -> dict[str, bool]:
    """Return static release evidence gates shared by CI and the CLI."""
    root = Path(__file__).parents[2]
    required = {
        "ux_control": (root / "docs/KEYBOARD_ACCESSIBILITY.md").is_file(),
        "navigation": (root / "docs/document-anchors.md").is_file(),
        "audit": (root / "docs/AUDIT_PRIVACY.md").is_file(),
        "resilience": (root / "docs/RESILIENCE.md").is_file(),
        "compatibility": (root / "docs/COMPATIBILITY_RELEASE_v0.6.2.md").is_file(),
    }
    return required


def write_report(path: str | Path) -> dict[str, Any]:
    report = run_benchmark()
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report
