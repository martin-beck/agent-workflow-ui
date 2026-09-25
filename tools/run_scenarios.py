#!/usr/bin/env python3
"""Replay synthetic workflows and generate deterministic screenshot artifacts."""
from __future__ import annotations
import argparse
import html
import json
import re
import sys
import threading
import time
from io import StringIO
from pathlib import Path
ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).parents[1] / "src"))
from awtui.live import dispatch_recorded_input
from awtui.scenario_helper import demo_decisions
from tools.validate_scenarios import validate

_ACTION_KEYS = {
    "enter": "\n",
    "escape": "\x1b",
    "r": "r",
    "c": "c",
    "m": "m",
    "a": "a",
    "s": "s",
    "o": "o",
    "q": "q",
}
_NAVIGATION_KEYS = {
    "up": b"\x1b[A",
    "down": b"\x1b[B",
    "left": b"\x1b[D",
    "right": b"\x1b[C",
    "tab": b"\t",
    "workplan": b"w",
    "design": b"d",
    "page-up": b"\x1b[5~",
    "page-down": b"\x1b[6~",
    "dashboard": b"b",
    "drill-down": b"]",
    "drill-up": b"[",
    "resume": b"R",
}
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
# A visible human-paced cadence without making CI regenerate 20 casts for
# minutes. The cast timestamps preserve this cadence for asciinema players.
_HUMAN_DELAY = 0.10

def _live_demo_state(scenario: dict, events: list[str]):
    """Construct and exercise the same live multi-pane model used by the helper."""
    from awtui.live import build_application
    decisions = demo_decisions(scenario)
    app = build_application(
        design_document=f"DESIGN DOCUMENT\nScenario: {scenario['title']}\nAnchors: design:L10, design:L30",
        workplan=f"WORKPLAN\nScenario: {scenario['title']}\nAnchor: workplan:L20",
        decisions=decisions,
    )
    state = app.awtui_state
    for event in events:
        if event in {"select", "reject", "clarify"}:
            state.respond(event)
        elif event == "add-proposal":
            from awtui.discussion import Proposal
            state.add_proposal(Proposal("User: Demo proposal", "Synthetic rationale", .7, "Synthetic trade-off"))
    return app, len(decisions)


def _terminal_snapshot(app) -> list[str]:
    """Return the actual live panes as short, accessible screenshot content."""
    panes = getattr(app, "awtui_panes", ())
    names = ("DOCUMENT", "DECISIONS", "HELPER")
    lines: list[str] = []
    for name, pane in zip(names, panes):
        lines.append(f"--- {name} PANE ---")
        lines.extend(pane.text.splitlines()[:12])
    return lines


def _cast_frame(app) -> str:
    """Build a stable terminal frame from the actual live widget state.

    Prompt-toolkit's renderer emits timing-sensitive cursor repaint bytes. For
    committed documentation, capture the post-input widget frame instead;
    this keeps the asciinema animation deterministic while still exercising
    and displaying the real TUI state after every human-paced key action.
    """
    panes = getattr(app, "awtui_panes", ())
    sections = []
    for name, pane in zip(("DOCUMENT", "DECISIONS", "HELPER"), panes):
        sections.append(f"--- {name} PANE ---\n{pane.text}")
    if getattr(app.editor, "visible", False):
        sections.append(f"--- PROPOSAL INPUT ---\n{app.editor.text}")
    sections.append(f"--- FOOTER ---\n{app.awtui_footer.text}")
    return "\x1b[2J\x1b[H" + "\n\n".join(sections) + "\n"


def screenshot(scenario: dict, events: list[str], snapshot: list[str] | None = None) -> str:
    app, decision_count = _live_demo_state(scenario, events)
    snapshot = snapshot or _terminal_snapshot(app)
    title = f"{scenario['title']} ({scenario['id']})"
    event_trace = " -> ".join(events) or "none"
    lines = [title, f"AR: {scenario['context']['ar_id']}  revision: {scenario['context']['task_revision']}", "DOCUMENTS: design <-> workplan", f"DECISIONS: {decision_count} anchored points", "", "INPUT: " + " ".join(scenario["actions"]), "EVENTS: " + event_trace, ""] + snapshot + ["", "Human-in-the-loop decision session complete"]
    text = "\n".join(lines)
    rows = "".join(f'<text x="24" y="{42 + i * 24}">{html.escape(line)}</text>' for i, line in enumerate(lines))
    description = f"Synthetic TUI workflow. Input actions: {' '.join(scenario['actions'])}. Emitted events: {event_trace}."
    # Keep the SVG useful to screen readers as well as visual documentation.
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="900" height="240" '
        f'role="img" aria-labelledby="title-{html.escape(scenario["id"])} desc-{html.escape(scenario["id"])}">'
        f'<title id="title-{html.escape(scenario["id"])}">{html.escape(title)}</title>'
        f'<desc id="desc-{html.escape(scenario["id"])}">{html.escape(description)}</desc>'
        '<rect width="100%" height="100%" fill="#101820"/>'
        f'<g fill="#d7f9ff" font-family="monospace" font-size="16">{rows}</g></svg>\n'
    )


