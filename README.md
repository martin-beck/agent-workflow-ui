# Agent Workflow UI

Release line: **v0.6.0** (dashboard, bounded hierarchy navigation, directive
entry, paused-session resume, rollback/conflict display, and refreshed scenario
artifacts).

Agent Workflow UI is the interactive Linux desktop and terminal application
for human-oracle discussion, decision selection, and post-discussion conflict
reconciliation. `awui-live` selects the premium Qt desktop renderer whenever a
local or X-forwarded display is available and falls back to the full
prompt-toolkit TUI in headless/SSH environments. `awtui-live` remains
available as an explicit TUI compatibility command.
It is a downstream client: Agent Workflow Guidance owns decision semantics,
Agent Workflow Coordinator owns AR identity/revisions/events, and Agent
Workflow Quality owns quality and evidence policy.

The application is developed through the public coordination state repository
`martin-beck/agent-workflow-ui-state` and routed by the Agent Workflow
umbrella project. It must never silently mutate an AR: every session starts
from an immutable AR/revision envelope and emits typed, revision-bound output.

The live renderer supports revision-bound batches of independent decisions in
one session. It renders Coordinator-generated Design and Work plan Markdown,
keeps each decision's source phrase highlighted while switching or scrolling,
reflows to three stacked panes on narrow terminals, and offers proposal editing
and Save + exit for a complete unsaved batch.

## Interaction boundary

The TUI consumes an `ar_context` containing project, AR, revision, dependency,
decision packet, formal-check, and quality-evidence references. It emits
`tui_event` records for acknowledgement, clarification, candidate selection,
user-authored alternatives, conflict dispositions, safe exit, and completion.
Coordinator accepts only events matching the active AR revision; stale,
cross-AR, skipped-gate, or incomplete events fail closed.

See [`docs/AR_TUI_INTERACTION.md`](docs/AR_TUI_INTERACTION.md) and the formal
state model in [`specifications/tui-lifecycle.json`](specifications/tui-lifecycle.json).

For a Coordinator-created human handoff, run the private session request with
`awtui-live --session-file PATH`. See
[`docs/HOST_HANDOFF.md`](docs/HOST_HANDOFF.md) for local, tmux, SSH, resume,
and privacy behavior.
