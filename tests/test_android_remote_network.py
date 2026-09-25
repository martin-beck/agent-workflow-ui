"""Localhost/LAN-shaped qualification for the same HTTPS client contract."""
from __future__ import annotations

import threading
from http.server import ThreadingHTTPServer

import pytest

from awtui.android_client import AndroidRemoteClient
from awtui.android_server import _Handler
from awtui.android_service import AndroidDeviceRegistry


def test_remote_client_polls_and_submits_revision_bound_batch(tmp_path):
    registry = AndroidDeviceRegistry(tmp_path / "state.json")
    qr = registry.create_bootstrap(project_id="p", endpoint="https://workflow.example")
    registration = registry.redeem(qr, device_public_key="k" * 32, capabilities=["decisions"])
    handler = type("RemoteHandler", (_Handler,), {"registry": registry, "service_key": "key"})
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        endpoint = f"http://127.0.0.1:{server.server_address[1]}"
        client = AndroidRemoteClient(endpoint, registration["device_id"], registration["credential"])
        batch = {"session_id": "s", "task_revision": 9, "packet_digest": "sha256:" + "a" * 64,
                 "decisions": [{"id": "D-1", "proposals": ["A", "B"]}],
                 "design_markdown": "# Design", "workplan_markdown": "# Work plan"}
        registry.publish_batch(project_id="p", batch=batch)
        assert client.poll_until_available()["batch"] == batch
        message = {"schema_version": "1.0", "kind": "android-decision-event", "project_id": "p",
                   "device_id": registration["device_id"], "session_id": "s", "task_revision": 9,
                   "packet_digest": batch["packet_digest"], "sequence": 1, "event_type": "select",
                   "payload": {"decision_id": "D-1", "answer": "A"}}
        assert client.submit(message=message, project_id="p", session_id="s", task_revision=9,
                             packet_digest=batch["packet_digest"])["sequence"] == 1
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=5)


def test_remote_client_reconnects_after_service_unavailable(tmp_path):
    client = AndroidRemoteClient("http://127.0.0.1:1", "device", "credential", timeout=0.1)
    with pytest.raises(ConnectionError):
        client.poll_until_available(attempts=2, delay=0)
