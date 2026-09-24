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
