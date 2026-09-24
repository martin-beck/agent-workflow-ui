from awtui.live import build_application
from awtui.discussion import Proposal
from pathlib import Path
from types import SimpleNamespace


def _binding(app, key):
    aliases = {"enter": "Keys.ControlM", "tab": "Keys.ControlI", "escape": "Keys.Escape", "right": "Keys.Right"}
    wanted = aliases.get(key, key)
    return next(binding for binding in app.key_bindings.bindings if str(binding.keys[0]) == wanted)


def _event(app, key):
    return SimpleNamespace(app=app, key_sequence=[SimpleNamespace(key=key)])


def test_prompt_toolkit_application_has_two_panes_and_quit_binding():
    app = build_application(document="design:42", points="design [unresolved]", helper="confidence=.8; impact=bounded")
    assert app.full_screen is True
    assert any(any(str(key) == "q" for key in binding.keys) for binding in app.key_bindings.bindings)
    assert [pane.text for pane in app.awtui_panes] == ["design:42", "design [unresolved]", "confidence=.8; impact=bounded"]


def test_live_controls_emit_explicit_event_types():
    events = []
    app = build_application(on_event=events.append)
    class Event:
        app = None
    for key, expected in (("enter", "select"), ("r", "reject"), ("c", "clarify"), ("m", "request-more-evidence"), ("a", "add-proposal"), ("s", "safe-exit"), ("o", "reopen")):
        binding = next(binding for binding in app.key_bindings.bindings if (str(binding.keys[0]) == key or (key == "enter" and str(binding.keys[0]) == "Keys.ControlM")))
        binding.handler(Event())
        assert events[-1] == expected


def test_live_navigation_switches_documents_and_tracks_decision_anchor():
    app = build_application(
        workplan="WORKPLAN: ship parser",
        design_document="DESIGN: parser boundary",
        decisions=[
            {"point_id": "parser", "anchor": "design:L12", "question": "Which parser?",
             "proposals": [{"label": "strict", "rationale": "bounded", "tradeoffs": "migration", "confidence": .8},
                           {"label": "permissive", "rationale": "compatible", "tradeoffs": "ambiguity", "confidence": .6}],
             "helper": "Impact: changes validation."},
            {"point_id": "rollout", "anchor": "plan:L4", "question": "How roll out?",
             "proposals": [{"label": "canary"}, {"label": "direct"}], "helper": "Impact: changes blast radius."},
        ],
    )
    state = app.awtui_state
    assert state.document_mode == "design"
    assert "▶ parser" in app.awtui_panes[1].text
    assert "Anchor: design:L12" in app.awtui_panes[2].text
    state.move(1)
    assert "▶ rollout" in app.awtui_panes[1].text
    assert "Anchor: plan:L4" in app.awtui_panes[2].text
    # A decision anchored in the workplan follows its authoritative document
    # automatically so the highlighted text is visible immediately.
    assert state.document_mode == "workplan"
    state.next_proposal(1)
    assert "Proposal 2/2: direct" in app.awtui_panes[2].text
    state.switch_document()
    assert state.document_mode == "design"
    assert app.awtui_panes[0].text.startswith("▶ ACTIVE DECISION ANCHOR: plan:L4")
    assert "DESIGN: parser boundary" in app.awtui_panes[0].text
    assert "ACTIVE DECISION ANCHOR: plan:L4" in app.awtui_panes[0].text


def test_live_footer_advertises_document_and_focus_controls():
    app = build_application(workplan="plan", design_document="design", decisions=[])
    footer = app.awtui_footer.text
    assert "tab/w/d: workplan/design" in footer
    assert "↑/↓: decision" in footer
    assert "←/→: proposal" in footer


def test_live_application_erases_final_frame_on_terminal_exit():
    app = build_application()
    assert app.erase_when_done is True


def test_standalone_live_launcher_bootstraps_src_import_path():
    launcher = (Path(__file__).parents[1] / "tools/awtui-live").read_text(encoding="utf-8")
    assert "Path(__file__).resolve().parents[1]" in launcher
    assert "sys.path.insert" in launcher


def test_standalone_demo_has_multiple_decisions_and_active_anchor():
    from awtui.live import _standalone_demo_decisions
    app = build_application(workplan="WORKPLAN", design_document="DESIGN", decisions=_standalone_demo_decisions())
    assert len(app.awtui_state.packet.points) == 3
    assert "ACTIVE DECISION ANCHOR: design:L4" in app.awtui_panes[0].text


