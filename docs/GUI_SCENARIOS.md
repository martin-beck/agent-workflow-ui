# GUI scenario artifacts

The scenario workflow replays the same batched decision model used by the TUI
and captures a redacted Qt screenshot for every scenario. The complete set is
published as the `gui-scenario-screenshots` CI artifact (the legacy
`gui-batch-screenshot` remains as a smoke check). The GUI renders the Markdown design and work-plan documents in
separate scrollable panes, lists every decision and proposal, follows the
active decision highlight, and uses the same revision-bound event callbacks as
the terminal UI. The screenshot is generated offscreen, so CI does not need a
desktop session or user credentials.

The committed gallery is linked from [SCENARIOS.md](SCENARIOS.md); regenerate
it with `python tools/run_gui_scenarios.py` after changing GUI behavior.

The corpus also includes the post-release flows: `company-dashboard`,
`hierarchy-drill-down`, `board-directive-entry`, `pause-resume-session`, and
`rollback-conflict-display`. These use the same batch fixture and capture
pipeline as proposal decisions, so GUI behavior remains comparable across
dashboard, directive, resume, and rollback review sessions.
