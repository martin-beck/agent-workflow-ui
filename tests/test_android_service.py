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
    retry = registry.route_event(device_id=response["device_id"], credential=response["credential"],
                                 message=message, project_id="p", session_id="session-1",
                                 task_revision=2, packet_digest=message["packet_digest"])
    assert retry["idempotent"] is True
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


def test_batch_contract_rejects_missing_revision_or_malformed_digest(tmp_path):
    registry = AndroidDeviceRegistry(tmp_path / "service.json")
    for batch in ({"session_id": "s", "task_revision": 0,
                   "packet_digest": "sha256:" + "a" * 64, "decisions": [],
                   "design_markdown": "# D", "workplan_markdown": "# W"},
                  {"session_id": "s", "task_revision": 1, "packet_digest": "bad",
                   "decisions": [], "design_markdown": "# D", "workplan_markdown": "# W"}):
        with pytest.raises(ValueError):
            registry.publish_batch(project_id="p", batch=batch)


def test_expired_device_credential_cannot_poll(tmp_path):
    now = [datetime(2026, 9, 25, 12, 0, tzinfo=timezone.utc)]
    registry = AndroidDeviceRegistry(tmp_path / "service.json", clock=lambda: now[0])
    qr = registry.create_bootstrap(project_id="p", endpoint="https://workflow.example")
    response = registry.redeem(qr, device_public_key="k" * 32, capabilities=[])
    registry.state["devices"][response["device_id"]]["credential_expires_at"] = "2026-09-25T11:59:00Z"
    with pytest.raises(ValueError, match="expired"):
        registry.get_batch(device_id=response["device_id"], credential=response["credential"])


def _device_and_message(registry, *, sequence, answer="A", session="sparse"):
    qr = registry.create_bootstrap(project_id="p", endpoint="https://workflow.example")
    response = registry.redeem(qr, device_public_key=("k" + str(sequence)) * 32,
                                capabilities=["decisions"])
    message = {"schema_version": "1.0", "kind": "android-decision-event",
               "project_id": "p", "device_id": response["device_id"], "session_id": session,
               "task_revision": 2, "packet_digest": "sha256:" + "a" * 64,
               "sequence": sequence, "event_type": "select",
               "payload": {"decision_id": "D-" + str(sequence), "answer": answer}}
    return response, message


def test_sparse_session_sequence_is_accepted_and_repeated_save_is_idempotent(tmp_path):
    registry = AndroidDeviceRegistry(tmp_path / "service.json")
    response, message = _device_and_message(registry, sequence=2)
    first = registry.route_event(device_id=response["device_id"], credential=response["credential"],
                                 message=message, project_id="p", session_id="sparse",
                                 task_revision=2, packet_digest=message["packet_digest"])
    retry = registry.route_event(device_id=response["device_id"], credential=response["credential"],
                                message=message, project_id="p", session_id="sparse",
                                task_revision=2, packet_digest=message["packet_digest"])
    assert first["idempotent"] is False
    assert retry["idempotent"] is True
    assert len(registry.state["events"]) == 1


def test_same_sequence_with_changed_answer_is_rejected(tmp_path):
    registry = AndroidDeviceRegistry(tmp_path / "service.json")
    response, message = _device_and_message(registry, sequence=1, answer="A")
    registry.route_event(device_id=response["device_id"], credential=response["credential"],
                         message=message, project_id="p", session_id="sparse",
                         task_revision=2, packet_digest=message["packet_digest"])
    changed = dict(message, payload={"decision_id": "D-1", "answer": "B"})
    with pytest.raises(ValueError, match="collision"):
        registry.route_event(device_id=response["device_id"], credential=response["credential"],
                             message=changed, project_id="p", session_id="sparse",
                             task_revision=2, packet_digest=message["packet_digest"])
