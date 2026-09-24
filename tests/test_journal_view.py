import pytest

from awtui.journal import render_history, render_paused_cards, resume_event


def test_render_history_exposes_resume_state_and_future_requests():
    text = render_history({"ar_id": "AR-22", "task_revision": 4, "responses": {"p1": "select"}, "unresolved": ["p2"], "future_requests": ["AR-30"]})
    assert "Journal AR-22 revision 4" in text
    assert "answered: 1" in text
    assert "unresolved: p2" in text
    assert "future ARs: AR-30" in text


def test_paused_session_cards_show_progress_and_safe_resume_command():
    record = {
        "session_id": "session-1", "project_id": "demo", "ar_id": "AR-0022",
        "task_revision": 4, "packet_digest": "sha256:" + "a" * 64,
        "session_file": "/srv/state/awui-session-1.json", "unresolved": ["design", "rollout"],
    }
    text = render_paused_cards([record])
    assert "Paused sessions (1)" in text
    assert "session-1  AR-0022 r4" in text
    assert "unresolved: design, rollout" in text
    assert "awtui-live --session-file /srv/state/awui-session-1.json" in text
    event = resume_event(record)
    assert event["event_type"] == "resume"
    assert event["session_id"] == "session-1"
    assert event["payload"]["unresolved"] == ["design", "rollout"]


def test_paused_session_cards_reject_incomplete_or_unsafe_records():
    with pytest.raises(ValueError, match="incomplete"):
        render_paused_cards([{"session_id": "s"}])
    with pytest.raises(ValueError, match="incomplete"):
        resume_event({"session_id": "s", "project_id": "p", "ar_id": "AR-0001", "task_revision": 1,
                      "packet_digest": "d", "session_file": "", "unresolved": []})
