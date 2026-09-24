from awtui.live import LiveInteraction, _default_packet, build_application_from_context


def record():
    return {
        "session_id": "s-1", "project_id": "demo", "ar_id": "AR-0001",
        "task_revision": 2, "packet_digest": "sha256:" + "b" * 64,
        "session_file": "/srv/state/s-1.json", "unresolved": ["p2"],
    }


def test_interaction_exposes_paused_card_and_revision_bound_resume_event():
    interaction = LiveInteraction(_default_packet("design", "boundary"), paused_sessions=[record()])
    assert "Paused sessions (1)" in interaction.render_helper()
    event = interaction.resume_selected_session()
    assert event["event_type"] == "resume"
    assert event["payload"]["session_file"] == "/srv/state/s-1.json"


def test_context_passes_paused_records_into_live_application():
    context = {
        "project_id": "demo", "ar_id": "AR-0001", "task_revision": 2,
        "packet_digest": "sha256:" + "c" * 64, "session_id": "s-2",
        "documents": {"design": "# Design", "workplan": "# Workplan"},
        "paused_sessions": [record()],
    }
    app = build_application_from_context(context, decisions=[{
        "point_id": "p1", "anchor": "design:1", "question": "Choose",
        "proposals": [{"label": "A"}, {"label": "B"}],
    }])
    assert len(app.interaction.paused_sessions) == 1
    assert "Paused sessions" in app.interaction.render_helper()
