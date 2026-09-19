import os

import pytest

from awtui.host import (
    attach_session,
    append_event,
    detect_launch_mode,
    handoff_message,
    launch_argv,
    write_session_file,
    client_capabilities,
    powershell_ssh_handoff_command,
    powershell_bootstrap_handoff_command,
    posix_bootstrap_handoff_command,
)


def request():
    return {"schema_version": "1.0", "kind": "coordinator-tui-request", "project_id": "demo",
            "session_id": "s-1", "ar": {"ar_id": "AR-0005", "task_revision": 3, "status": "open",
            "description": "d", "specification": {}}, "interaction": {"interaction_required": True,
            "decision_request_ref": "AWG-1", "decision_status": "pending", "trigger": "decision"},
            "guidance_request": {"schema_version": "0.2", "request_id": "AWG-1", "context": {},
            "formal_check": {}, "candidates": []}}


def test_mode_detection_is_deterministic_and_bounded():
    assert detect_launch_mode(environ={"TMUX": "1"}, stdin_tty=False, stdout_tty=False) == "tmux"
    assert detect_launch_mode(environ={}, stdin_tty=True, stdout_tty=True) == "tty"
    assert detect_launch_mode(environ={"AWTUI_LAUNCH_MODE": "inline"}, stdin_tty=False, stdout_tty=False) == "inline"
    assert detect_launch_mode(environ={}, stdin_tty=False, stdout_tty=False) == "manual"
    assert launch_argv("manual", "/tmp/x") is None
    assert launch_argv("tmux", "/tmp/x")[:2] == ["tmux", "new-window"]
    assert "HUMAN DECISION REQUIRED" in handoff_message("manual", "/tmp/x", summary="2 decisions")
    assert "awtui-live --session-file /tmp/x" in handoff_message(
        "manual", "/tmp/x", summary="2 decisions"
    )


def test_windows_client_capabilities_are_explicit_not_inferred_from_ssh():
    assert client_capabilities(environ={"AWUI_CLIENT_PLATFORM": "windows", "AWUI_CLIENT_SHELL": "powershell"}) == {
        "platform": "windows", "shell": "powershell", "ssh_config": "default", "gui_available": True
    }


def test_capabilities_normalize_platform_and_shell_for_bridge_schema():
    assert client_capabilities(environ={"AWUI_CLIENT_PLATFORM": "darwin", "AWUI_CLIENT_SHELL": "/bin/zsh"}) == {
        "platform": "macos", "shell": "zsh", "ssh_config": "default", "gui_available": False
    }


def test_windows_remote_handoff_falls_back_to_tui_without_gui_capability():
    message = handoff_message(
        "manual", "/remote/request.json", summary="2 decisions",
        remote={"ssh_host": "build-box", "session_file": "/remote/request.json",
                "event_file": "/remote/events.json", "client_capabilities":
                {"platform": "windows", "shell": "powershell", "gui_available": False}},
    )
    assert "awui-connect" in message
    assert "--backend tui" in message


def test_powershell_ssh_round_trip_uses_config_alias_and_remote_result():
    command = powershell_ssh_handoff_command(
        ssh_host="project-prod",
        remote_session_file="/srv/state/.runtime/request.json",
        remote_event_file="/srv/state/.runtime/response.json",
    )
    assert "ssh project-prod" in command
    assert "awui-live --session-file" in command
    assert "scp \"$env:TEMP\\awui-events.json\" project-prod:'/srv/state/.runtime/response.json'" in command
    with pytest.raises(ValueError):
        powershell_ssh_handoff_command(ssh_host="bad;host", remote_session_file="/tmp/x")


def test_powershell_bootstrap_fetches_remote_script_and_cleans_up():
    command = powershell_bootstrap_handoff_command(
        ssh_host="ai-ws", bootstrap_script="/srv/data/projects/agent-workflow-tui/tools/awui-bootstrap.ps1",
        remote_session_file="/srv/state/request.json", remote_event_file="/srv/state/events.jsonl",
    )
    assert "ssh ai-ws" in command
    assert "awui-bootstrap" in command
    assert "-ep Bypass" in command
    assert "'ai-ws' '/srv/state/request.json'" in command
    assert "ri $d -r -fo -ea 0" in command
    assert command.count("[guid]::NewGuid()") == 1
    assert "-f \"$d\\a.ps1\"" in command


