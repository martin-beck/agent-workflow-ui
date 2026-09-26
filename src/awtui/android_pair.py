"""Start/reuse the project HTTPS service and initialize Android pairing.

Pairing is intentionally a separate command from the registry core: the core
creates revision-bound bootstrap records, while this adapter owns the local
service process and its liveness check.
"""
from __future__ import annotations

import argparse
import json
import os
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from .android_service import AndroidDeviceRegistry


def endpoint_for(host: str, port: int) -> str:
    if not host or any(ch.isspace() for ch in host) or host.startswith("-"):
        raise ValueError("public service host must be one hostname or address")
    display = f"[{host}]" if ":" in host and not host.startswith("[") else host
    return f"https://{display}:{port}"


def service_health(endpoint: str, *, timeout: float = 1.5, verify_tls: bool = False) -> bool:
    """Return true only for the service's explicit liveness response."""
    if not endpoint.startswith("https://"):
        raise ValueError("Android pairing endpoint must use HTTPS")
    request = urllib.request.Request(endpoint.rstrip("/") + "/v1/health", method="GET")
    context = None if verify_tls else ssl._create_unverified_context()
    try:
        with urllib.request.urlopen(request, timeout=timeout, context=context) as response:
            return response.status == 200 and json.loads(response.read()) .get("status") == "ok"
    except (OSError, ValueError, json.JSONDecodeError, urllib.error.URLError):
        return False


def ensure_service(*, endpoint: str, state: Path, host: str, port: int,
                   certfile: Path | None, keyfile: Path | None,
                   service_key: str = "", ssh_host: str | None = None,
                   ssh_phone_host: str | None = None,
                   ssh_bind_address: str | None = None,
                   pid_file: Path | None = None, timeout: float = 15.0,
                   start: bool = True, popen=subprocess.Popen) -> bool:
    """Ensure the configured service is healthy; return whether this call started it."""
    if service_health(endpoint):
        return False
    if not start:
        raise RuntimeError(f"Android HTTPS service is not running at {endpoint}")
    if certfile is None or keyfile is None:
        raise RuntimeError("starting Android HTTPS service requires --certfile and --keyfile")
    if not certfile.is_file() or not keyfile.is_file():
        raise RuntimeError("starting Android HTTPS service requires existing certificate and key files")
    command = [sys.executable, "-m", "awtui.android_server", "--state", str(state),
               "--host", host, "--port", str(port), "--certfile", str(certfile),
               "--keyfile", str(keyfile)]
    if service_key:
        command.extend(["--service-key", service_key])
    if ssh_host:
        command.extend(["--ssh-host", ssh_host])
    if ssh_phone_host:
        command.extend(["--ssh-phone-host", ssh_phone_host])
    if ssh_bind_address:
        command.extend(["--ssh-bind-address", ssh_bind_address])
    process = popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL, start_new_session=True)
    if pid_file:
        pid_file.parent.mkdir(parents=True, exist_ok=True)
        pid_file.write_text(str(process.pid) + "\n", encoding="utf-8")
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if service_health(endpoint, timeout=1.0):
            return True
        if process.poll() is not None:
            raise RuntimeError("Android HTTPS service exited before becoming healthy")
        time.sleep(0.15)
    raise TimeoutError(f"Android HTTPS service did not become healthy at {endpoint}")


def _write_pairing(payload: dict, output: Path | None) -> None:
    if output:
        try:
            import qrcode
        except ImportError as exc:
            raise SystemExit("PNG output requires the 'android' extra: pip install agent-workflow-ui[android]") from exc
        output.parent.mkdir(parents=True, exist_ok=True)
        qrcode.make(json.dumps(payload, separators=(",", ":"))).save(output)
        print(output)
    else:
        print(json.dumps(payload, sort_keys=True))


def main() -> None:
    parser = argparse.ArgumentParser(description="Start/reuse HTTPS and initialize Android pairing")
    parser.add_argument("--state", required=True)
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--endpoint", help="public HTTPS endpoint; defaults to --public-host/--service-port")
    parser.add_argument("--public-host", default=os.environ.get("AWUI_ANDROID_PUBLIC_HOST"))
    parser.add_argument("--service-host", default=os.environ.get("AWUI_ANDROID_SERVICE_HOST", "127.0.0.1"))
    parser.add_argument("--service-port", type=int, default=int(os.environ.get("AWUI_ANDROID_SERVICE_PORT", "8765")))
    parser.add_argument("--certfile", type=Path, default=None)
    parser.add_argument("--keyfile", type=Path, default=None)
    parser.add_argument("--service-key", default=os.environ.get("AWUI_WORKFLOW_SERVICE_KEY", ""))
    parser.add_argument("--ssh-host", default=os.environ.get("AWUI_SSH_HOST"))
    parser.add_argument("--ssh-phone-host", default=os.environ.get("AWUI_SSH_PHONE_HOST"))
    parser.add_argument("--ssh-bind-address", default=os.environ.get("AWUI_SSH_BIND_ADDRESS"))
    parser.add_argument("--pid-file", type=Path)
    parser.add_argument("--ttl", type=int, default=300)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--no-start-service", action="store_true")
    args = parser.parse_args()
    endpoint = args.endpoint or endpoint_for(args.public_host or args.service_host, args.service_port)
    if not endpoint.startswith("https://"):
        raise SystemExit("--endpoint must use HTTPS")
    ensure_service(endpoint=endpoint, state=args.state, host=args.service_host,
                   port=args.service_port, certfile=args.certfile, keyfile=args.keyfile,
                   service_key=args.service_key, ssh_host=args.ssh_host,
                   ssh_phone_host=args.ssh_phone_host, ssh_bind_address=args.ssh_bind_address,
                   pid_file=args.pid_file, start=not args.no_start_service)
    payload = AndroidDeviceRegistry(args.state).create_bootstrap(
        project_id=args.project_id, endpoint=endpoint, ttl_seconds=args.ttl)
    _write_pairing(payload, args.output)


if __name__ == "__main__":
    main()
