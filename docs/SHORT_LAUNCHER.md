# Short decision launcher

After the one-time installation, a pending decision batch is started from the
user's own machine with a short, revision-bound token:

```powershell
awui 8K4M
```

The optional host override is useful when a user has more than one configured
Agent Workflow host:

```powershell
awui ai-ws 8K4M
```

The token is an opaque lookup key. It contains no SSH credentials, private
paths, prompts, or decision contents. The Coordinator resolves it to exactly
one project, complete batch, task revision, and event destination. Resolution
is rejected when the token is unknown, expired, already consumed, from another
project/revision, or otherwise malformed. A token is consumed only after a
validated final response has been written to the authoritative event journal;
closing the UI before commitment leaves the token available for recovery.

## One-time installation

Installation is per-user and does not require administrator rights. The
installer validates the signed release/hash before placing the small launcher
in the user's PATH and writes only non-secret configuration. The exact command
is supplied by the Coordinator for the selected release. The launcher supports
these maintenance operations:

```text
awui-install.ps1 -Action Version
awui-install.ps1 -Action Repair
awui-install.ps1 -Action Uninstall

The `awui --version`, `awui --repair`, and `awui --uninstall` aliases are also
accepted by the installed launcher.
```

On Linux and other POSIX systems, the equivalent no-admin one-time install is:

```sh
curl -fsSL https://raw.githubusercontent.com/martin-beck/agent-workflow-ui/v0.5.1/tools/awui-install.sh | sh -s -- \
  --ssh-host ai-ws --remote-state-root /srv/data/projects/awc-malloc-state
```

`wget` can be used when `curl` is unavailable:

```sh
wget -qO- https://raw.githubusercontent.com/martin-beck/agent-workflow-ui/v0.5.1/tools/awui-install.sh | sh -s -- \
  --ssh-host ai-ws --remote-state-root /srv/data/projects/awc-malloc-state
```

The POSIX installer writes `~/.local/share/agent-workflow-ui`, links `awui`
into `~/.local/bin`, validates the launcher SHA-256 for the selected release,
creates a per-user Python virtual environment, and installs the GUI extra.
Use `awui --repair`, `awui --version`, or `awui --uninstall` for maintenance.

The install directory and cache are temporary-runtime inputs, not authority:
SSH host aliases, ProxyJump, identity, and port are always resolved by the
user's existing OpenSSH configuration.

## Runtime and transport

`awui` detects the local OS, architecture, distribution/runtime, display
availability, and shell. It opens the Qt GUI when a usable display and GUI
runtime are available, otherwise it starts the complete TUI. Both paths show
the entire batch in one session and use the same revision-bound bridge. The
validated event journal is written back to the authoritative host; local
temporary launchers, runtimes, and copied request data are removed on normal
and interrupted exit.

The long self-bootstrap command remains available when the launcher is not yet
installed. It is the recovery path, not the normal user workflow:

```text
PowerShell: fetch awui-bootstrap.ps1 over SSH, invoke it with the session, and remove it
POSIX:      fetch awui-bootstrap.sh over SSH, invoke it with the session, and remove it
```

The scripts must continue to reject unsafe host/script/path values and must
never interpolate user-controlled values into a shell command without
validation.

## Failure and recovery

| Condition | User-visible result | Authority effect |
| --- | --- | --- |
| Unknown/expired/replayed token | Clear error; no UI session | No event is accepted |
| Wrong project or revision | Clear stale-session error | No event is accepted |
| GUI unavailable | Full TUI fallback | Same bridge and journal |
| Interrupted UI | Safe retry with same token | No partial final commitment |
| Partial batch | Resume/reopen prompt | Only validated selected points persist |
| Completed batch | Success summary | Token becomes unusable |

The coordinator must batch independent points before issuing the token. A
separate token or UI process must not be created for each decision in one
batch.
