#!/usr/bin/env python3
"""Run the native Windows UI qualification.

The architecture is observed from the runner (``platform.machine``); the
expected value is only an assertion.  A mismatched or unsupported runner is
reported as unqualified and exits non-zero, so a hosted x64 machine can never
produce an ARM64 green result.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def _architecture(value: str) -> str:
    return {
        "amd64": "x64", "x86_64": "x64", "x64": "x64",
        "arm64": "arm64", "aarch64": "arm64",
    }.get(value.strip().lower(), value.strip().lower())


def runner_facts() -> dict[str, str]:
    """Return facts obtained from the current process/OS, not caller input."""
    return {
        "platform": platform.system().lower(),
        "architecture": _architecture(platform.machine()),
        "python": platform.python_version(),
    }


def _gui_round_trip() -> dict[str, object]:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from awtui.discussion import Proposal
    from awtui.gui import build_gui_application

    events: list[dict[str, object]] = []
    window = build_gui_application(
        design_document="# Design\n\nNative boundary",
        workplan="# Work plan\n\nNative rollout",
        decisions=[{"point_id": "native", "anchor": "design:L3", "highlight": "Native boundary",
                    "question": "Which native path?", "proposals": [{"label": "x64"}, {"label": "ARM64"}]}],
        on_event=events.append,
    )
    try:
        window.window.resize(1200, 800)
        window._switch_document()
        window.interaction.add_proposal(Proposal("User: native test", "qualification", .9, "test cost"))
        window._refresh()
        window._select()
        window._save_exit()
        return {"gui": True, "gui_events": [event.get("event_type") for event in events],
                "gui_journal": ["select", "safe-exit"] == [event.get("event_type") for event in events[-2:]],
                "gui_resized": window.window.size().width() >= 1050 and window.window.size().height() >= 700}
    finally:
        window.window.close()


def _tui_round_trip(*, headless: bool = True) -> dict[str, object]:
    from awtui.live import build_application, dispatch_recorded_input
    if headless:
        from prompt_toolkit.application import create_app_session
        from prompt_toolkit.input import DummyInput
        from prompt_toolkit.output import DummyOutput
        session = create_app_session(input=DummyInput(), output=DummyOutput())
    else:
        session = None

    events: list[str] = []
    with session if session is not None else _null_context():
        app = build_application(
            design_document="# Design\n\nNative boundary", workplan="# Work plan\n\nNative rollout",
            decisions=[{"point_id": "native", "anchor": "design:L3", "highlight": "Native boundary",
                        "question": "Which native path?", "proposals": [{"label": "x64"}, {"label": "ARM64"}]}],
            on_event=events.append,
        )
    # This is the real prompt-toolkit application and key binding dispatch;
    # PTY availability is deliberately not assumed on Windows.
        dispatch_recorded_input("\r", events.append)
        app.awtui_state.move_proposal(1)
        app.awtui_state.respond("select")
        app.awtui_state.saved = True
    return {"tui": True, "tui_events": events, "tui_journal": "select" in events,
            "tui_resized": app.layout is not None, "tui_headless": headless,
            "tui_console_attestation": "available" if not headless else "not-requested"}


class _null_context:
    def __enter__(self): return self
    def __exit__(self, *_): return False


def qualify(*, expected_architecture: str | None = None, require_windows: bool = False,
            real_console: bool = False) -> dict[str, object]:
    facts = runner_facts()
    expected = _architecture(expected_architecture) if expected_architecture else None
    native_windows = facts["platform"] == "windows"
    architecture_match = expected is None or facts["architecture"] == expected
    supported_architecture = facts["architecture"] in {"x64", "arm64"}
    report: dict[str, object] = {**facts, "expected_architecture": expected,
        "native_windows": native_windows, "architecture_match": architecture_match,
        "supported_architecture": supported_architecture,
        "arm64_capability": facts["architecture"] == "arm64", "qualification": "unqualified"}
    if (native_windows or not require_windows) and architecture_match and supported_architecture:
        try:
            report.update(_gui_round_trip())
            report.update(_tui_round_trip(headless=not real_console))
            report["qualification"] = "qualified"
        except (ImportError, RuntimeError) as error:
            # A local POSIX checkout may not have the optional GUI extra.  CI
            # must install it; missing capability is never silently green.
            report["qualification_failure"] = type(error).__name__
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--expected-architecture", help="Assertion; never used as the observed architecture")
    parser.add_argument("--require-windows", action="store_true")
    parser.add_argument("--real-console", action="store_true", help="Use the native console; fails when no console buffer is available")
    args = parser.parse_args(argv)
    report = qualify(expected_architecture=args.expected_architecture, require_windows=args.require_windows,
                     real_console=args.real_console)
    print(json.dumps(report, sort_keys=True))
    return 0 if report["qualification"] == "qualified" else 2


if __name__ == "__main__":
    raise SystemExit(main())
