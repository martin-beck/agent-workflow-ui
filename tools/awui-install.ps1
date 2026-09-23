<#
.SYNOPSIS
  Install or repair the per-user ``awui`` decision launcher on Windows.

The installer requires no administrator privileges.  It writes only below
LOCALAPPDATA and adds that user's AgentWorkflowUI\bin directory to the user
PATH.  Configuration is deliberately limited to non-secret routing data.
#>
[CmdletBinding()]
param(
    [ValidateSet('Install', 'Repair', 'Uninstall', 'Version')]
    [string]$Action = 'Install',
    [string]$SshHost = '',
    [string]$RemoteStateRoot = '',
    [ValidatePattern('^v[0-9]+\.[0-9]+\.[0-9]+$')]
    [string]$Release = 'v0.5.2',
    [switch]$Force,
    [string]$InstallRoot = ''
)

$ErrorActionPreference = 'Stop'
$defaultRoot = Join-Path ([Environment]::GetFolderPath('LocalApplicationData')) 'AgentWorkflowUI'
if (-not $InstallRoot) { $InstallRoot = $defaultRoot }
$bin = Join-Path $InstallRoot 'bin'
$runtime = Join-Path $InstallRoot 'runtime'
$configPath = Join-Path $InstallRoot 'config.json'
$launcherPath = Join-Path $bin 'awui.ps1'
$cmdPath = Join-Path $bin 'awui.cmd'
$installerPath = Join-Path $bin 'awui-install.ps1'