def test_answered_decision_shows_checkmark_and_only_selected_proposal():
    app = build_application(
        design_document="# Design\n\nBoundary phrase",
        decisions=[{"point_id": "p", "anchor": "design:L2", "highlight": "Boundary phrase", "question": "Choose", "proposals": [{"label": "A"}, {"label": "B"}]}],
    )
    state = app.awtui_state
    state.respond("select")
    rendered = app.awtui_panes[1].text
    assert "✅ answered" in rendered
    assert "A" in rendered and "B" not in rendered
    state.next_proposal(1)
    state.respond("select")
    rendered = app.awtui_panes[1].text
    assert "B" in rendered and "A" not in rendered


def test_clarify_requests_more_context_without_marking_decision_answered():
    app = build_application(
        design_document="# Design\n\nBoundary phrase",
        decisions=[{"point_id": "p", "anchor": "design:L2", "highlight": "Boundary phrase", "question": "Choose", "proposals": [{"label": "A"}, {"label": "B"}]}],
    )
    state = app.awtui_state
    state.respond("select")
    state.respond("clarify")
    rendered = app.awtui_panes[1].text
    assert "⚠ clarification requested" in rendered
    assert "✅ answered" not in rendered
    assert "A" in rendered and "B" in rendered
    assert "Clarification requested" in app.awtui_panes[2].text


def test_own_proposal_is_a_four_field_modal_form_with_confirmation():
    app = build_application(decisions=[{"point_id": "p", "anchor": "design:L1", "question": "Choose", "proposals": [{"label": "A"}, {"label": "B"}]}])
    add = _binding(app, "a")
    enter = _binding(app, "enter")
    right = _binding(app, "right")

    add.handler(_event(app, "a"))
    assert app.interaction.input_mode is True
    assert app.editor.visible is True
    assert len(app.editor_fields) == 4

    # Action letters are ordinary text while editing.
    app.editor.text = "rSafer rollout"
    assert app.editor.text == "rSafer rollout"
    enter.handler(_event(app, "enter"))
    assert app.interaction.proposal_edit_index == 1
    app.editor_fields[1].text = "Because it limits blast radius"
    enter.handler(_event(app, "enter"))
    app.editor_fields[2].text = "0.9"
    enter.handler(_event(app, "enter"))
    app.editor_fields[3].text = "Slower delivery"
    enter.handler(_event(app, "enter"))

    assert app.interaction.proposal_confirm is True
    assert "Confirm own proposal?" in app.confirmation_view.text
    assert "▶ Yes" in app.confirmation_view.text

    right.handler(_event(app, "right"))
    assert "▶ No" in app.confirmation_view.text
    enter.handler(_event(app, "enter"))
    assert app.interaction.input_mode is True
    assert app.interaction.proposal_confirm is False

    # Return to confirmation and accept it.
    app.editor_fields[3].text = "Slower delivery"
    enter.handler(_event(app, "enter"))
    enter.handler(_event(app, "enter"))
    enter.handler(_event(app, "enter"))
    enter.handler(_event(app, "enter"))
    assert app.interaction.proposal_confirm is True
    enter.handler(_event(app, "enter"))
    assert app.interaction.input_mode is False
    assert "User: rSafer rollout" in app.awtui_panes[1].text


def test_status_and_exit_prompt_explain_unresolved_or_unsaved_work():
    app = build_application(decisions=[{"point_id": "p", "anchor": "design:L1", "question": "Choose", "proposals": [{"label": "A"}, {"label": "B"}]}])
    assert "0/1 selected" in app.awtui_panes[1].text
    assert "state unsaved" in app.awtui_panes[1].text

    q = _binding(app, "q")
    q.handler(_event(app, "q"))
    assert app.interaction.exit_confirm is True
    assert "select a proposal for: p" in app.awtui_panes[2].text
    assert "save the current decision state (s)" in app.awtui_panes[2].text

    # Escape/second q cancels the exit prompt and returns to the session.
    q.handler(_event(app, "q"))
    assert app.interaction.exit_confirm is False


