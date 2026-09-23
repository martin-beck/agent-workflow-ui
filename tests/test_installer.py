from hashlib import sha256
from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_installer_supports_reversible_user_actions_and_short_entrypoint():
    text = (ROOT / "tools/awui-install.ps1").read_text(encoding="utf-8")
    for marker in ("Install", "Repair", "Uninstall", "Version", "LOCALAPPDATA", "SetEnvironmentVariable('Path',", "awui.ps1", "awui.cmd"):
        assert marker in text
    assert "SetAccessRuleProtection($true, $false)" in text
    assert "Administrator" not in text


def test_installer_configuration_is_non_secret_and_has_token_routing_fields():
    text = (ROOT / "tools/awui-install.ps1").read_text(encoding="utf-8")
    for marker in ("schema_version", "ssh_host", "remote_state_root", "release", "runtime_root", "launcher_version"):
        assert marker in text
    assert "password" not in text.lower()
    assert "private_key" not in text.lower()


def test_installer_validates_alias_remote_root_release_and_launcher_hash():
    text = (ROOT / "tools/awui-install.ps1").read_text(encoding="utf-8")
    assert "Assert-SafeAlias" in text
    assert "Assert-AbsoluteRemoteRoot" in text
    assert "ValidatePattern('^v[0-9]+\\.[0-9]+\\.[0-9]+$')" in text
    launcher_hash = sha256((ROOT / "tools/awui.ps1").read_bytes()).hexdigest()
    assert launcher_hash in text
    assert "Invoke-WebRequest" in text
    assert "raw.githubusercontent.com/martin-beck/agent-workflow-ui" in text


def test_installed_launcher_delegates_to_pinned_shortcut_with_config():
    text = (ROOT / "tools/awui.ps1").read_text(encoding="utf-8")
    assert "runtime\\Scripts\\python.exe" in text
    assert "awtui.shortcut" in text
    assert "--config $config" in text
    assert "ValueFromRemainingArguments" in text


def test_inline_scriptblock_never_uses_empty_script_paths():
    """The documented irm/ScriptBlock::Create shape has no script path."""
    text = (ROOT / "tools/awui-install.ps1").read_text(encoding="utf-8")
    assert "$source = if ($PSScriptRoot)" in text
    assert "if ($source -and (Test-Path -LiteralPath $source))" in text
    assert "if ($PSCommandPath -and (Test-Path -LiteralPath $PSCommandPath))" in text
    assert "Join-Path $PSScriptRoot" not in text.split("$source = if", 1)[0]


def test_inline_bootstrap_harness_covers_install_repair_and_cleanup():
    harness = (ROOT / "tests/powershell_inline_bootstrap.ps1").read_text(encoding="utf-8")
    for marker in (
        "ScriptBlock::Create",
        "-Action Install",
        "-Action Repair",
        "-Action Version",
        "-Action Uninstall",
        "PSScriptRoot",
    ):
        assert marker in harness
