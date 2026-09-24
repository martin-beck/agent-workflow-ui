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
import hashlib
import uuid
from pathlib import Path

from .host import detect_ui_backend


def _normalise_architecture(value: str) -> str:
    """Map platform spellings to the archive names used by the launcher."""
    return {
        "amd64": "amd64", "x86_64": "x86_64", "x64": "amd64",
        "arm64": "arm64", "aarch64": "aarch64", "x86": "x86",
        "i386": "x86", "i686": "x86",
    }.get(value.lower(), value.lower())


def environment_fingerprint() -> dict[str, str]:
    """Return stable facts used by a portable runtime bootstrap."""
    raw_platform = platform.system().lower()
    normalized_platform = {"win32": "windows", "cygwin": "windows", "darwin": "macos"}.get(raw_platform, raw_platform)
    return {"platform": normalized_platform, "architecture": _normalise_architecture(platform.machine()),
            "python": platform.python_version(), "shell": os.environ.get("SHELL", "powershell" if os.name == "nt" else "sh")}


def runtime_archive_name(facts: dict[str, str] | None = None) -> str:
    facts = facts or environment_fingerprint()
    return f"awui-{facts['platform']}-{facts['architecture']}.tar.gz"


def runtime_manifest(facts: dict[str, str] | None = None) -> dict[str, str]:
    facts = facts or environment_fingerprint()
    return {"schema_version": "1", "platform": facts["platform"],
            "architecture": facts["architecture"], "python": facts["python"]}


def bootstrap_runtime(archive: str | Path, destination: str | Path, *, expected: dict[str, str] | None = None) -> Path:
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
    manifest_path = target / "runtime-manifest.json"
    if not manifest_path.is_file():
        raise ValueError("runtime archive has no manifest")
    manifest = __import__("json").loads(manifest_path.read_text(encoding="utf-8"))
    expected = expected or runtime_manifest()
    for key in ("schema_version", "platform", "architecture"):
        if manifest.get(key) != expected.get(key):
            raise ValueError(f"runtime archive {key} does not match this host")
    return target


def _run(command: list[str], *, env: dict[str, str] | None = None) -> int:
    return subprocess.run(command, check=False, env=env).returncode


def _validate_remote_path(value: str) -> str:
    if not value or any(char in value for char in "\r\n\x00") or not value.startswith("/"):
        raise ValueError("remote paths must be absolute single-line paths")
    if ".." in Path(value).parts:
        raise ValueError("remote paths must not contain traversal")
    return value


def _validate_ssh_host(value: str) -> str:
    """Validate an OpenSSH config alias without interpreting shell syntax."""
    if not value or any(char in value for char in "\r\n\x00;&|`$<>\"' \t"):
        raise ValueError("ssh_host must be a plain SSH config alias or host name")
    return value


def _transport(command: list[str], *, attempts: int) -> int:
    """Run a transport command with bounded reconnect retries."""
    for attempt in range(attempts):
        result = subprocess.run(command, check=False)
        if result.returncode == 0:
            return 0
        if attempt + 1 == attempts:
            return result.returncode
    return 1


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
    runtime_env = os.environ.copy()
    if not shutil.which(executable) and os.environ.get("AWUI_RUNTIME_ARCHIVE"):
        runtime_root = bootstrap_runtime(os.environ["AWUI_RUNTIME_ARCHIVE"], tempfile.mkdtemp(prefix="awui-runtime-"))
        # The archive is deliberately source-oriented and may not contain a
        # console-script entry point.  Make its package importable for the
        # module fallback while retaining the caller's environment.
        runtime_env["PYTHONPATH"] = os.pathsep.join(
            part for part in (str(runtime_root), runtime_env.get("PYTHONPATH", "")) if part
        )
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
        return _run([*executable_argv, "--session-file", session_file, "--output-json", output_path], env=runtime_env)
    ssh_host = _validate_ssh_host(ssh_host)
    session_file = _validate_remote_path(session_file)
    remote_result = _validate_remote_path(remote_event_file or f"{session_file}.events.jsonl")
    try:
        reconnect_attempts = max(1, min(3, int(os.environ.get("AWUI_CONNECT_RETRIES", "2"))))
    except ValueError as error:
        raise ValueError("AWUI_CONNECT_RETRIES must be an integer") from error
    with tempfile.TemporaryDirectory(prefix="awui-connect-") as directory:
        local_request = Path(directory) / "request.json"
        local_result = Path(directory) / "events.json"
        with local_request.open("wb") as stream:
            fetched = subprocess.run(["ssh", ssh_host, "cat", "--", session_file], stdout=stream, check=False)
        if fetched.returncode != 0:
            return fetched.returncode
        # The live launcher rejects group/world-readable session packets;
        # scp/ssh fetches must preserve that privacy boundary locally too.
        os.chmod(local_request, 0o600)
        result = _run([*executable_argv, "--session-file", str(local_request), "--output-json", str(local_result)], env=runtime_env)
        journal = local_result.with_suffix(".events.jsonl")
        if result != 0 or not local_result.is_file():
            return result or 2
        source = journal if journal.is_file() else local_result
        # Upload to a unique sibling and publish with one remote rename. This
        # prevents a reconnect or interrupted copy from exposing partial JSON.
        remote_tmp = f"{remote_result}.tmp-{uuid.uuid4().hex}"
        try:
            code = _transport(["scp", "--", str(source), f"{ssh_host}:{remote_tmp}"], attempts=reconnect_attempts)
            if code:
                return code
            return _transport(["ssh", ssh_host, "mv", "-f", "--", remote_tmp, remote_result], attempts=reconnect_attempts)
        finally:
            # A failed scp or mv must not leave private event material behind.
            subprocess.run(["ssh", ssh_host, "rm", "-f", "--", remote_tmp], check=False)


def main() -> int:
    parser = argparse.ArgumentParser(prog="awui-connect", description="Open a local or SSH-backed Agent Workflow decision session")
    parser.add_argument("--session-file", required=True, help="Coordinator request path; remote when --ssh-host is supplied")
    parser.add_argument("--ssh-host", help="SSH config alias for the authoritative Coordinator host")
    parser.add_argument("--remote-event-file", help="Remote result path (defaults to SESSION.events.jsonl)")
    parser.add_argument("--backend", choices=("gui", "tui"), help="Override environment detection")
    parser.add_argument("--runtime-archive", help="Optional platform/architecture runtime archive for a temporary self-contained launch")
    parser.add_argument("--resume", action="store_true", help="Reconnect to the same revision-bound request after an interrupted UI")
    args = parser.parse_args()
    if args.runtime_archive:
        os.environ["AWUI_RUNTIME_ARCHIVE"] = args.runtime_archive
    if args.resume:
        os.environ["AWUI_CONNECT_RESUME"] = "1"
    return connect(session_file=args.session_file, ssh_host=args.ssh_host,
                   remote_event_file=args.remote_event_file, backend=args.backend)


if __name__ == "__main__":
    raise SystemExit(main())
