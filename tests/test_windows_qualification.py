import json

from awtui.connect import environment_fingerprint
from awtui.launcher import detect_ui_backend
from tools.qualify_windows import qualify


def test_windows_desktop_prefers_gui_without_display():
    assert detect_ui_backend(environ={"OS": "Windows_NT"}) == "gui"
    assert detect_ui_backend(environ={"OS": "Windows_NT", "AWUI_GUI_AVAILABLE": "0"}) == "tui"


def test_windows_qualification_reports_batch_alias_return_and_cleanup(monkeypatch):
    monkeypatch.setenv("AWUI_GUI_AVAILABLE", "1")
    report = qualify(expected_architecture="arm64")
    assert report["backend"] == "gui"
    assert report["expected_architecture"] == "arm64"
    assert report["batch_mode"] is True
    assert report["returned_event_journal"] is True
    assert report["single_use_token"] is True
    assert report["temporary_cleanup"] is True
    assert report["command_has_config_alias"] is True
    assert report["command_has_cleanup"] is True


def test_windows_qualification_tui_fallback_is_reported(monkeypatch):
    monkeypatch.setenv("AWUI_GUI_AVAILABLE", "0")
    assert qualify()["backend"] == "tui"


def test_qualification_output_is_json_safe_and_observed_architecture_is_real():
    output = qualify()
    assert json.dumps(output)
    assert output["architecture"] == environment_fingerprint()["architecture"]