def _action_chunks(action: str) -> list[bytes]:
    """Encode one corpus action for the real prompt-toolkit input parser."""
    if action in _NAVIGATION_KEYS:
        return [_NAVIGATION_KEYS[action]]
    if action == "enter":
        return [b"\n"]
    if action == "escape":
        return [b"\x1b"]
    if action == "a":
        # Drive the same four-field form a human uses.  Each chunk is paced by
        # the replay loop so focus changes are observable and action letters
        # remain ordinary text while editing.
        return [
            b"a", b"Scenario proposal", b"\t", b"Synthetic rationale",
            b"\t", b"0.7", b"\t", b"Synthetic trade-off", b"\n", b"\n",
        ]
    if len(action) == 1:
        return [action.encode()]
    raise ValueError(f"unknown live action: {action}")


def _run_live_replay(scenario: dict) -> tuple[object, list[str], list[str], str]:
    """Drive the real app and record its terminal output as asciinema v2."""
    from prompt_toolkit.input import create_pipe_input
    from prompt_toolkit.output import create_output
    from awtui.live import build_application

    decisions = demo_decisions(scenario)
    board_request = None
    if scenario.get("flow") in {"dashboard", "drill-down"}:
        board_request = {
            "schema_version": "1.0", "kind": "coordinator-board-request",
            **scenario["context"], "rollup_revision": 3,
            "pages": [{"page_id": "overview", "title": "Overview", "status": "active", "completed": 3, "total": 5},
                       {"page_id": "bottlenecks", "title": "Bottlenecks", "status": "watch", "blocked": 1}],
            "hierarchy": [{"node_id": "company", "title": "Example company", "kind": "company", "level": 0, "status": "active", "total": 5},
                          {"node_id": "team", "title": "Platform team", "kind": "team", "level": 1, "parent_id": "company", "status": "active", "total": 3},
                          {"node_id": "task", "title": "Directive integration", "kind": "task", "level": 2, "parent_id": "team", "status": "blocked", "blocked": 1}],
        }
    paused_sessions = []
    if scenario.get("flow") == "pause-resume":
        paused_sessions = [{"session_id": "paused-demo", **scenario["context"], "session_file": "/state/paused-demo.json", "unresolved": ["p2"]}]
    if scenario.get("flow") == "rollback":
        decisions[1]["rollback_of"] = decisions[0]["point_id"]
        decisions[1]["conflict_reason"] = "new evidence diverged from the earlier choice"
    events: list[str] = []
    app = build_application(
        design_document=f"# Design document\n\nScenario: {scenario['title']}\n\n## Design boundary\nThe design boundary is reviewed before implementation.\n\n## Validation path\nThe validation path records independent evidence.",
        workplan=f"# Workplan\n\nScenario: {scenario['title']}\n\n## Rollout step\nThe rollout step is selected in the batch decision.",
        decisions=decisions,
        on_event=lambda event: events.append(event if isinstance(event, str) else event.get("event_type", "resume")),
        board_request=board_request,
        paused_sessions=paused_sessions,
    )
    stream = StringIO()
    with create_pipe_input() as pipe:
        app.input = pipe
        app.renderer.output = create_output(stream, always_prefer_tty=True)
        ready = threading.Event()
        failure: list[BaseException] = []

        def run() -> None:
            try:
                app.run(pre_run=ready.set, set_exception_handler=False)
            except BaseException as error:  # pragma: no cover - defensive boundary
                failure.append(error)

        thread = threading.Thread(target=run, daemon=True)
        thread.start()
        if not ready.wait(3):
            raise RuntimeError("scenario TUI did not start")
        # Exercise all non-event navigation paths on every recording. These
        # are intentionally human-paced so the casts are useful to reviewers.
        replay_actions = ["down", "up", "right", "left", "tab", "workplan", "design", "page-down", "page-up"] + list(scenario["actions"])
        cast_events: list[list[object]] = []
        elapsed = 0.0
        # ``pre_run`` fires just before prompt-toolkit's first render.  Give
        # that render one human-paced tick before injecting the first key so
        # scheduling differences between hosted and local runners cannot drop
        # or reorder the initial navigation frame.
        time.sleep(_HUMAN_DELAY)
        for action in replay_actions:
            for chunk_index, chunk in enumerate(_action_chunks(action)):
                # Page navigation intentionally focuses the document pane.
                # Return focus to the decision pane before scenario actions so
                # proposal entry exercises the same path as a user returning
                # from document review.
                if chunk_index == 0 and action not in {"page-up", "page-down"} and action in scenario["actions"]:
                    app.layout.focus(app.awtui_panes[1])
                pipe.send_bytes(chunk)
                time.sleep(_HUMAN_DELAY)
                cast_events.append([round(elapsed, 3), "o", _cast_frame(app)])
                elapsed += _HUMAN_DELAY
                if not thread.is_alive():
                    break
            if not thread.is_alive():
                break
            # Live sessions now protect unresolved/unsaved work with an exit
            # confirmation.  Scenario replay completes that explicit prompt
            # with Enter so every generated workflow still terminates.
            if action == "q" and thread.is_alive():
                app.awtui_state.input_mode = False
                app.awtui_state.proposal_confirm = False
                pipe.send_bytes(b"\x1b[C\r")
                time.sleep(_HUMAN_DELAY)
                cast_events.append([round(elapsed, 3), "o", _cast_frame(app)])
                elapsed += _HUMAN_DELAY
                break
        if thread.is_alive():
            app.awtui_state.input_mode = False
            app.awtui_state.proposal_confirm = False
            pipe.send_bytes(b"q")
            time.sleep(_HUMAN_DELAY)
            cast_events.append([round(elapsed, 3), "o", _cast_frame(app)])
            pipe.send_bytes(b"\x1b[C\r")
            time.sleep(_HUMAN_DELAY)
            cast_events.append([round(elapsed + _HUMAN_DELAY, 3), "o", _cast_frame(app)])
        thread.join(3)
        if thread.is_alive():
            raise RuntimeError("scenario TUI did not exit")
    if failure:
        raise RuntimeError(f"scenario TUI failed: {type(failure[0]).__name__}")
    if events != scenario["expected_events"]:
        raise ValueError(f"{scenario['id']}: expected {scenario['expected_events']}, got {events}")
    header = {"version": 2, "width": 120, "height": 40, "timestamp": 0, "env": {"TERM": "xterm-256color"}}
    cast = json.dumps(header, separators=(",", ":"), ensure_ascii=False) + "\n"
    cast += "".join(json.dumps(item, ensure_ascii=False, separators=(",", ":")) + "\n" for item in cast_events)
    return app, events, _terminal_snapshot(app), cast


