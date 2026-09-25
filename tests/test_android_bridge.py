from awtui.android import registration_qr, registration_request, validate_decision_message


def test_qr_contains_no_credential_and_request_adds_public_key():
    qr = registration_qr(project_id="demo", endpoint="https://workflow.example",
                         bootstrap_id="bootstrap_12345678", expires_at="2026-09-25T13:00:00Z",
                         nonce="a" * 32)
    assert "credential" not in qr
    request = registration_request(qr, device_public_key="k" * 32, capabilities=["decisions", "markdown"])
    assert request["kind"] == "android-registration-request"
    assert request["capabilities"] == ["decisions", "markdown"]


def test_android_message_is_bound_to_exact_revision_and_device():
    message = {"schema_version": "1.0", "kind": "android-decision-event",
               "project_id": "p", "device_id": "device-1", "session_id": "session-1",
               "task_revision": 4, "packet_digest": "sha256:" + "a" * 64,
               "sequence": 1, "event_type": "select", "payload": {}}
    validate_decision_message(message, project_id="p", session_id="session-1",
                              task_revision=4, packet_digest=message["packet_digest"],
                              device_id="device-1")


def test_android_message_rejects_stale_revision_and_wrong_device():
    message = {"schema_version": "1.0", "kind": "android-decision-event",
               "project_id": "p", "device_id": "device-2", "session_id": "session-1",
               "task_revision": 3, "packet_digest": "sha256:" + "a" * 64,
               "sequence": 1}
    for kwargs in ({"task_revision": 4, "device_id": "device-2"},
                   {"task_revision": 3, "device_id": "device-1"}):
        try:
            validate_decision_message(message, project_id="p", session_id="session-1",
                                      packet_digest=message["packet_digest"], **kwargs)
        except ValueError:
            pass
        else:
            raise AssertionError("invalid Android message accepted")
