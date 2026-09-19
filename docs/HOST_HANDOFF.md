# Human decision handoff

When the autonomous worker has exhausted independent work, Coordinator creates
a revision-bound decision batch and a private session request. The worker must
show the user the batch summary and one of these launch paths:

* **Inline/TTY:** use the current user-controlled terminal.
* **tmux:** open a new window only when the host explicitly opted into tmux.
* **SSH or headless:** print a copyable command; the remote process must not
  try to open a terminal on the user's computer.

The manual fallback is deliberately explicit:

```text
HUMAN DECISION REQUIRED
Run in a user-controlled terminal:
  awui-live --session-file /protected/path/awui-SESSION.json
```

The request file is private (`0600`), bounded, and contains the AR id,
revision, request reference, decision packet, and Markdown design/work-plan
documents. It must not contain credentials, raw host prompts, or private
transcripts. Start `awui-live --session-file` to select the Qt GUI whenever
`DISPLAY`/`WAYLAND_DISPLAY` is available (including SSH X forwarding). In a
headless environment it automatically runs the full TUI; `awtui-live` remains
the explicit terminal-only command.

Submitting a choice produces revision-bound TUI events in the private sibling
`*.events.jsonl` journal. The Coordinator/agent host consumes that journal and
remains the only component allowed to persist the AR outcome. If the terminal
disconnects, the user reruns the same attach command; stale revisions are
rejected rather than silently applied. A clarification or incomplete batch
leaves the worker waiting, while accepted independent points can be resumed
individually.

## Windows PowerShell through SSH

SSH does not identify the operating system of the client. The Coordinator
therefore carries explicit `client_capabilities` (`platform: windows`,
`shell: powershell`, and optional `gui_available`) and an `ssh_host` alias from
the user's host adapter. For that capability set, `handoff_message(...,
remote=...)` prints one copyable PowerShell `awui-connect` command that reads the
private batch JSON with `ssh`, opens the local `awui-live` GUI when
`gui_available` is true (otherwise `awtui-live`), copies the revision-bound
event JSON back with `scp`, and removes local temporary files. A missing `gui_available` preserves the
GUI-preferred default for backwards-compatible clients.

The same short command works from Linux and macOS. It detects the local display
and architecture, supports `--backend tui` for an explicit terminal fallback,
and uses a temporary runtime directory for the request and response. See
[`GUI_UX.md`](GUI_UX.md) for the complete handoff and reconciliation contract.

If the controlling machine does not have the connector installed, the request's
optional `host_handoff.bootstrap_script` points at a trusted absolute script on
the authoritative host. The printed command fetches that script with the SSH
config alias, detects local platform/architecture/distribution/runtime, creates
a temporary virtual environment, installs the pinned release, prefers Qt GUI
when usable, falls back to TUI when the GUI wheel or display is unavailable,
uploads the event journal, and removes the temporary launcher/runtime.

The alias is passed unchanged to OpenSSH, so the user's existing SSH config,
ProxyJump, port, and identity settings are used. The remote event path is
explicit and is never guessed from a local path.

The reproducible transport qualification is documented in
[`REMOTE_ROUNDTRIP.md`](REMOTE_ROUNDTRIP.md); it covers the actual SSH copy and
Coordinator response projection without claiming an external user's machine.
