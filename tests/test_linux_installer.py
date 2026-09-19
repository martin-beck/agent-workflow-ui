from __future__ import annotations

import hashlib
import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_posix_installer_is_syntax_clean_and_has_reversible_actions():
    installer = ROOT / "tools/awui-install.sh"
    result = subprocess.run(["sh", "-n", str(installer)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    text = installer.read_text(encoding="utf-8")
    for marker in ("Install", "Repair", "Uninstall", "Version", "curl", "wget", "sha256sum", "shasum", "mktemp", "python3", "venv", "agent-workflow-ui[gui]"):
        assert marker in text
    assert "sudo" not in text.lower()


def test_posix_installer_pins_the_release_launcher_hash():
    installer = (ROOT / "tools/awui-install.sh").read_text(encoding="utf-8")
    launcher_hash = hashlib.sha256((ROOT / "tools/awui").read_bytes()).hexdigest()
    assert launcher_hash in installer
    assert "raw.githubusercontent.com/martin-beck/agent-workflow-ui" in installer


def test_posix_installed_launcher_has_short_maintenance_commands(tmp_path):
    root = tmp_path / "install"
    env = {**os.environ, "AWUI_INSTALL_ROOT": str(root)}
    result = subprocess.run(
        ["sh", str(ROOT / "tools/awui-install.sh"), "--action", "version"],
        env=env, capture_output=True, text=True, check=True,
    )
    assert result.stdout.strip() == "awui is not installed."
    text = (ROOT / "tools/awui").read_text(encoding="utf-8")
    assert "--version" in text and "--repair" in text and "--uninstall" in text
    assert "awtui.shortcut" in text


def test_posix_installer_rejects_unsafe_routing_values(tmp_path):
    env = {**os.environ, "AWUI_INSTALL_ROOT": str(tmp_path / "install")}
    for option, value in (("--ssh-host", "bad;host"), ("--remote-state-root", "/state/../secret")):
        result = subprocess.run(
            ["sh", str(ROOT / "tools/awui-install.sh"), "--action", "repair", option, value],
            env=env, capture_output=True, text=True,
        )
        assert result.returncode != 0


def test_posix_installer_rejects_broad_destructive_install_roots():
    result = subprocess.run(
        ["sh", str(ROOT / "tools/awui-install.sh"), "--action", "uninstall", "--install-root", "/"],
        capture_output=True, text=True,
    )
    assert result.returncode != 0
