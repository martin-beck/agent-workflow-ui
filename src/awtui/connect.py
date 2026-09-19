"""One-command local and SSH handoff for a Coordinator decision session."""
from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import tempfile
import tarfile
import re
from pathlib import Path

from .host import detect_ui_backend


def environment_fingerprint() -> dict[str, str]:
    """Return stable facts used by a future portable runtime bootstrap."""
    return {"platform": platform.system().lower(), "architecture": platform.machine().lower(),
            "python": platform.python_version(), "shell": os.environ.get("SHELL", "powershell" if os.name == "nt" else "sh")}


def runtime_archive_name(facts: dict[str, str] | None = None) -> str:
    facts = facts or environment_fingerprint()
    return f"awui-{facts['platform']}-{facts['architecture']}.tar.gz"


def bootstrap_runtime(archive: str | Path, destination: str | Path) -> Path:
    """Extract a bounded, prebuilt UI runtime into a temporary directory."""
    source = Path(archive)
    target = Path(destination)
    target.mkdir(parents=True, exist_ok=True)
    with tarfile.open(source, "r:gz") as bundle:
        members = bundle.getmembers()
        if any(member.name.startswith("/") or ".." in Path(member.name).parts or member.issym() or member.islnk() for member in members):
            raise ValueError("runtime archive contains unsafe paths")
        if sum(member.size for member in members if member.isfile()) > 256 * 1024 * 1024:
            raise ValueError("runtime archive exceeds bounded size")
        bundle.extractall(target)
    return target


def _run(command: list[str]) -> int:
    return subprocess.run(command, check=False).returncode


def _validate_remote_path(value: str) -> str:
    if not value or any(char in value for char in "\r\n\x00") or not value.startswith("/"):
        raise ValueError("remote paths must be absolute single-line paths")
    if ".." in Path(value).parts:
        raise ValueError("remote paths must not contain traversal")
    return value


def connect(*, session_file: str, ssh_host: str | None = None,
            remote_event_file: str | None = None, backend: str | None = None) -> int:
    """Run the local GUI/TUI and return its revision-bound result.

    With ``ssh_host`` the request is fetched with the user's OpenSSH config,
    the selected local UI runs, and the event file is copied back.  Commands
    use argv arrays, never a shell, so aliases, ProxyJump, and paths remain
    bounded and injection-safe.
    """
    selected = backend or detect_ui_backend()
    os.environ["AWUI_BACKEND"] = selected
    executable = "awui-live" if selected == "gui" else "awtui-live"
    runtime_root: Path | None = None
    if not shutil.which(executable) and os.environ.get("AWUI_RUNTIME_ARCHIVE"):
        runtime_root = bootstrap_runtime(os.environ["AWUI_RUNTIME_ARCHIVE"], tempfile.mkdtemp(prefix="awui-runtime-"))
        candidate = runtime_root / "bin" / executable
        if candidate.exists():
            executable_argv = [str(candidate)]
        else:
            executable_argv = [os.environ.get("PYTHON", "python"), "-m", "awtui.launcher" if selected == "gui" else "awtui.live"]
    elif not shutil.which(executable):
        # Editable checkouts and Windows module installs may not expose the
        # console script on PATH; the module entry point is equivalent.
        executable_argv = [os.environ.get("PYTHON", "python"), "-m", "awtui.launcher"] if selected == "gui" else [os.environ.get("PYTHON", "python"), "-m", "awtui.live"]
    else:
        executable_argv = [executable]
    output_path = remote_event_file or f"{session_file}.events.jsonl"
    if not ssh_host:
        return _run([*executable_argv, "--session-file", session_file, "--output-json", output_path])
    session_file = _validate_remote_path(session_file)
    remote_result = _validate_remote_path(remote_event_file or f"{session_file}.events.jsonl")
    with tempfile.TemporaryDirectory(prefix="awui-connect-") as directory:
        local_request = Path(directory) / "request.json"
        local_result = Path(directory) / "events.json"
        with local_request.open("wb") as stream:
            fetched = subprocess.run(["ssh", ssh_host, "cat", "--", session_file], stdout=stream, check=False)
        if fetched.returncode != 0:
            return fetched.returncode
        result = _run([*executable_argv, "--session-file", str(local_request), "--output-json", str(local_result)])
        journal = local_result.with_suffix(".events.jsonl")
        if result != 0 or not local_result.is_file():
            return result or 2
        return _run(["scp", "--", str(journal if journal.is_file() else local_result), f"{ssh_host}:{remote_result}"])


def main() -> int:
    parser = argparse.ArgumentParser(prog="awui-connect", description="Open a local or SSH-backed Agent Workflow decision session")
    parser.add_argument("--session-file", required=True, help="Coordinator request path; remote when --ssh-host is supplied")
    parser.add_argument("--ssh-host", help="SSH config alias for the authoritative Coordinator host")
    parser.add_argument("--remote-event-file", help="Remote result path (defaults to SESSION.events.jsonl)")
    parser.add_argument("--backend", choices=("gui", "tui"), help="Override environment detection")
    parser.add_argument("--runtime-archive", help="Optional platform/architecture runtime archive for a temporary self-contained launch")
    args = parser.parse_args()
    if args.runtime_archive:
        os.environ["AWUI_RUNTIME_ARCHIVE"] = args.runtime_archive
    return connect(session_file=args.session_file, ssh_host=args.ssh_host,
                   remote_event_file=args.remote_event_file, backend=args.backend)


if __name__ == "__main__":
    raise SystemExit(main())
