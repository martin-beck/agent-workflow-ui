"""Environment-aware GUI/TUI selection for Coordinator handoff."""
from __future__ import annotations

import os


def detect_ui_backend(*, environ: dict[str, str] | None = None) -> str:
    env = os.environ if environ is None else environ
    if env.get("AWUI_BACKEND") in {"gui", "tui"}:
        return env["AWUI_BACKEND"]
    if env.get("DISPLAY") or env.get("WAYLAND_DISPLAY"):
        return "gui"
    return "tui"


def backend_for_invocation(program: str, *, environ: dict[str, str] | None = None) -> str:
    """Honor explicit GUI/TUI entry points before display auto-detection."""
    from pathlib import Path
    if Path(program).stem.lower() in {"awui-live", "awui_live"}:
        return "gui"
    return detect_ui_backend(environ=environ)


def command_for_environment(*, environ: dict[str, str] | None = None, session_file: str | None = None) -> list[str]:
    command = "awui-live" if detect_ui_backend(environ=environ) == "gui" else "awtui-live"
    return [command, "--session-file", session_file] if session_file else [command]


def main() -> int:
    import argparse
    import sys
    parser = argparse.ArgumentParser(prog="awui-live")
    parser.add_argument("--session-file")
    parser.add_argument("--input-json", action="store_true", help="read one Coordinator request JSON object from stdin")
    parser.add_argument("--output-json", help="atomically write the latest revision-bound event JSON")
    args = parser.parse_args()
    if args.session_file and args.input_json:
        parser.error("--session-file and --input-json are mutually exclusive")
    # The console entry point is an explicit user choice.  This matters on
    # Windows, where a GUI has no DISPLAY/WAYLAND_DISPLAY environment.
    backend = backend_for_invocation(sys.argv[0])
    if os.environ.get("AWUI_BACKEND") in {"gui", "tui"}:
        backend = os.environ["AWUI_BACKEND"]
    if backend == "tui":
        from .live import main as tui_main
        argv = []
        if args.session_file:
            argv += ["--session-file", args.session_file]
        if args.input_json:
            argv += ["--input-json"]
        if args.output_json:
            argv += ["--output-json", args.output_json]
        return int(tui_main(argv))
    if args.session_file or args.input_json:
        from .awg import envelope_requests_to_tui
        from .gui import build_gui_application
        from .host import attach_session
        from .transport_io import read_json, write_json_file
        from .host import append_event
        request = attach_session(args.session_file) if args.session_file else read_json(sys.stdin)
        if request.get("kind") != "coordinator-tui-request":
            parser.error("input is not a coordinator-tui-request")
        _context, decisions = envelope_requests_to_tui(request, project_id=request["project_id"], session_id=request["session_id"], documents=request.get("documents"))
        sequence = 0
        event_log = args.output_json.with_suffix(".events.jsonl") if args.output_json else None
        def record_event(event: dict) -> None:
            nonlocal sequence
            sequence += 1
            payload = dict(event.get("payload") or {})
            payload.update({key: event[key] for key in ("point_id", "disposition", "selected", "user_proposal") if key in event})
            event = {**event, "payload": payload, "project_id": request["project_id"],
                     "ar_id": request.get("ar", {}).get("ar_id", ""),
                     "task_revision": request.get("ar", {}).get("task_revision", 0),
                     "session_id": request["session_id"], "sequence": sequence}
            if args.output_json:
                write_json_file(event, args.output_json)
            if event_log:
                append_event(event_log, event)
        window = build_gui_application(
            design_document=(request.get("documents") or {}).get("design", "# Design\n\nAwaiting context"),
            workplan=(request.get("documents") or {}).get("workplan", "# Work plan\n\nAwaiting context"),
            decisions=decisions,
            on_event=record_event,
        )
        return window.run()
    from .gui import main as gui_main
    return int(gui_main())


if __name__ == "__main__":
    raise SystemExit(main())
