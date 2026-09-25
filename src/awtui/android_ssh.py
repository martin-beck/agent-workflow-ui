"""OpenSSH rendezvous helpers for Android's outbound SSH tunnel.

The service host owns an outbound reverse forward on the configured SSH alias.
The phone then makes its own outbound SSH connection and forwards localhost to
that loopback-only relay port. Neither endpoint needs an inbound NAT mapping.
"""
from __future__ import annotations

import base64
import hashlib
import os
import queue
import re
import shlex
import subprocess
import threading
import time
from dataclasses import dataclass

from .android import ssh_public_key_fingerprint

_ALIAS = re.compile(r"^[A-Za-z0-9_.@:-]{1,253}$")
_ALLOCATED = re.compile(r"Allocated port ([0-9]+) for remote forward to 127\.0\.0\.1:[0-9]+")

_REMOTE_KEY_HELPER = r'''import fcntl,json,os,pathlib,stat,sys,tempfile
request=json.load(sys.stdin); device=request["device_id"]
if not device or not all(c.isalnum() or c in "_-" for c in device): raise SystemExit("invalid device id")
ssh=pathlib.Path.home()/".ssh"; ssh.mkdir(mode=0o700,exist_ok=True); os.chmod(ssh,0o700)
path=ssh/"authorized_keys"; marker="awui:"+device
try:
 st=path.lstat()
 if not stat.S_ISREG(st.st_mode) or st.st_uid!=os.getuid(): raise SystemExit("unsafe authorized_keys owner or type")
except FileNotFoundError: pass
if request["operation"]=="install":
 line=request["line"]
 if "\n" in line or "\r" in line or marker not in line: raise SystemExit("invalid authorized key record")
 fd=os.open(path,os.O_RDWR|os.O_CREAT|getattr(os,"O_NOFOLLOW",0),0o600)
 with os.fdopen(fd,"r+") as out:
  fcntl.flock(out,fcntl.LOCK_EX); lines=out.read().splitlines()
  if any(marker in old for old in lines): raise SystemExit("device key marker already exists")
  out.seek(0,2)
  out.write(line+"\n"); out.flush(); os.fsync(out.fileno())
 os.chmod(path,0o600)
elif request["operation"]=="revoke":
 if not path.exists(): raise SystemExit(0)
 lines=path.read_text().splitlines(keepends=True)
 retained=[line for line in lines if marker not in line]
 if len(retained)==len(lines): raise SystemExit("device key marker not found")
 fd,tmp=tempfile.mkstemp(prefix="authorized_keys.",dir=ssh)
 try:
  with os.fdopen(fd,"w") as out: out.writelines(retained); out.flush(); os.fsync(out.fileno())
  os.chmod(tmp,0o600); os.replace(tmp,path)
 finally:
  if os.path.exists(tmp): os.unlink(tmp)
else: raise SystemExit("invalid operation")
'''


def authorized_key_record(public_key: str, device_id: str, forward_port: int,
                          *, expires_at: str) -> str:
    """Build an attributable key restricted to one loopback TCP target and no shell."""
    if not re.fullmatch(r"android-[A-Za-z0-9_-]{8,128}", device_id):
        raise ValueError("invalid Android device id")
    if not 1 <= forward_port <= 65535:
        raise ValueError("invalid SSH forward port")
    from datetime import datetime
    try:
        expiry = datetime.fromisoformat(expires_at.replace("Z", "+00:00")).strftime("%Y%m%d%H%M%SZ")
    except ValueError as exc:
        raise ValueError("invalid SSH key expiry") from exc
    fingerprint = ssh_public_key_fingerprint(public_key)
    if not fingerprint.startswith("SHA256:"):
        raise ValueError("invalid device public key")
    fields = public_key.strip().split()
    if len(fields) < 2 or fields[0] != "ecdsa-sha2-nistp256":
        raise ValueError("Android enrollment requires an ECDSA P-256 OpenSSH key")
    options = (f'restrict,port-forwarding,permitopen="127.0.0.1:{forward_port}",'
               f'command="/usr/bin/false",expiry-time="{expiry}"')
    return f"{options} {fields[0]} {fields[1]} awui:{device_id}"


def mutate_authorized_key(alias: str, *, operation: str, device_id: str,
                          line: str = "") -> None:
    """Run a fixed remote helper over pre-authorized SSH config; no shell data interpolation."""
    alias = configured_alias(alias) or ""
    if operation not in {"install", "revoke"}:
        raise ValueError("unsupported authorized-key operation")
    payload = __import__("json").dumps({"operation": operation, "device_id": device_id,
                                          "line": line}, separators=(",", ":"))
    command = ["ssh", "-T", "-oBatchMode=yes", "-oStrictHostKeyChecking=yes", alias,
               "python3", "-c", shlex.quote(_REMOTE_KEY_HELPER)]
    result = subprocess.run(command, input=payload, text=True, capture_output=True, timeout=20)
    if result.returncode:
        raise RuntimeError("authorized-key update failed on SSH rendezvous")


