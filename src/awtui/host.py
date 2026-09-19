"""Safe local host handoff for Coordinator-owned TUI sessions."""
from __future__ import annotations

import json
import os
import shlex
import stat
import sys
from pathlib import Path
from typing import Any

LAUNCH_MODES = {"inline", "tty", "tmux", "manual"}
MAX_SESSION_BYTES = 2 * 1024 * 1024


def powershell_ssh_handoff_command(
    *,
    ssh_host: str,
    remote_session_file: str | Path,
    remote_event_file: str | Path | None = None,
    local_session_file: str = "$env:TEMP\\awui-session.json",
    local_event_file: str = "$env:TEMP\\awui-events.json",
    backend: str = "gui",
) -> str:
    """Build a copyable Windows PowerShell SSH round-trip command.

    ``ssh_host`` is deliberately passed unchanged to OpenSSH, so the user's
    existing ``~/.ssh/config`` alias, ProxyJump, identity, and port settings
    are honored.  The remote coordinator remains the persistence authority:
    the request is copied down, the local UI runs, and the revision-bound
    event file is copied back only after the UI exits.
    """
    if not ssh_host or any(ch in ssh_host for ch in "\r\n;&|`$"):
        raise ValueError("ssh_host must be a plain SSH config alias or host name")
    if backend not in {"gui", "tui"}:
        raise ValueError("backend must be gui or tui")
    remote_request = str(remote_session_file).replace("'", "'\\''")
    remote_result = str(remote_event_file or f"{remote_session_file}.events.jsonl").replace("'", "'\\''")
    executable = "awui-live" if backend == "gui" else "awtui-live"
    return (
        f"ssh {ssh_host} \"cat -- '{remote_request}'\" > \"{local_session_file}\"; "
        f"{executable} --session-file \"{local_session_file}\" --output-json \"{local_event_file}\"; "
        f"scp \"{local_event_file}\" {ssh_host}:'{remote_result}'; "
        f"Remove-Item -Force \"{local_session_file}\",\"{local_event_file}\""
    )


def powershell_bootstrap_handoff_command(
    *, ssh_host: str, bootstrap_script: str, remote_session_file: str | Path,
    remote_event_file: str | Path | None = None, backend: str = "gui",
) -> str:
    """Fetch and execute the trusted bootstrap script from the SSH host.

    The controlling Windows machine needs only OpenSSH, PowerShell, and a
    Python launcher.  The script itself installs the pinned GUI/TUI package
    temporarily through the module entry point, avoiding a PATH dependency.
    """
    values = (ssh_host, bootstrap_script, str(remote_session_file), str(remote_event_file or f"{remote_session_file}.events.jsonl"))
    if not ssh_host or any(any(ch in value for ch in "\r\n;&|`$") for value in values):
        raise ValueError("bootstrap handoff values must be plain single-line arguments")
    if not str(bootstrap_script).startswith("/"):
        raise ValueError("bootstrap_script must be an absolute remote path")
    if backend not in {"gui", "tui"}:
        raise ValueError("backend must be gui or tui")
    script = "$env:TEMP\\awui-bootstrap-$([guid]::NewGuid().ToString('N')).ps1"
    return (
        f"$f = \"{script}\"; ssh {ssh_host} \"cat -- '{bootstrap_script}'\" > $f; "
        f"try {{ powershell -NoProfile -ExecutionPolicy Bypass -File $f "
        f"-SshHost '{ssh_host}' -SessionFile '{remote_session_file}' "
        f"-RemoteEventFile '{remote_event_file or f'{remote_session_file}.events.jsonl'}' -Backend {backend} }} "
        f"finally {{ Remove-Item -Force $f -ErrorAction SilentlyContinue }}"
    )


def posix_bootstrap_handoff_command(
    *, ssh_host: str, bootstrap_script: str, remote_session_file: str | Path,
    remote_event_file: str | Path | None = None, backend: str = "gui",
) -> str:
    """Fetch and execute the matching POSIX bootstrap script over SSH."""
    values = (ssh_host, bootstrap_script, str(remote_session_file), str(remote_event_file or f"{remote_session_file}.events.jsonl"))
    if not ssh_host or any(any(ch in value for ch in "\r\n;&|`$") for value in values):
        raise ValueError("bootstrap handoff values must be plain single-line arguments")
    if not str(bootstrap_script).startswith("/"):
        raise ValueError("bootstrap_script must be an absolute remote path")
    if backend not in {"gui", "tui"}:
        raise ValueError("backend must be gui or tui")
    return (
        f"f=$(mktemp \"${{TMPDIR:-/tmp}}/awui-bootstrap.XXXXXX\"); "
        f"trap 'rm -f \"$f\"' EXIT; ssh {ssh_host} \"cat -- '{bootstrap_script}'\" > \"$f\"; "
        f"AWUI_SSH_HOST='{ssh_host}' AWUI_SESSION_FILE='{remote_session_file}' "
        f"AWUI_REMOTE_EVENT_FILE='{remote_event_file or f'{remote_session_file}.events.jsonl'}' "
        f"AWUI_BACKEND='{backend}' sh \"$f\""
    )


