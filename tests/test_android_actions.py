import pytest

from awtui.android import validate_decision_message


def _message(event_type):
    return {
        "schema_version": "1.0", "kind": "android-decision-event",
        "project_id": "p", "session_id": "session-1", "task_revision": 2,
        "packet_digest": "sha256:" + "a" * 64, "sequence": 1,
        "device_id": "android-device", "event_type": event_type, "payload": {},
    }


def test_full_action_vocabulary_is_revision_bound():
    for action in ("select", "reject", "clarify", "request-more-evidence",
                   "add-proposal", "save", "reopen", "safe-exit"):
        validate_decision_message(_message(action), project_id="p",
                                  session_id="session-1", task_revision=2,
                                  packet_digest="sha256:" + "a" * 64,
                                  device_id="android-device")


def test_unknown_action_and_non_object_payload_are_rejected():
    with pytest.raises(ValueError, match="event type"):
        validate_decision_message(_message("invented"), project_id="p",
                                  session_id="session-1", task_revision=2,
                                  packet_digest="sha256:" + "a" * 64,
                                  device_id="android-device")
    message = _message("clarify")
    message["payload"] = "not an object"
    with pytest.raises(ValueError, match="payload"):
        validate_decision_message(message, project_id="p", session_id="session-1",
                                  task_revision=2, packet_digest="sha256:" + "a" * 64,
                                  device_id="android-device")
