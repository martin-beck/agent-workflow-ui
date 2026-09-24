# Remote SSH round-trip qualification

`tools/run_ssh_roundtrip.py` exercises the bounded request/response path against
an SSH endpoint. It creates a synthetic revision-bound Coordinator request,
copies it to the remote host, projects a selected TUI event into a Coordinator
response, copies that response back, and verifies the AR revision and resolved
disposition. The helper never prints packet contents or credentials.

The Linux scenario workflow starts an isolated, temporary `sshd` account and
runs this helper against loopback. The Windows compatibility workflow runs the
same fixture with a fake transport plus the PowerShell command/capability tests;
Windows CI does not assume that an SSH daemon is available. The Windows job
also runs `tools/qualify_windows.py` for `amd64` and `arm64` architecture
contract rows. It records only redacted facts: observed and expected
architecture, GUI/TUI selection, preservation of the OpenSSH alias,
batch/journal return, single-use-token status, and temporary cleanup. The
ARM64 row is portable contract coverage on hosted CI; native ARM64
qualification uses the same command on an ARM64 self-hosted runner.

For a manually prepared endpoint:

```text
python tools/run_ssh_roundtrip.py --host SSH_ALIAS --port 22 \
  --user REMOTE_USER --identity ~/.ssh/id_ed25519 \
  --remote-dir /tmp/awui-roundtrip
```

Use the user's existing SSH config and host key policy for real projects. The
fixture's `--insecure-host-key-check` option is only for disposable CI daemons.
