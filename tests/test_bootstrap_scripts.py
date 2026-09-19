from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_windows_bootstrap_negotiates_environment_uses_temp_runtime_and_cleans_up():
    text = (ROOT / "tools/awui-bootstrap.ps1").read_text(encoding="utf-8")
    assert "Positional invocation" in text
    for marker in ("OSArchitecture", "OSVersion", "PSEdition", "-m venv", "RuntimeInformation", "Remove-Item -Recurse -Force", "--backend $Backend"):
        assert marker in text
    assert "agent-workflow-ui[gui]" in text
    assert "agent-workflow-ui @ https" in text


def test_posix_bootstrap_negotiates_architecture_distribution_display_and_cleanup():
    text = (ROOT / "tools/awui-bootstrap.sh").read_text(encoding="utf-8")
    assert "usage: awui-bootstrap.sh <ssh-host> <session-file>" in text
    for marker in ("uname -m", "uname -s", "/etc/os-release", "DISPLAY", "WAYLAND_DISPLAY", "mktemp", "trap 'rm -rf"):
        assert marker in text
    assert "agent-workflow-ui[gui]" in text
    assert "AWUI_BACKEND=tui" in text