def test_powershell_bootstrap_rejects_unsafe_script_path():
    with pytest.raises(ValueError):
        powershell_bootstrap_handoff_command(
            ssh_host="ai-ws", bootstrap_script="tools/awui-bootstrap.ps1", remote_session_file="/srv/state/request.json",
        )


def test_posix_bootstrap_detects_runtime_and_cleans_up():
    command = posix_bootstrap_handoff_command(
        ssh_host="linux-box", bootstrap_script="/srv/agent-workflow-ui/tools/awui-bootstrap.sh",
        remote_session_file="/srv/state/request.json", backend="gui",
    )
    assert "mktemp" in command
    assert "'linux-box' '/srv/state/request.json'" in command
    assert "sh \"$d/a\" 'linux-box' '/srv/state/request.json'" in command
    assert "trap 'rm -rf \"$d\"' EXIT" in command


def test_handoff_message_prints_windows_round_trip_command():
    message = handoff_message(
        "manual", "/remote/request.json", summary="2 decisions",
        remote={"ssh_host": "build-box", "session_file": "/remote/request.json",
                "event_file": "/remote/events.json", "client_capabilities":
                {"platform": "windows", "shell": "powershell"}},
    )
    assert "Windows PowerShell" in message
    assert "awui-connect --ssh-host build-box" in message
    assert "--remote-event-file '/remote/events.json'" in message


def test_handoff_message_can_print_self_bootstrap_for_windows_and_posix():
    common = {"ssh_host": "ai-ws", "session_file": "/remote/request.json",
              "event_file": "/remote/events.json", "bootstrap_script": "/srv/ui/tools/awui-bootstrap.ps1",
              "client_capabilities": {"platform": "windows", "shell": "powershell", "gui_available": True}}
    message = handoff_message("manual", "/remote/request.json", summary="1 decision", remote=common)
    assert "self-bootstrapping" in message
    assert "-ep Bypass" in message
    common["client_capabilities"] = {"platform": "linux", "shell": "bash", "gui_available": True}
    common["bootstrap_script"] = "/srv/ui/tools/awui-bootstrap.sh"
    message = handoff_message("manual", "/remote/request.json", summary="1 decision", remote=common)
    assert "self-bootstrapping" in message
    assert "'ai-ws' '/remote/request.json'" in message


def test_handoff_rejects_unsafe_short_command_host():
    with pytest.raises(ValueError, match="plain SSH"):
        handoff_message("manual", "/remote/request.json", summary="1 decision", remote={
            "ssh_host": "bad;host", "client_capabilities": {"platform": "windows", "shell": "powershell"}})


def test_linux_remote_handoff_is_also_one_short_connector_command():
    message = handoff_message("manual", "/local/request.json", summary="1 decision", remote={
        "ssh_host": "linux-box", "session_file": "/srv/state/request.json",
        "event_file": "/srv/state/events.json", "client_capabilities":
        {"platform": "linux", "shell": "bash", "gui_available": False}})
    assert "awui-connect --ssh-host linux-box" in message
    assert "--backend tui" in message


def test_private_session_file_can_be_attached(tmp_path):
    path = write_session_file(request(), tmp_path)
    if os.name != "nt":
        assert os.stat(path).st_mode & 0o077 == 0
    assert attach_session(path)["session_id"] == "s-1"


def test_session_file_is_not_overwritten_or_attached_if_public(tmp_path):
    path = write_session_file(request(), tmp_path)
    with pytest.raises(FileExistsError):
        write_session_file(request(), tmp_path)
    if os.name != "nt":
        path.chmod(0o644)
        with pytest.raises(ValueError, match="accessible"):
            attach_session(path)


def test_unsafe_request_is_rejected(tmp_path):
    bad = request()
    bad["session_id"] = "../escape"
    with pytest.raises(ValueError, match="filename"):
        write_session_file(bad, tmp_path)


def test_event_journal_is_private_bounded_and_append_only(tmp_path):
    path = tmp_path / "session.events.jsonl"
    append_event(path, {"session_id": "s-1", "sequence": 1, "event_type": "select"})
    append_event(path, {"session_id": "s-1", "sequence": 2, "event_type": "reconciled"})
    assert path.read_text().count("session_id") == 2
    if os.name != "nt":
        assert os.stat(path).st_mode & 0o077 == 0
