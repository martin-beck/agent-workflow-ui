from awtui.host import detect_ui_backend, launch_argv
from awtui.launcher import backend_for_invocation


def test_x_forwarded_ssh_prefers_gui() -> None:
    env = {"SSH_CONNECTION": "client", "DISPLAY": "localhost:10.0"}
    assert detect_ui_backend(environ=env) == "gui"
    assert launch_argv("manual", "/tmp/session.json") is None


def test_headless_environment_uses_tui() -> None:
    assert detect_ui_backend(environ={}) == "tui"


def test_explicit_gui_entrypoint_wins_without_display() -> None:
    assert backend_for_invocation("C:/Python/Scripts/awui-live.exe", environ={}) == "gui"


def test_explicit_backend_survives_module_fallback_without_display() -> None:
    assert detect_ui_backend(environ={"AWUI_BACKEND": "gui"}) == "gui"
    assert backend_for_invocation("awtui-live", environ={}) == "tui"
