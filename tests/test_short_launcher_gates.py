"""AR-0076 security and compatibility gates.

These tests intentionally exercise the public handoff builders rather than
private implementation details. Token/installer-specific tests are added by
the AR-0073--0075 implementations, while these gates remain valid for every
launcher release.
"""

from pathlib import Path

import pytest

from awtui.host import (
    posix_bootstrap_handoff_command,
    powershell_bootstrap_handoff_command,
)


ROOT = Path(__file__).parents[1]


@pytest.mark.parametrize("value", ["bad;host", "host && rm -rf /", "host\nnext"])
def test_bootstrap_handoff_rejects_shell_injection_in_host(value):
    with pytest.raises(ValueError):
        powershell_bootstrap_handoff_command(
            ssh_host=value,
            bootstrap_script="/srv/agent-workflow-ui/tools/awui-bootstrap.ps1",
            remote_session_file="/srv/state/request.json",
        )
    with pytest.raises(ValueError):
        posix_bootstrap_handoff_command(
            ssh_host=value,
            bootstrap_script="/srv/agent-workflow-ui/tools/awui-bootstrap.sh",
            remote_session_file="/srv/state/request.json",
        )


@pytest.mark.parametrize("path", ["/tmp/a\n.json"])
def test_bootstrap_handoff_rejects_non_absolute_or_unsafe_session_path(path):
    with pytest.raises(ValueError):
        powershell_bootstrap_handoff_command(
            ssh_host="ai-ws",
            bootstrap_script="/srv/agent-workflow-ui/tools/awui-bootstrap.ps1",
            remote_session_file=path,
        )


def test_bootstrap_scripts_are_present_and_documented():
    assert (ROOT / "tools/awui-bootstrap.ps1").is_file()
    assert (ROOT / "tools/awui-bootstrap.sh").is_file()
    docs = (ROOT / "docs/SHORT_LAUNCHER.md").read_text()
    for required in ("awui 8K4M", "awui ai-ws 8K4M", "GUI", "TUI", "expired", "replayed"):
        assert required in docs


def test_bootstrap_scripts_have_cleanup_and_probe_contracts():
    posix = (ROOT / "tools/awui-bootstrap.sh").read_text()
    powershell = (ROOT / "tools/awui-bootstrap.ps1").read_text()
    assert "mktemp" in posix and "trap" in posix
    assert "AWUI_PROBE_ONLY" in posix
    assert "Remove-Item" in powershell and "ProbeOnly" in powershell
    assert "OSArchitecture" in powershell


def test_short_command_does_not_claim_to_embed_private_paths_or_credentials():
    docs = (ROOT / "docs/SHORT_LAUNCHER.md").read_text()
    assert "no SSH credentials" in docs
    assert "private\npaths" in docs
    assert "complete batch" in docs