def _encoded_input(actions: list[str]) -> str:
    """Encode corpus action names into the exact keys used by live replay."""
    try:
        return "".join(_ACTION_KEYS[action] for action in actions if action in _ACTION_KEYS)
    except KeyError as error:
        raise ValueError(f"unknown scenario action: {error.args[0]}") from error


def _artifacts(root: Path = ROOT) -> dict[Path, str]:
    corpus_path = root / "scenarios/corpus.json"
    problems = validate(corpus_path)
    if problems:
        raise ValueError("invalid scenario corpus:\n" + "\n".join(problems))
    corpus = json.loads(corpus_path.read_text(encoding="utf-8"))
    results = []
    screenshots = {}
    recordings = {}
    for scenario in corpus["scenarios"]:
        scenario_id = scenario["id"]
        if not _SAFE_ID.fullmatch(scenario_id):
            raise ValueError(f"unsafe scenario id for artifact path: {scenario_id!r}")
        _app, events, snapshot, cast = _run_live_replay(scenario)
        filename = f"{scenario_id}.svg"
        screenshots[Path("docs/screenshots") / filename] = screenshot(scenario, events, snapshot)
        recording = f"docs/recordings/{scenario_id}.cast"
        recordings[Path(recording)] = cast
        decision_count = len(demo_decisions(scenario))
        results.append({"id": scenario_id, "title": scenario["title"], "events": events, "decision_count": decision_count, "screenshot": f"docs/screenshots/{filename}", "gui_screenshot": f"docs/gui-screenshots/{scenario_id}.png", "recording": recording})
    manifest = {"schema_version": 1, "scenario_count": len(results), "results": results}
    artifacts = dict(screenshots)
    artifacts.update(recordings)
    artifacts[Path("artifacts/scenario-results.json")] = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    return artifacts


def _current_artifacts(root: Path) -> dict[Path, str]:
    paths = list((root / "docs/screenshots").glob("*.svg")) + list((root / "docs/recordings").glob("*.cast")) + [root / "artifacts/scenario-results.json"]
    return {path.relative_to(root): path.read_text(encoding="utf-8") for path in paths if path.exists()}

def generate(root: Path = ROOT) -> dict:
    artifacts = _artifacts(root)
    screenshot_dir = root / "docs/screenshots"
    screenshot_dir.mkdir(parents=True, exist_ok=True)
    artifact_dir = root / "artifacts"
    artifact_dir.mkdir(exist_ok=True)
    recording_dir = root / "docs/recordings"
    recording_dir.mkdir(parents=True, exist_ok=True)
    expected_paths = set(artifacts)
    # Remove only stale generated screenshots after all replay checks pass.
    for path in screenshot_dir.glob("*.svg"):
        if path.relative_to(root) not in expected_paths:
            path.unlink()
    for path in recording_dir.glob("*.cast"):
        if path.relative_to(root) not in expected_paths:
            path.unlink()
    for relative, content in artifacts.items():
        target = root / relative
        temporary = target.with_name(target.name + ".tmp")
        temporary.write_text(content, encoding="utf-8")
        temporary.replace(target)
    return json.loads(artifacts[Path("artifacts/scenario-results.json")])

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="regenerate in memory and fail if tracked artifacts differ")
    args = parser.parse_args()
    if args.check:
        expected = _artifacts(ROOT)
        return 0 if _current_artifacts(ROOT) == expected else 1
    print(json.dumps(generate(ROOT), indent=2, sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
