"""Minimal HTTPS adapter for the Android registry core."""
from __future__ import annotations

import argparse
import json
import ssl
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from .android_service import AndroidDeviceRegistry


class _Handler(BaseHTTPRequestHandler):
    registry: AndroidDeviceRegistry
    service_key: str = ""

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
        else:
            self._json(404, {"error": "not-found"})

    def do_POST(self) -> None:  # noqa: N802
        try:
            body = self._body()
            if self.path == "/v1/register":
                result = self.registry.redeem(body["qr"], device_public_key=body["device_public_key"],
                                              capabilities=body.get("capabilities", []))
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
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--certfile", required=True)
    parser.add_argument("--keyfile", required=True)
    parser.add_argument("--service-key", default="", help="key required to publish coordinator batches")
    args = parser.parse_args()
    registry = AndroidDeviceRegistry(args.state)
    handler = type("AndroidHandler", (_Handler,), {"registry": registry, "service_key": args.service_key})
    server = ThreadingHTTPServer((args.host, args.port), handler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(args.certfile, args.keyfile)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