def client_capabilities(*, environ: dict[str, str] | None = None) -> dict[str, str | bool]:
    """Return explicit client facts; SSH does not expose the client OS."""
    env = os.environ if environ is None else environ
    raw_platform = env.get("AWUI_CLIENT_PLATFORM", "windows" if env.get("OS") == "Windows_NT" else sys.platform)
    platform = {"win32": "windows", "cygwin": "windows", "darwin": "macos"}.get(raw_platform, raw_platform)
    raw_shell = env.get("AWUI_CLIENT_SHELL", "powershell" if platform == "windows" else env.get("SHELL", "sh"))
    shell = Path(raw_shell).name.lower()
    shell = {"powershell.exe": "powershell", "pwsh.exe": "powershell", "pwsh": "powershell",
             "cmd.exe": "cmd", "bash.exe": "bash", "zsh.exe": "zsh", "sh.exe": "sh"}.get(shell, shell)
    if shell not in {"powershell", "cmd", "bash", "zsh", "sh"}:
        shell = "sh"
    gui_value = env.get("AWUI_GUI_AVAILABLE")
    gui_available = gui_value.lower() not in {"0", "false", "no", "off"} if gui_value is not None else bool(
        env.get("DISPLAY") or env.get("WAYLAND_DISPLAY") or platform == "windows"
    )
    return {
        "platform": platform,
        "shell": shell,
        "ssh_config": env.get("AWUI_SSH_CONFIG", "default"),
        "gui_available": gui_available,
    }


def detect_ui_backend(*, environ: dict[str, str] | None = None) -> str:
    """Prefer Qt when a local or X-forwarded display is available."""
    env = os.environ if environ is None else environ
    requested = env.get("AWUI_BACKEND", "").lower()
    if requested in {"gui", "tui"}:
        return requested
    return "gui" if env.get("DISPLAY") or env.get("WAYLAND_DISPLAY") else "tui"


def detect_launch_mode(*, environ: dict[str, str] | None = None, stdin_tty: bool | None = None, stdout_tty: bool | None = None) -> str:
    """Select a host mode without executing host commands."""
    env = os.environ if environ is None else environ
    requested = env.get("AWTUI_LAUNCH_MODE", "").lower()
    if requested in LAUNCH_MODES:
        return requested
    if env.get("TMUX"):
        return "tmux"
    in_tty = sys.stdin.isatty() if stdin_tty is None else stdin_tty
    out_tty = sys.stdout.isatty() if stdout_tty is None else stdout_tty
    return "tty" if in_tty and out_tty else "manual"


def write_session_file(request: dict[str, Any], directory: str | Path) -> Path:
    """Write a Coordinator request with private permissions and bounded size."""
    if request.get("kind") != "coordinator-tui-request" or request.get("schema_version") != "1.0":
        raise ValueError("only coordinator-tui-request schema 1.0 may be attached")
    session_id = request.get("session_id")
    safe = isinstance(session_id, str) and session_id and all(c.isalnum() or c in "._-" for c in session_id)
    if not safe:
        raise ValueError("session_id is not a safe filename component")
    encoded = json.dumps(request, sort_keys=True, separators=(",", ":")).encode("utf-8")
    if len(encoded) > MAX_SESSION_BYTES:
        raise ValueError("session request exceeds bounded session-file size")
    root = Path(directory)
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"awtui-{session_id}.json"
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(encoded)
    except Exception:
        try:
            path.unlink()
        except OSError:
            pass
        raise
    return path


def attach_session(path: str | Path) -> dict[str, Any]:
    """Read and validate the minimal host handoff envelope."""
    candidate = Path(path)
    data = candidate.read_bytes()
    if len(data) > MAX_SESSION_BYTES:
        raise ValueError("session file exceeds bounded size")
    # POSIX exposes mode bits; Windows uses ACLs and reports synthetic mode
    # bits that do not describe the effective DACL.  The creator's Windows
    # profile/ACL is therefore the authority there.
    if os.name != "nt" and stat.S_IMODE(candidate.stat().st_mode) & 0o077:
        raise ValueError("session file must not be group/world accessible")
    value = json.loads(data.decode("utf-8"))
    if value.get("kind") != "coordinator-tui-request" or value.get("schema_version") != "1.0":
        raise ValueError("unsupported session request")
    return value


