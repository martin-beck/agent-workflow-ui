from awtui.bridge import apply_tui_response, interaction_state, tui_to_coordinator_response


def test_interaction_state_is_explicit_and_pending():
    value = interaction_state(request_id="AWG-DECIDE-1", decision_class="implementation-choice")
    assert value["interaction_required"] is True
    assert value["decision_status"] == "pending"


def test_response_projects_selection_and_ar_text():
    ar = {"id": "AR-0001", "interaction": interaction_state(request_id="AWG-DECIDE-1", decision_class="design")}
    event = {"event_type": "select", "payload": {"disposition": "selected", "request_id": "AWG-DECIDE-1", "selected_candidate": "C-A", "selected": "Use A", "description": "Chosen design", "specification": {"mode": "A"}}}
    result = apply_tui_response(ar, event, response_event_ref="evt-1")
    assert result["interaction"]["interaction_required"] is False
    assert result["decision"]["selected_candidate"] == "C-A"
    assert result["description"] == "Chosen design"


def test_invalid_event_rejected():
    try:
        apply_tui_response({}, {"event_type": "acknowledge"}, response_event_ref="evt")
    except ValueError:
        return
    raise AssertionError("invalid event accepted")


def test_tui_response_is_coordinator_persistence_command():
    request = {"kind": "coordinator-tui-request", "project_id": "p", "session_id": "s", "ar": {"ar_id": "AR-0001", "task_revision": 3}, "interaction": {"decision_request_ref": "AWG-DECIDE-1"}}
    event = {"session_id": "s", "sequence": 1, "event_type": "select", "payload": {"point_id": "p1", "disposition": "selected", "selected_candidate": "C-A"}}
    result = tui_to_coordinator_response(request, event, description_append="Selected C-A")
    assert result["ar_update"]["decision_status"] == "resolved"
    assert result["ar_update"]["specification_update"]["selected_candidate"] == "C-A"


def test_directive_response_is_revision_bound_and_persistable():
    request = {"kind": "coordinator-tui-request", "project_id": "p", "session_id": "s",
               "ar": {"ar_id": "AR-0001", "task_revision": 3},
               "packet_digest": "sha256:" + "a" * 64,
               "interaction": {"decision_request_ref": "AWG-DIRECT-1", "mode": "directive"}}
    event = {"project_id": "p", "ar_id": "AR-0001", "task_revision": 3,
             "packet_digest": request["packet_digest"], "session_id": "s", "sequence": 1,
             "event_type": "directive", "payload": {"request_id": "AWG-DIRECT-1", "directive": "Pause rollout and collect evidence."}}
    result = tui_to_coordinator_response(request, event)
    assert result["ar_update"]["decision_status"] == "resolved"
    assert result["ar_update"]["specification_update"]["directive"].startswith("Pause rollout")


def test_empty_directive_is_rejected():
    ar = {"interaction": interaction_state(request_id="AWG-DIRECT-2", decision_class="board")}
    try:
        apply_tui_response(ar, {"event_type": "directive", "payload": {"directive": "  "}}, response_event_ref="evt")
    except ValueError:
        return
    raise AssertionError("empty directive accepted")