def configured_alias(explicit: str | None = None) -> str | None:
    """Resolve a user-selected SSH config alias; never guess a host."""
    value = explicit or os.environ.get("AWUI_SSH_HOST")
    if not value:
        return None
    if not _ALIAS.fullmatch(value) or value.startswith("-"):
        raise ValueError("SSH rendezvous must be a simple configured host alias")
    return value


def _ssh_config(alias: str) -> dict[str, str]:
    result = subprocess.run(["ssh", "-G", alias], check=True, capture_output=True,
                            text=True, timeout=10, env={**os.environ, "LC_ALL": "C"})
    values: dict[str, str] = {}
    for line in result.stdout.splitlines():
        key, _, value = line.partition(" ")
        if key in {"hostname", "port", "user", "identityfile", "userknownhostsfile"} and key not in values:
            values[key] = value.strip()
    if not values.get("hostname") or not values.get("user"):
        raise ValueError("SSH config did not resolve host and user")
    return values


def host_key_fingerprint(alias: str) -> str:
    """Return an already trusted known_hosts fingerprint; never TOFU/scan silently."""
    config = _ssh_config(alias)
    host, port = config["hostname"], int(config.get("port", "22"))
    known_hosts = config.get("userknownhostsfile", "~/.ssh/known_hosts").split()[0]
    searches = [alias, host, f"[{host}]:{port}"]
    key_lines: set[str] = set()
    for search in searches:
        found = subprocess.run(["ssh-keygen", "-F", search, "-f", os.path.expanduser(known_hosts)],
                               capture_output=True, text=True, timeout=5)
        for line in found.stdout.splitlines():
            if line.startswith("#") or not line.strip():
                continue
            fields = line.split()
            if len(fields) >= 3 and fields[1].startswith(("ssh-", "ecdsa-", "sk-")):
                key_lines.add(" ".join(fields[1:3]))
    fingerprints = set()
    for line in key_lines:
        kind, encoded = line.split()[:2]
        blob = base64.b64decode(encoded, validate=True)
        if not blob.startswith(len(kind).to_bytes(4, "big") + kind.encode()):
            continue
        fingerprints.add("SHA256:" + base64.b64encode(hashlib.sha256(blob).digest()).decode().rstrip("="))
    if len(fingerprints) != 1:
        raise ValueError("SSH alias must have exactly one already-trusted host key fingerprint")
    return next(iter(fingerprints))


@dataclass
class ReverseTunnel:
    alias: str
    remote_port: int
    process: subprocess.Popen[str]

    def close(self) -> None:
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)


def rendezvous_metadata(alias: str, remote_forward_port: int, *, phone_host: str | None = None) -> dict[str, object]:
    alias = configured_alias(alias) or ""
    config = _ssh_config(alias)
    host = phone_host or os.environ.get("AWUI_SSH_PHONE_HOST") or config["hostname"]
    if not host or any(ch.isspace() for ch in host) or host.startswith("-"):
        raise ValueError("SSH phone-reachable host candidate is invalid")
    return {"host": host, "port": int(config.get("port", "22")),
            "username": config["user"], "forward_port": remote_forward_port,
            "host_key_fingerprint": host_key_fingerprint(alias)}


def open_reverse_tunnel(alias: str, local_service_port: int, *,
                        bind_address: str = "127.0.0.1", timeout: float = 15.0) -> ReverseTunnel:
    """Open a loopback-only dynamic reverse forward through a known SSH alias."""
    alias = configured_alias(alias) or ""
    if not alias or not 1 <= local_service_port <= 65535:
        raise ValueError("SSH alias and local service port are required")
    if bind_address not in {"127.0.0.1", "0.0.0.0", "::1", "::"}:
        raise ValueError("SSH reverse tunnel bind address must be loopback or wildcard")
    # StrictHostKeyChecking uses the resolved alias/host records from OpenSSH's
    # config. BatchMode prevents hidden password prompts and CI hangs.
    command = ["ssh", "-N", "-T", "-v", "-oBatchMode=yes", "-oStrictHostKeyChecking=yes",
               "-oExitOnForwardFailure=yes", "-oServerAliveInterval=15", "-oServerAliveCountMax=3",
               "-R", f"{bind_address}:0:127.0.0.1:{local_service_port}", alias]
    process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                stderr=subprocess.PIPE, text=True, bufsize=1,
                                env={**os.environ, "LC_ALL": "C"})
    lines: queue.Queue[str | None] = queue.Queue()

    def collect() -> None:
        assert process.stderr is not None
        try:
            for item in process.stderr:
                lines.put(item)
        finally:
            lines.put(None)

    threading.Thread(target=collect, name="awui-ssh-diagnostics", daemon=True).start()
    deadline = time.monotonic() + timeout
    try:
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError("SSH rendezvous exited before opening its reverse forward")
            try:
                line = lines.get(timeout=min(0.25, max(0.01, deadline - time.monotonic())))
            except queue.Empty:
                continue
            if line is None:
                break
            match = _ALLOCATED.search(line)
            if match:
                port = int(match.group(1))
                if 1 <= port <= 65535:
                    return ReverseTunnel(alias, port, process)
        raise TimeoutError("SSH rendezvous did not report a remote forward allocation")
    except BaseException:
        if process.poll() is None:
            process.terminate()
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()
        raise
