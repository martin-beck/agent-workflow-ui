<#
.SYNOPSIS
  Disposable Windows smoke harness for the exact inline installer invocation.

Run from the repository checkout.  The harness uses an isolated LOCALAPPDATA
and a local installer copy, so it never mutates the user's normal installation.
#>
[CmdletBinding()]
param([string]$Installer = (Join-Path $PSScriptRoot '..\tools\awui-install.ps1'))
$ErrorActionPreference = 'Stop'
$root = Join-Path ([IO.Path]::GetTempPath()) ('awui-inline-' + [guid]::NewGuid().ToString('N'))
$env:LOCALAPPDATA = Join-Path $root 'LocalAppData'
New-Item -ItemType Directory -Path $env:LOCALAPPDATA -Force | Out-Null
try {
    # ScriptBlock::Create intentionally gives the evaluated script no
    # $PSScriptRoot/$PSCommandPath. This is the regression shape from AR-0083.
    $source = Get-Content -Raw -LiteralPath $Installer
    $script = [scriptblock]::Create($source)
    & $script -Action Install -InstallRoot (Join-Path $env:LOCALAPPDATA 'AgentWorkflowUI')
    & $script -Action Repair -InstallRoot (Join-Path $env:LOCALAPPDATA 'AgentWorkflowUI')
    & $script -Action Version -InstallRoot (Join-Path $env:LOCALAPPDATA 'AgentWorkflowUI')
    & $script -Action Uninstall -InstallRoot (Join-Path $env:LOCALAPPDATA 'AgentWorkflowUI')
    if (Test-Path (Join-Path $env:LOCALAPPDATA 'AgentWorkflowUI')) {
        throw 'inline bootstrap cleanup left the isolated installation behind'
    }
} finally {
    if (Test-Path $root) { Remove-Item -LiteralPath $root -Recurse -Force }
}