def append_event(path: str | Path, event: dict[str, Any]) -> None:
    """Append one bounded revision-bound event to a private session journal."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    encoded = (json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    current = target.stat().st_size if target.exists() else 0
    if current + len(encoded) > MAX_SESSION_BYTES:
        raise ValueError("session event journal exceeds bounded size")
    flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND
    fd = os.open(target, flags, 0o600)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
    finally:
        if os.name != "nt" and target.exists() and stat.S_IMODE(target.stat().st_mode) & 0o077:
            target.chmod(0o600)


def launch_argv(mode: str, session_file: str | Path) -> list[str] | None:
    """Return an argv for a host launcher, or None for manual handoff."""
    if mode not in LAUNCH_MODES:
        raise ValueError("unknown launch mode")
    if mode == "manual":
        return None
    command = ["awui-live" if detect_ui_backend() == "gui" else "awtui-live", "--session-file", str(session_file)]
    return ["tmux", "new-window", *command] if mode == "tmux" else command


def handoff_message(mode: str, session_file: str | Path, *, summary: str, remote: dict[str, Any] | None = None) -> str:
    """Render a concise user-facing handoff without launching a process."""
    if mode not in LAUNCH_MODES:
        raise ValueError("unknown launch mode")
    backend = detect_ui_backend()
    if remote:
        capabilities = remote.get("client_capabilities") or client_capabilities()
        if capabilities.get("platform") == "windows" and capabilities.get("shell") == "powershell":
            if not remote.get("ssh_host"):
                raise ValueError("Windows remote handoff requires ssh_host")
            if any(ch in str(remote["ssh_host"]) for ch in "\r\n;&|`$"):
                raise ValueError("ssh_host must be a plain SSH config alias or host name")
            backend = str(remote.get("backend") or ("gui" if capabilities.get("gui_available", True) else "tui"))
            remote_request = str(remote.get("session_file", session_file))
            remote_result = str(remote.get("event_file") or f"{remote_request}.events.jsonl")
            if remote.get("bootstrap_script"):
                command = powershell_bootstrap_handoff_command(
                    ssh_host=str(remote["ssh_host"]), bootstrap_script=str(remote["bootstrap_script"]),
                    remote_session_file=remote_request, remote_event_file=remote_result, backend=backend,
                )
                return f"HUMAN DECISION REQUIRED\n{summary}\nRun in Windows PowerShell (self-bootstrapping):\n  {command}\nWaiting for Coordinator acceptance."
            # The installed connector performs capability detection, request
            # transfer, UI selection, and result upload. Keep the agent's
            # handoff short; the user's SSH config remains authoritative.
            command = f"awui-connect --ssh-host {remote['ssh_host']} --session-file '{remote_request}' --remote-event-file '{remote_result}' --backend {backend}"
            return f"HUMAN DECISION REQUIRED\n{summary}\nRun in Windows PowerShell (SSH config alias preserved):\n  {command}\nWaiting for Coordinator acceptance."
        if remote.get("ssh_host"):
            if any(ch in str(remote["ssh_host"]) for ch in "\r\n;&|`$"):
                raise ValueError("ssh_host must be a plain SSH config alias or host name")
            capabilities = remote.get("client_capabilities") or client_capabilities()
            backend = str(remote.get("backend") or ("gui" if capabilities.get("gui_available", True) else "tui"))
            remote_request = str(remote.get("session_file", session_file))
            remote_result = str(remote.get("event_file") or f"{remote_request}.events.jsonl")
            if remote.get("bootstrap_script"):
                command = posix_bootstrap_handoff_command(
                    ssh_host=str(remote["ssh_host"]), bootstrap_script=str(remote["bootstrap_script"]),
                    remote_session_file=remote_request, remote_event_file=remote_result, backend=backend,
                )
                return f"HUMAN DECISION REQUIRED\n{summary}\nRun in the user-controlled terminal (self-bootstrapping):\n  {command}\nWaiting for Coordinator acceptance."
            command = f"awui-connect --ssh-host {remote['ssh_host']} --session-file '{remote_request}' --remote-event-file '{remote_result}' --backend {backend}"
            return f"HUMAN DECISION REQUIRED\n{summary}\nRun in the user-controlled terminal:\n  {command}\nWaiting for Coordinator acceptance."
    executable = "awui-live" if backend == "gui" else "awtui-live"
    command = shlex.join([executable, "--session-file", str(session_file)])
    if mode == "manual":
        action = f"Run in a user-controlled terminal ({backend}):\n  {command}"
    elif mode == "tmux":
        action = f"Open a configured tmux window with:\n  {shlex.join(launch_argv(mode, session_file) or [])}"
    else:
        action = f"The configured host can launch the {backend.upper()} in the current session."
    return f"HUMAN DECISION REQUIRED\n{summary}\n{action}\nWaiting for Coordinator acceptance."
