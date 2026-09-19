<#
.SYNOPSIS
  Installed, short Agent Workflow UI launcher.

This file is copied to the per-user installation directory by
awui-install.ps1.  It deliberately delegates token resolution to the pinned
Python package; no SSH credentials or decision data are stored in this file.
#>
[CmdletBinding()]
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Arguments
)

$installRoot = Split-Path -Parent $PSScriptRoot
$config = Join-Path $installRoot 'config.json'
$python = Join-Path $installRoot 'runtime\Scripts\python.exe'
$maintenance = @{ '--version' = 'Version'; '--repair' = 'Repair'; '--uninstall' = 'Uninstall' }
if ($Arguments.Count -gt 0 -and $maintenance.ContainsKey($Arguments[0])) {
    $installer = Join-Path $PSScriptRoot 'awui-install.ps1'
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $installer -Action $maintenance[$Arguments[0]]
    exit $LASTEXITCODE
}
if (-not (Test-Path -LiteralPath $python)) {
    throw "Agent Workflow UI runtime is missing. Run awui-install.ps1 -Action Repair."
}
& $python -m awtui.shortcut --config $config @Arguments
exit $LASTEXITCODE
