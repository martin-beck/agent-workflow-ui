"""Minimal HTTPS adapter for the Android registry core."""
from __future__ import annotations

import argparse
import json
import os
import ssl
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

from .android_service import AndroidDeviceRegistry
from .android_ssh import (configured_alias, mutate_authorized_key, open_reverse_tunnel,
                          rendezvous_metadata)


class _Handler(BaseHTTPRequestHandler):
    registry: AndroidDeviceRegistry
    service_key: str = ""
    tunnel_mode: bool = False

    def _json(self, status: int, value: dict[str, Any]) -> None:
        body = json.dumps(value, sort_keys=True).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length > 1_000_000:
            raise ValueError("request body too large")
        value = json.loads(self.rfile.read(length))
        if not isinstance(value, dict):
            raise ValueError("request body must be an object")
        return value

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/v1/health":
            self._json(200, {"status": "ok", "service": "agent-workflow-android"})
        elif self.path == "/v1/session":
            try:
                device_id = self.headers.get("X-Device-Id", "")
                credential = self.headers.get("Authorization", "").removeprefix("Bearer ")
                batch = self.registry.get_batch(device_id=device_id, credential=credential)
                self._json(200, {"status": "pending" if batch else "idle", "batch": batch})
            except (KeyError, TypeError, ValueError) as exc:
                self._json(401, {"error": str(exc)})
        elif urlparse(self.path).path == "/v1/ssh/challenge":
            if not self.tunnel_mode:
                self._json(404, {"error": "not-found"})
                return
            try:
                query = parse_qs(urlparse(self.path).query)
                device_id = query.get("device_id", [""])[0]
                self._json(200, self.registry.create_ssh_challenge(device_id))
            except (KeyError, TypeError, ValueError) as exc:
                self._json(401, {"error": str(exc)})
        else:
            self._json(404, {"error": "not-found"})

    def do_POST(self) -> None:  # noqa: N802
        try:
            body = self._body()
            if self.path == "/v1/register":
                result = self.registry.redeem(body["qr"], device_public_key=body["device_public_key"],
                                              capabilities=body.get("capabilities", []),
                                              proof_signature=body.get("proof_signature", ""),
                                              consent=body.get("consent") is True)
                self._json(200, result)
                return
            if self.path == "/v1/ssh/credential":
                if not self.tunnel_mode:
                    self._json(404, {"error": "not-found"})
                    return
                result = self.registry.release_ssh_credential(
                    device_id=body["device_id"], challenge_id=body["challenge_id"],
                    nonce=body["nonce"], expires_at=body["expires_at"],
                    signature=body["signature"])
                self._json(200, result)
                return
            if self.path == "/v1/events":
                device_id = body["device_id"]
                credential = self.headers.get("Authorization", "").removeprefix("Bearer ")
                result = self.registry.route_event(device_id=device_id, credential=credential,
                                                   message=body["message"], project_id=body["project_id"],
                                                   session_id=body["session_id"],
                                                   task_revision=body["task_revision"],
                                                   packet_digest=body["packet_digest"])
                self._json(200, result)
                return
            if self.path == "/v1/batches":
                if not self.service_key or self.headers.get("X-Workflow-Service-Key") != self.service_key:
                    self._json(401, {"error": "invalid service credential"})
                    return
                self.registry.publish_batch(project_id=body["project_id"], batch=body["batch"])
                self._json(202, {"status": "published", "project_id": body["project_id"]})
                return
            self._json(404, {"error": "not-found"})
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            self._json(400, {"error": str(exc)})

    def log_message(self, *_: Any) -> None:
        return


def main() -> None:
    parser = argparse.ArgumentParser(description="Agent Workflow Android HTTPS service")
    parser.add_argument("--state", required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", "--service-port", type=int, default=8765)
    parser.add_argument("--certfile", required=True)
    parser.add_argument("--keyfile", required=True)
    parser.add_argument("--service-key", default="", help="key required to publish coordinator batches")
    parser.add_argument("--ssh-host", default=os.environ.get("AWUI_SSH_HOST"),
                        help="SSH config alias used for the service-owned reverse tunnel (or AWUI_SSH_HOST)")
    parser.add_argument("--ssh-phone-host", default=os.environ.get("AWUI_SSH_PHONE_HOST"),
                        help="phone-reachable candidate; defaults to HostName from ssh -G")
    parser.add_argument("--ssh-bind-address", default=os.environ.get("AWUI_SSH_BIND_ADDRESS", "0.0.0.0"),
                        help="rendezvous-side reverse tunnel bind; 0.0.0.0 is required for phone bootstrap")
    args = parser.parse_args()
    registry = AndroidDeviceRegistry(args.state)
    handler = type("AndroidHandler", (_Handler,), {"registry": registry, "service_key": args.service_key})
    server = ThreadingHTTPServer((args.host, args.port), handler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(args.certfile, args.keyfile)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    tunnel = None
    try:
        if args.ssh_host:
            alias = configured_alias(args.ssh_host)
            assert alias is not None
            # Forward the actual TLS listener.  This makes the rendezvous
            # endpoint in the QR usable before the phone has credentials or
            # an authorized SSH key of its own.
            tunnel = open_reverse_tunnel(alias, args.port,
                                         bind_address=args.ssh_bind_address)
            metadata = rendezvous_metadata(alias, tunnel.remote_port, phone_host=args.ssh_phone_host)
            registry.configure_ssh_rendezvous(metadata=metadata, service_alias=alias,
                                              installer=mutate_authorized_key)
        server.serve_forever()
    finally:
        if tunnel:
            tunnel.close()
        server.server_close()


if __name__ == "__main__":
    main()