function Assert-SafeAlias([string]$Value) {
    if ($Value -and $Value -notmatch '^[A-Za-z0-9][A-Za-z0-9_.-]{0,62}$') {
        throw 'SshHost must be an SSH config alias (letters, digits, dot, underscore, hyphen).'
    }
}
function Assert-AbsoluteRemoteRoot([string]$Value) {
    if ($Value -and ($Value -notmatch '^/[A-Za-z0-9._/@+-]+$' -or $Value.Contains('..'))) {
        throw 'RemoteStateRoot must be an absolute remote path without traversal.'
    }
}
function Set-PrivateFile([string]$Path, [string]$Contents) {
    [System.IO.File]::WriteAllText($Path, $Contents, [System.Text.UTF8Encoding]::new($false))
    $acl = Get-Acl -LiteralPath $Path
    $acl.SetAccessRuleProtection($true, $false)
    $identity = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
    $rule = [System.Security.AccessControl.FileSystemAccessRule]::new($identity, 'FullControl', 'Allow')
    $acl.SetAccessRule($rule)
    Set-Acl -LiteralPath $Path -AclObject $acl
}
function Add-UserPath([string]$Directory) {
    $old = [Environment]::GetEnvironmentVariable('Path', 'User')
    $parts = @($old -split ';' | Where-Object { $_ })
    if ($parts -notcontains $Directory) {
        [Environment]::SetEnvironmentVariable('Path', (($parts + $Directory) -join ';'), 'User')
    }
    if (($env:Path -split ';') -notcontains $Directory) { $env:Path = "$Directory;$env:Path" }
}
function Remove-UserPath([string]$Directory) {
    $old = [Environment]::GetEnvironmentVariable('Path', 'User')
    [Environment]::SetEnvironmentVariable('Path', (($old -split ';' | Where-Object { $_ -and $_ -ne $Directory }) -join ';'), 'User')
}
function Install-Files {
    Assert-SafeAlias $SshHost
    Assert-AbsoluteRemoteRoot $RemoteStateRoot
    if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
        throw 'Python launcher ``py`` is required. Install Python 3.11+ and retry.'
    }
    New-Item -ItemType Directory -Path $bin -Force | Out-Null
    # `$PSScriptRoot` is empty when this file is evaluated via irm/iex or
    # ScriptBlock::Create. Do not pass an empty path to Join-Path/Test-Path.
    $source = if ($PSScriptRoot) { Join-Path $PSScriptRoot 'awui.ps1' } else { $null }
    $cmdSource = if ($PSScriptRoot) { Join-Path $PSScriptRoot 'awui.cmd' } else { $null }
    if ($source -and (Test-Path -LiteralPath $source)) {
        $launcherText = Get-Content -Raw -LiteralPath $source
    } else {
        # The normal one-time command downloads only this installer. Fetch the
        # matching launcher from the same immutable release and verify it
        # before it is written to the user's PATH.
        $url = "https://raw.githubusercontent.com/martin-beck/agent-workflow-ui/$Release/tools/awui.ps1"
        $launcherText = (Invoke-WebRequest -UseBasicParsing -Uri $url).Content
    }
    $expected = 'd2031e2cf35a795a4badc820619620fa53ee969e7283074f30db1293dfbbaf7d'
    $actual = [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData([Text.Encoding]::UTF8.GetBytes($launcherText))).ToLowerInvariant()
    if ($actual -ne $expected) {
        throw 'Launcher hash validation failed; refusing installation.'
    }
    Set-PrivateFile $launcherPath $launcherText
    Set-PrivateFile $cmdPath "@echo off`r`nsetlocal`r`npowershell.exe -NoProfile -ExecutionPolicy Bypass -File `"%~dp0awui.ps1`" %*`r`nexit /b %ERRORLEVEL%`r`n"
    if ($PSCommandPath -and (Test-Path -LiteralPath $PSCommandPath)) {
        Copy-Item -LiteralPath $PSCommandPath -Destination $installerPath -Force
    } else {
        # ``irm ... | iex`` has no script path. Preserve a repair/uninstall
        # entry point by fetching the same release's installer beside awui.
        $installerUrl = "https://raw.githubusercontent.com/martin-beck/agent-workflow-ui/$Release/tools/awui-install.ps1"
        $installerText = (Invoke-WebRequest -UseBasicParsing -Uri $installerUrl).Content
        Set-PrivateFile $installerPath $installerText
    }
    if (-not (Test-Path -LiteralPath $runtime)) {
        & py -3 -m venv $runtime
        if ($LASTEXITCODE) { throw 'Could not create the per-user Python runtime.' }
    }
    $package = "agent-workflow-ui[gui] @ https://github.com/martin-beck/agent-workflow-ui/archive/refs/tags/$Release.zip"
    & (Join-Path $runtime 'Scripts\python.exe') -m pip install --disable-pip-version-check --quiet --upgrade $package
    if ($LASTEXITCODE) { throw "Could not install pinned Agent Workflow UI release $Release." }
    $existing = if (Test-Path -LiteralPath $configPath) { Get-Content -Raw -LiteralPath $configPath | ConvertFrom-Json } else { $null }
    $config = [ordered]@{
        schema_version = '1'
        ssh_host = if ($SshHost) { $SshHost } elseif ($existing) { $existing.ssh_host } else { '' }
        remote_state_root = if ($RemoteStateRoot) { $RemoteStateRoot } elseif ($existing) { $existing.remote_state_root } else { '' }
        release = $Release
        runtime_root = $runtime
        launcher_version = '1'
    }
    Set-PrivateFile $configPath (($config | ConvertTo-Json -Depth 3) + "`n")
    Add-UserPath $bin
    Write-Output "awui installed in $InstallRoot (restart PowerShell, or use the current session PATH)."
}

switch ($Action) {
    'Version' {
        if (Test-Path -LiteralPath $configPath) { Get-Content -Raw -LiteralPath $configPath } else { Write-Output 'awui is not installed.' }
    }
    'Uninstall' {
        Remove-UserPath $bin
        if (Test-Path -LiteralPath $InstallRoot) { Remove-Item -LiteralPath $InstallRoot -Recurse -Force }
        Write-Output 'awui removed from this user profile.'
    }
    'Install' { if ((Test-Path -LiteralPath $InstallRoot) -and -not $Force) { throw 'awui is already installed; use -Action Repair or -Force.' }; Install-Files }
    'Repair' { Install-Files }
}
