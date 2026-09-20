"""Short installed launcher for revision-bound decision batches.

The installed command is intentionally small: ``awui TOKEN``.  Routing data
stays in the per-user config; the token registry and decision files remain
authoritative on the configured SSH host.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
from pathlib import Path, PurePosixPath

from .connect import connect
from .tokens import TokenError, resolve_batch_token


def _host(value: str) -> str:
    if not value or any(ch not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-" for ch in value):
        raise ValueError("SSH host must be an SSH config alias")
    return value


def _remote_path(value: str) -> str:
    if not value or not value.startswith("/") or ".." in PurePosixPath(value).parts or any(ord(ch) < 32 for ch in value):
        raise ValueError("remote state root must be an absolute safe path")
    return value.rstrip("/")


def _load_config(path: str | Path) -> dict[str, str]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("schema_version") != "1":
        raise ValueError("invalid awui launcher configuration")
    return value


def _registry(host: str, root: str) -> Path:
    remote = f"{_remote_path(root)}/.runtime/awui-tokens.json"
    result = subprocess.run(["ssh", host, "cat", "--", remote], check=False, capture_output=True)
    if result.returncode:
        raise RuntimeError("could not fetch the decision-batch registry")
    handle = tempfile.NamedTemporaryFile(prefix="awui-token-", suffix=".json", delete=False)
    try:
        os.chmod(handle.name, 0o600)
        handle.write(result.stdout)
        handle.close()
        return Path(handle.name)
    except Exception:
        handle.close()
        Path(handle.name).unlink(missing_ok=True)
        raise


def _consume_remote(host: str, root: str, token: str) -> int:
    """Ask the authoritative host to atomically consume a completed token."""
    remote = f"{_remote_path(root)}/.runtime/awui-tokens.json"
    argv = ["ssh", host, "awui-token", "consume", "--registry", remote, "--token", token, "--ssh-host", host]
    result = subprocess.run(argv, check=False)
    if result.returncode == 0:
        return 0
    # A source checkout or a package-only authoritative host may not expose
    # the console script; use the same installed module through Python.
    fallback = subprocess.run(
        ["ssh", host, "python3", "-m", "awtui.tokenctl", "consume", "--registry", remote, "--token", token, "--ssh-host", host],
        check=False,
    )
    return fallback.returncode


def run(*, config: str | Path, token: str, ssh_host: str | None = None) -> int:
    settings = _load_config(config)
    host = _host(ssh_host or str(settings.get("ssh_host", "")))
    root = str(settings.get("remote_state_root", ""))
    registry = _registry(host, root)
    try:
        record = resolve_batch_token(registry, token, ssh_host=host)
    except TokenError as exc:
        raise SystemExit(f"awui: {exc}") from exc
    finally:
        registry.unlink(missing_ok=True)
    result = connect(session_file=record.session_file, ssh_host=host, remote_event_file=record.event_file)
    if result != 0:
        return result
    consumed = _consume_remote(host, root, token)
    if consumed != 0:
        raise RuntimeError("decision journal was returned, but the authoritative token could not be consumed; retry finalization")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="awui", description="Open a tokenized Agent Workflow decision batch")
    parser.add_argument("--config", required=True)
    parser.add_argument("values", nargs="+", help="TOKEN or SSH_HOST TOKEN")
    args = parser.parse_args(argv)
    if len(args.values) == 1:
        host, token = None, args.values[0]
    elif len(args.values) == 2:
        host, token = args.values
    else:
        parser.error("use awui TOKEN or awui SSH_HOST TOKEN")
    return run(config=args.config, token=token, ssh_host=host)


if __name__ == "__main__":
    raise SystemExit(main())
