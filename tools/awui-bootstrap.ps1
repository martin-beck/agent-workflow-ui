<#
.SYNOPSIS
  Bootstrap the Agent Workflow UI on a Windows controlling machine.

This file is intentionally small enough to fetch with `ssh host cat ...`.
It installs the pinned GUI-capable release into the user's Python environment,
invokes the module entry point (so PATH changes are not required), and leaves
the authoritative request/result files on the SSH host.
#>
[CmdletBinding()]
param(
    [string]$SshHost,
    [string]$SessionFile,
    [string]$RemoteEventFile,
    [ValidateSet('gui', 'tui')][string]$Backend = 'gui',
    [string]$Release = 'v0.4.13',
    [switch]$ProbeOnly
)

$facts = [ordered]@{
    platform = [System.Environment]::OSVersion.Platform.ToString()
    architecture = [System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture.ToString()
    runtime = ''
    distribution = 'Windows'
    shell = $PSVersionTable.PSEdition
    gui_available = $true
}
$python = Get-Command py -ErrorAction SilentlyContinue
if (-not $python) { $python = Get-Command python -ErrorAction SilentlyContinue }
if (-not $python) {
    throw 'Python 3.11+ is required on the controlling Windows machine.'
}

$facts.runtime = (& $python.Source --version 2>&1 | Out-String).Trim()
Write-Verbose (($facts | ConvertTo-Json -Compress))
if ($ProbeOnly) { $facts | ConvertTo-Json -Compress; exit 0 }
if (-not $SshHost -or -not $SessionFile -or -not $RemoteEventFile) {
    throw 'SshHost, SessionFile, and RemoteEventFile are required unless ProbeOnly is used.'
}

$runtimeRoot = Join-Path $env:TEMP ("awui-runtime-" + [guid]::NewGuid().ToString('N'))
$venvPython = Join-Path $runtimeRoot 'Scripts\python.exe'
New-Item -ItemType Directory -Path $runtimeRoot -Force | Out-Null
try {
    & $python.Source -m venv $runtimeRoot
    if ($LASTEXITCODE -ne 0) { throw 'Could not create a temporary Python runtime.' }
    $package = "agent-workflow-ui[gui] @ https://github.com/martin-beck/agent-workflow-ui/archive/refs/tags/$Release.zip"
    & $venvPython -m pip install --disable-pip-version-check --quiet $package
    if ($LASTEXITCODE -ne 0) {
        # A GUI wheel may not exist for every architecture; the same trusted
        # release still provides a complete terminal client.
        & $venvPython -m pip install --disable-pip-version-check --quiet "agent-workflow-ui @ https://github.com/martin-beck/agent-workflow-ui/archive/refs/tags/$Release.zip"
        if ($LASTEXITCODE -ne 0) { throw 'Could not install the pinned Agent Workflow UI runtime.' }
        $Backend = 'tui'
    }

    & $venvPython -m awtui.connect `
        --ssh-host $SshHost `
        --session-file $SessionFile `
        --remote-event-file $RemoteEventFile `
        --backend $Backend
    exit $LASTEXITCODE
}
finally {
    Remove-Item -Recurse -Force $runtimeRoot -ErrorAction SilentlyContinue
}
