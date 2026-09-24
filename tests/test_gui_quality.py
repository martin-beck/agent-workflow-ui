import os

import pytest

pytest.importorskip("PySide6")

from awtui.gui import build_gui_application


def test_gui_actions_have_accessible_names_and_supplemental_help(monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    window = build_gui_application()
    buttons = window.window.findChildren(window.QtWidgets.QPushButton)
    assert {button.text() for button in buttons} >= {"Select", "Reject", "Clarify", "Save", "Save + Exit"}
    assert all(button.accessibleName() for button in buttons)
    assert all(button.toolTip() for button in buttons)
    window.close_without_prompt()
    window.app.quit()


def test_gui_more_evidence_emits_a_persistable_event(monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    events = []
    window = build_gui_application(on_event=events.append)
    window._request_evidence()
    assert events[-1]["event_type"] == "request-more-evidence"
    window.close_without_prompt()
    window.app.quit()


def test_gui_save_emits_same_canonical_snapshot_as_other_renderer(monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    events = []
    window = build_gui_application(on_event=events.append)
    window.interaction.respond("select")
    window._save()
    save = next(event for event in events if event["event_type"] == "save")
    assert save["payload"]["snapshot"]["responses"]["point-1"]["selected"] == "Review in context"
    assert window.interaction.saved is True
    window.close_without_prompt()
    window.app.quit()
