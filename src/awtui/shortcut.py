"""Short installed launcher for revision-bound decision batches.

The installed command is intentionally small: ``awui TOKEN``.  Routing data
stays in the per-user config; the token registry and decision files remain
authoritative on the configured SSH host.
"""
from __future__ import annotations

import argparse
import json
import os
import shlex
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
    # A source checkout or package-only authoritative host may not expose the
    # console script. Use a bounded stdlib-only finalizer so remote hosts do
    # not need a pre-installed UI package merely to own the registry.
    finalizer = r'''import datetime,fcntl,hashlib,json,os,tempfile,sys
p,t,h=sys.argv[2:]
if len(t)!=8 or any(c not in "ABCDEFGHJKLMNPQRSTUVWXYZ23456789" for c in t): raise SystemExit("invalid token")
with open(p+".lock","a+b") as lock:
 fcntl.flock(lock,fcntl.LOCK_EX)
 with open(p,encoding="utf-8") as stream: data=json.load(stream)
 item=next((x for x in data.get("tokens",[]) if x.get("token_digest")==hashlib.sha256(t.encode("ascii")).hexdigest()),None)
 if item is None: raise SystemExit("unknown batch token")
 if item.get("status")!="active": raise SystemExit("batch token is no longer active")
 if item.get("ssh_host")!=h: raise SystemExit("batch token ssh_host mismatch")
 expires=datetime.datetime.fromisoformat(item["expires_at"].replace("Z","+00:00"))
 if datetime.datetime.now(datetime.timezone.utc)>=expires: raise SystemExit("batch token has expired")
 item["status"]="consumed"; item["consumed_at"]=datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00","Z")
 fd,tmp=tempfile.mkstemp(prefix="."+os.path.basename(p)+".",dir=os.path.dirname(p)); os.fchmod(fd,0o600)
 with os.fdopen(fd,"w",encoding="utf-8") as out: json.dump(data,out,sort_keys=True,indent=2); out.write("\\n"); out.flush(); os.fsync(out.fileno())
 os.replace(tmp,p)'''
    fallback = subprocess.run(
        ["ssh", host, f"python3 -c {shlex.quote(finalizer)} -- {shlex.quote(remote)} {shlex.quote(token)} {shlex.quote(host)}"],
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
    try:
        return run(config=args.config, token=token, ssh_host=host)
    except (OSError, ValueError, RuntimeError) as exc:
        parser.error(str(exc))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
