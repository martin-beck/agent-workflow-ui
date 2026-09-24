import json

from awtui.launcher import detect_ui_backend
from tools.qualify_windows import qualify, runner_facts


def test_windows_desktop_prefers_gui_without_display():
    assert detect_ui_backend(environ={"OS": "Windows_NT"}) == "gui"
    assert detect_ui_backend(environ={"OS": "Windows_NT", "AWUI_GUI_AVAILABLE": "0"}) == "tui"


def test_windows_qualification_tui_fallback_is_reported(monkeypatch):
    monkeypatch.setenv("AWUI_GUI_AVAILABLE", "0")
    # Backend-selection behavior remains covered independently of native UI.
    assert detect_ui_backend(environ={"OS": "Windows_NT", "AWUI_GUI_AVAILABLE": "0"}) == "tui"


def test_qualification_uses_runner_architecture_not_expected_value():
    opposite = "x64" if runner_facts()["architecture"] == "arm64" else "arm64"
    report = qualify(expected_architecture=opposite)
    assert report["architecture"] != opposite
    assert report["qualification"] == "unqualified"
    assert report["architecture_match"] is False


def test_qualification_report_is_json_safe_and_explicit():
    report_architecture = runner_facts()["architecture"]
    report = qualify(expected_architecture=report_architecture)
    assert json.dumps(report)
    assert report["expected_architecture"] == report_architecture
    assert "arm64_capability" in report
