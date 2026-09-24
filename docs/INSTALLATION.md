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

The installer supports both a temporary script file and the short inline
PowerShell form below. The inline form is safe because it still pins the
release and validates the launcher hash before writing files:

```powershell
$s = irm https://raw.githubusercontent.com/martin-beck/agent-workflow-ui/v0.6.0/tools/awui-install.ps1
& ([scriptblock]::Create($s)) -Action Install -SshHost ai-ws -RemoteStateRoot /srv/data/projects/awc-malloc-state
```

```powershell
$d = Join-Path $env:TEMP ("awui-install-" + [guid]::NewGuid().ToString('N') + '.ps1')
try {
  irm https://raw.githubusercontent.com/martin-beck/agent-workflow-ui/v0.6.0/tools/awui-install.ps1 -OutFile $d
  & $d -Action Install -SshHost ai-ws -RemoteStateRoot /srv/data/projects/awc-malloc-state
} finally { Remove-Item -Force $d -ErrorAction SilentlyContinue }

Configure the SSH alias and authoritative state root during installation (the
values are routing metadata only):

```powershell
& "$env:LOCALAPPDATA\AgentWorkflowUI\bin\awui-install.ps1" -Action Repair -SshHost ai-ws -RemoteStateRoot /srv/data/projects/awc-malloc-state
```
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
