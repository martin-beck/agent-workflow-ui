import os

import pytest

pytest.importorskip("PySide6")

from awtui.gui import build_gui_application
from awtui.audit import audit_from_context


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


def test_gui_audit_view_and_redacted_export(monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    audit = audit_from_context({"project_id": "demo", "ar_id": "AR-0102", "task_revision": 2,
                                "packet_digest": "sha256:" + "c" * 64, "session_id": "gui-audit"})
    window = build_gui_application(audit=audit)
    window._show_audit()
    assert window.audit_view.isVisible()
    assert "AR-0102" in window.audit_view.toPlainText()
    assert window.export_audit()["redacted"] is True
    with pytest.raises(ValueError):
        audit.export(redact=False)
    window.close_without_prompt()
    window.app.quit()
