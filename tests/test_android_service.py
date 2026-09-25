from datetime import datetime, timezone

import pytest

from awtui.android_service import AndroidDeviceRegistry


def test_registration_is_one_time_and_event_routing_is_idempotency_guarded(tmp_path):
    registry = AndroidDeviceRegistry(tmp_path / "service.json")
    qr = registry.create_bootstrap(project_id="p", endpoint="https://workflow.example")
    response = registry.redeem(qr, device_public_key="k" * 32, capabilities=["decisions"])
    message = {"schema_version": "1.0", "kind": "android-decision-event",
               "project_id": "p", "device_id": response["device_id"], "session_id": "session-1",
               "task_revision": 2, "packet_digest": "sha256:" + "a" * 64,
               "sequence": 1, "event_type": "select", "payload": {}}
    ack = registry.route_event(device_id=response["device_id"], credential=response["credential"],
                               message=message, project_id="p", session_id="session-1",
                               task_revision=2, packet_digest=message["packet_digest"])
    assert ack["kind"] == "android-ack"
    with pytest.raises(ValueError, match="replayed"):
        registry.route_event(device_id=response["device_id"], credential=response["credential"],
                             message=message, project_id="p", session_id="session-1",
                             task_revision=2, packet_digest=message["packet_digest"])
    with pytest.raises(ValueError, match="already redeemed"):
        registry.redeem(qr, device_public_key="z" * 32, capabilities=[])


def test_expired_bootstrap_and_revoked_device_fail_closed(tmp_path):
    now = [datetime(2026, 9, 25, 12, 0, tzinfo=timezone.utc)]
    registry = AndroidDeviceRegistry(tmp_path / "service.json", clock=lambda: now[0])
    qr = registry.create_bootstrap(project_id="p", endpoint="https://workflow.example", ttl_seconds=30)
    now[0] = datetime(2026, 9, 25, 12, 1, tzinfo=timezone.utc)
    with pytest.raises(ValueError, match="expired"):
        registry.redeem(qr, device_public_key="k" * 32, capabilities=[])


def test_published_batch_is_revision_bound_and_only_visible_to_registered_device(tmp_path):
    registry = AndroidDeviceRegistry(tmp_path / "service.json")
    qr = registry.create_bootstrap(project_id="p", endpoint="https://workflow.example")
    response = registry.redeem(qr, device_public_key="k" * 32, capabilities=["decisions"])
    batch = {"session_id": "s", "task_revision": 4, "packet_digest": "sha256:" + "b" * 64,
             "decisions": [{"id": "D-1", "title": "Choose", "proposals": ["A", "B"]}],
             "design_markdown": "# Design\n\nChoose A or B.",
             "workplan_markdown": "# Work plan\n\nDecision D-1."}
    registry.publish_batch(project_id="p", batch=batch)
    assert registry.get_batch(device_id=response["device_id"], credential=response["credential"]) == batch
    with pytest.raises(ValueError, match="credential"):
        registry.get_batch(device_id=response["device_id"], credential="wrong")
