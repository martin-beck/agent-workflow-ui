"""HTTP adapter qualification for the Android registration service.

The emulator talks to this same API.  Keeping one localhost test here catches
wire-format regressions without requiring an Android SDK or a long-lived
service in the Python test suite.
"""

from __future__ import annotations

import json
import threading
from android_fixtures import sign_registration
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer

from awtui.android_server import _Handler
from awtui.android_service import AndroidDeviceRegistry


def _request(port: int, method: str, path: str, body: dict | None = None, **headers: str) -> tuple[int, dict]:
    connection = HTTPConnection("127.0.0.1", port, timeout=5)
    encoded = json.dumps(body).encode() if body is not None else None
    request_headers = {"Content-Type": "application/json", **headers}
    connection.request(method, path, encoded, request_headers)
    response = connection.getresponse()
    result = json.loads(response.read())
    connection.close()
    return response.status, result


def test_registration_batch_session_and_event_round_trip(tmp_path):
    registry = AndroidDeviceRegistry(tmp_path / "service.json")
    handler = type("TestAndroidHandler", (_Handler,), {"registry": registry, "service_key": "service-secret"})
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        port = server.server_address[1]
        status, health = _request(port, "GET", "/v1/health")
        assert status == 200 and health["status"] == "ok"

        qr = registry.create_bootstrap(project_id="remote-project", endpoint="https://workflow.example")
        public_key, signature = sign_registration(qr)
        status, registration = _request(
            port,
            "POST",
            "/v1/register",
            {"qr": qr, "device_public_key": public_key, "proof_signature": signature,
             "consent": True, "capabilities": ["decisions", "markdown"]},
        )
        assert status == 200

        batch = {
            "session_id": "remote-session",
            "task_revision": 7,
            "packet_digest": "sha256:" + "c" * 64,
            "decisions": [{"id": "D-1", "title": "Remote choice", "proposals": ["A", "B"]}],
            "design_markdown": "# Design\n\nRemote choice.",
            "workplan_markdown": "# Work plan\n\nReview D-1.",
        }
        status, published = _request(
            port,
            "POST",
            "/v1/batches",
            {"project_id": "remote-project", "batch": batch},
            **{"X-Workflow-Service-Key": "service-secret"},
        )
        assert status == 202 and published["status"] == "published"

        auth = {"Authorization": f"Bearer {registration['credential']}", "X-Device-Id": registration["device_id"]}
        status, session = _request(port, "GET", "/v1/session", **auth)
        assert status == 200 and session == {"status": "pending", "batch": batch}

        digest = batch["packet_digest"]
        message = {
            "schema_version": "1.0",
            "kind": "android-decision-event",
            "project_id": "remote-project",
            "device_id": registration["device_id"],
            "session_id": batch["session_id"],
            "task_revision": batch["task_revision"],
            "packet_digest": digest,
            "sequence": 1,
            "event_type": "select",
            "payload": {"decision_id": "D-1", "answer": "A"},
        }
        status, acknowledgement = _request(
            port,
            "POST",
            "/v1/events",
            {
                "device_id": registration["device_id"],
                "project_id": "remote-project",
                "session_id": batch["session_id"],
                "task_revision": batch["task_revision"],
                "packet_digest": digest,
                "message": message,
            },
            **{"Authorization": f"Bearer {registration['credential']}"},
        )
        assert status == 200
        assert acknowledgement["sequence"] == 1
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
