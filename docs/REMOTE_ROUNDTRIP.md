# Remote SSH round-trip qualification

`tools/run_ssh_roundtrip.py` exercises the bounded request/response path against
an SSH endpoint. It creates a synthetic revision-bound Coordinator request,
copies it to the remote host, projects a selected TUI event into a Coordinator
response, copies that response back, and verifies the AR revision and resolved
disposition. The helper never prints packet contents or credentials.

The Linux scenario workflow starts an isolated, temporary `sshd` account and
runs this helper against loopback. The Windows compatibility workflow runs the
same fixture with a fake transport plus the PowerShell command/capability tests;
Windows CI does not assume that an SSH daemon is available. The native x64 job
runs `tools/qualify_windows.py --expected-architecture x64 --require-windows`,
which drives the actual PySide6 window and prompt-toolkit application through
resize, document switching, proposal editing, selection, save+exit, and event
journal checks. `platform.machine()` is the observed architecture; the expected
value is only an assertion. ARM64 is explicitly reported as a capability and
is unqualified unless an authorized native `[self-hosted, windows, ARM64]`
runner is enabled with the `AWUI_NATIVE_ARM64_RUNNER` repository variable.

For a manually prepared endpoint:

```text
python tools/run_ssh_roundtrip.py --host SSH_ALIAS --port 22 \
  --user REMOTE_USER --identity ~/.ssh/id_ed25519 \
  --remote-dir /tmp/awui-roundtrip
```

Use the user's existing SSH config and host key policy for real projects. The
fixture's `--insecure-host-key-check` option is only for disposable CI daemons.

## Self-bootstrapping clients

When the client has no installed runtime, the coordinator can print a command
that fetches the trusted script through the user's OpenSSH config alias,
prefers the GUI, and falls back to the TUI when no display or GUI extra is
available:

```powershell
$d="$env:TEMP\awui-$([guid]::NewGuid().ToString('N'))"; md $d | Out-Null
ssh project-prod "cat -- '/srv/ui/tools/awui-bootstrap.ps1'" > "$d\a.ps1"
powershell -ExecutionPolicy Bypass -File "$d\a.ps1" project-prod '/srv/state/request.json' '/srv/state/events.jsonl'
Remove-Item -Recurse -Force $d
```

The POSIX equivalent is:

```sh
d=$(mktemp -d); trap 'rm -rf "$d"' EXIT
ssh project-prod "cat -- '/srv/ui/tools/awui-bootstrap.sh'" >"$d/a"
sh "$d/a" project-prod '/srv/state/request.json' '/srv/state/events.jsonl'
```

Both scripts accept a pinned `AWUI_RUNTIME_ARCHIVE` and `--resume` (PowerShell
`-Resume`) for reconnecting to the same revision-bound request. An interrupted
UI publishes no remote result; rerunning with resume fetches the same request
and continues its journal. Event material is uploaded to a unique remote
sibling and atomically renamed into the authoritative path. Failed copies
remove that sibling, and local request/runtime directories are removed on every
exit. Paths and aliases are validated as single-line values, and request/event
contents are never printed by the connector.

The hosted Windows job proves native x64 capability, GUI/TUI selection, and
script probes. The Linux scenario job proves an actual ephemeral OpenSSH
request/response transfer. These are qualification boundaries; they do not
claim that an external user's SSH alias, host, display, or credentials were
consumed successfully.
