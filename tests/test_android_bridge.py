import pytest

from awtui.android import registration_qr, registration_request, validate_decision_message
from android_fixtures import sign_registration


def test_qr_contains_no_credential_and_request_adds_public_key():
    qr = registration_qr(project_id="demo", endpoint="https://workflow.example",
                         bootstrap_id="bootstrap_12345678", expires_at="2026-09-25T13:00:00Z",
                         nonce="a" * 32)
    assert "credential" not in qr
    public_key, signature = sign_registration(qr)
    request = registration_request(qr, device_public_key=public_key, capabilities=["decisions", "markdown"],
                                   proof_signature=signature, consent=True)
    assert request["kind"] == "android-registration-request"
    assert request["capabilities"] == ["decisions", "markdown"]


def test_registration_requires_consent_and_rejects_qr_secret_or_substituted_proof():
    qr = registration_qr(project_id="demo", endpoint="https://workflow.example",
                         bootstrap_id="bootstrap_12345678", expires_at="2026-09-25T13:00:00Z",
                         nonce="a" * 32)
    public_key, signature = sign_registration(qr)
    with pytest.raises(ValueError, match="consent"):
        registration_request(qr, device_public_key=public_key, capabilities=[], proof_signature=signature, consent=False)
    with pytest.raises(ValueError, match="proof"):
        registration_request(qr, device_public_key=public_key, capabilities=[], proof_signature="AAAA", consent=True)
    with pytest.raises(ValueError, match="secret-bearing"):
        registration_request({**qr, "private_key": "must-never-be-here"}, device_public_key=public_key,
                             capabilities=[], proof_signature=signature, consent=True)


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
