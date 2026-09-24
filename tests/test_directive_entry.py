from awtui.live import build_directive_application
from awtui.transport import LiveSessionTransport
from awtui.tokens import TokenError, TokenStore
from datetime import datetime, timedelta, timezone


def context():
    return {"project_id": "demo", "ar_id": "AR-0001", "task_revision": 4,
            "packet_digest": "sha256:" + "a" * 64, "session_id": "directive-1",
            "request_id": "AWG-DIRECT-1", "contract_versions": {"tui": "1"}}


def test_directive_application_exposes_single_entry_editor():
    app = build_directive_application(context(), directive="Review deployment policy")
    assert app.directive_editor.text == "Review deployment policy"
    assert "Ctrl-S" in app.directive_status.text


def test_directive_round_trip_uses_revision_bound_event():
    delivered = []
    transport = LiveSessionTransport(context(), delivered.append)
    ack = transport.submit("directive", request_id="AWG-DIRECT-1", directive="Pause rollout")
    assert ack.accepted
    assert delivered[0]["event_type"] == "directive"
    assert delivered[0]["payload"]["directive"] == "Pause rollout"
    assert delivered[0]["task_revision"] == 4
    assert delivered[0]["sequence"] == 1


def test_directive_batch_token_expiry_is_fail_closed(tmp_path):
    now = datetime(2026, 9, 24, tzinfo=timezone.utc)
    store = TokenStore(tmp_path / "tokens.json")
    token = store.issue(project_id="demo", session_id="directive-1", task_revision=4,
                        packet_digest=context()["packet_digest"], session_file="/state/request.json",
                        event_file="/state/events.jsonl", ssh_host="ai-ws", ttl_seconds=1, now=now)
    try:
        store.resolve(token, ssh_host="ai-ws", now=now + timedelta(seconds=1))
    except TokenError as error:
        assert "expired" in str(error)
    else:
        raise AssertionError("expired directive token was accepted")
