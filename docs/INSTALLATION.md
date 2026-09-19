# Installation and live use

Requires Python 3.11 or newer. Install the pinned runtime and launch the
full-screen application:

```text
python3 -m pip install .
tools/awtui-live
```

The footer exposes keyboard controls for selection, rejection, clarification,
more evidence, proposal addition, safe exit, and targeted reopen. The public
UI accepts only revision-bound AR context and emits typed events; credentials,
private prompts, raw transcripts, host paths, and unbounded logs are not part
of the application contract.

For deterministic qualification, run `python3 -m pytest -q` from the checkout.

## One-time Windows launcher

The compact decision command is `awui TOKEN` (or `awui HOST TOKEN`). Install
the per-user launcher once from a trusted checkout or release tag; no
administrator rights are required:

```powershell
irm https://raw.githubusercontent.com/martin-beck/agent-workflow-ui/v0.4.14/tools/awui-install.ps1 | iex
```

The installer creates `%LOCALAPPDATA%\AgentWorkflowUI\config.json`, adds its
`bin` directory to the user's PATH, and installs the pinned GUI-capable
runtime. The configuration contains only `schema_version`, `ssh_host`,
`remote_state_root`, `release`, `runtime_root`, and `launcher_version`; SSH
keys and other credentials remain under the user's normal OpenSSH
configuration. Pass `-SshHost` and `-RemoteStateRoot` to the script when
installing defaults, or set them later through the token workflow.

Repair, inspect, and remove it with:

```powershell
& "$env:LOCALAPPDATA\AgentWorkflowUI\bin\awui-install.ps1" -Action Repair
awui-install.ps1 -Action Version
awui-install.ps1 -Action Uninstall
```

The installer verifies the release launcher hash before writing it and uses
the user's SSH config alias unchanged. A new PowerShell process is needed to
pick up the persistent PATH change.