def test_user_proposal_is_visible_and_can_be_replaced_before_commit():
    app = build_application(
        design_document="# Design\n\nBoundary phrase",
        decisions=[{"point_id": "p", "anchor": "design:L2", "highlight": "Boundary phrase", "question": "Choose", "proposals": [{"label": "A"}, {"label": "B"}]}],
    )
    state = app.awtui_state
    from awtui.discussion import Proposal
    state.add_proposal(Proposal("User: C", "Because", .9, "Review cost"))
    assert "✎ proposal" in app.awtui_panes[1].text
    assert "User: C" in app.awtui_panes[1].text
    state.respond("select")
    assert "✅ answered" in app.awtui_panes[1].text
    state.next_proposal(-2)
    state.respond("select")
    assert "A" in app.awtui_panes[1].text
    assert "User: C" not in app.awtui_panes[1].text


def test_live_decision_list_shows_effective_window_rollback_and_conflict():
    app = build_application(decisions=[{
        "point_id": "p", "anchor": "design:L2", "question": "Choose",
        "effective_from": "r4", "effective_until": "r7", "rollback_of": "p-old",
        "conflict_reason": "evidence diverged",
        "proposals": [{"label": "A"}, {"label": "B"}],
    }])
    text = app.awtui_panes[1].text
    assert "rollback:p-old" in text
    assert "conflict:evidence diverged" in text
    assert "effective:r4..r7" in text


def test_arrow_navigation_reopens_answered_decision_before_replacement():
    app = build_application(
        design_document="# Design\n\nBoundary phrase",
        decisions=[{"point_id": "p", "anchor": "design:L2", "highlight": "Boundary phrase", "question": "Choose", "proposals": [{"label": "A"}, {"label": "B"}]}],
    )
    state = app.awtui_state
    state.respond("select")
    assert "✅ answered" in app.awtui_panes[1].text
    assert "A" in app.awtui_panes[1].text and "B" not in app.awtui_panes[1].text

    # Navigating to another candidate makes the provisional answer editable;
    # both candidates become visible and Enter can commit the replacement.
    state.next_proposal(1)
    assert "unresolved" in app.awtui_panes[1].text
    assert "A" in app.awtui_panes[1].text and "B" in app.awtui_panes[1].text
    state.respond("select")
    assert "✅ answered" in app.awtui_panes[1].text
    assert "B" in app.awtui_panes[1].text and "A" not in app.awtui_panes[1].text


def test_user_proposal_can_be_reedited_before_final_selection():
    app = build_application(
        decisions=[{"point_id": "p", "anchor": "design:L1", "question": "Choose", "proposals": [{"label": "A"}, {"label": "B"}]}]
    )
    state = app.awtui_state
    state.add_proposal(Proposal("User: First", "Initial rationale", .7, "Initial tradeoff"))
    assert state.begin_edit_proposal() is True
    state.add_proposal(Proposal("User: Revised", "Updated rationale", .9, "Updated tradeoff"))
    assert any(proposal.label == "User: Revised" for proposal in state.point.proposals)
    assert not any(proposal.label == "User: First" for proposal in state.point.proposals)


def test_plan_anchor_follows_workplan_document_on_decision_change():
    app = build_application(
        design_document="# Design\n\nBoundary phrase",
        workplan="# Workplan\n\nRollout phrase",
        decisions=[{"point_id": "p", "anchor": "plan:L2", "highlight": "Rollout phrase", "question": "Choose", "proposals": [{"label": "A"}, {"label": "B"}]}],
    )
    assert app.awtui_state.document_mode == "workplan"
    assert "Rollout phrase" in app.awtui_panes[0].text


def test_run_application_reports_only_safe_status_after_interrupt():
    from awtui.live import run_application

    class Interrupted:
        def run(self, **_kwargs):
            raise KeyboardInterrupt

    output = []
    assert run_application(Interrupted(), output_fn=output.append) == 130
    assert output == ["TUI interrupted; terminal restored."]


def test_run_application_redacts_exception_details():
    from awtui.live import run_application

    class Broken:
        def run(self, **_kwargs):
            raise RuntimeError("private prompt /srv/secret")

    output = []
    assert run_application(Broken(), output_fn=output.append) == 1
    assert output == ["TUI stopped (RuntimeError); terminal restored."]
    assert "/srv/secret" not in output[0]
