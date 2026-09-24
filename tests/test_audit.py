import json

import pytest

from awtui.audit import AuditContext, AuditControl, audit_from_context
from awtui.live import LiveInteraction, _default_packet, build_application


def context():
    return {"project_id": "demo", "ar_id": "AR-0102", "task_revision": 3,
            "packet_digest": "sha256:" + "a" * 64, "session_id": "audit-1"}


def test_audit_is_revision_bound_and_redacts_payloads():
    audit = audit_from_context(context(), max_entries=3)
    audit.record("select", sequence=1, detail="point-1", payload={"proposal": "private text"})
    exported = audit.export()
    assert exported["redacted"] is True
    assert "private text" not in json.dumps(exported)
    assert exported["context"]["task_revision"] == 3
    with pytest.raises(ValueError, match="unredacted"):
        audit.export(redact=False)


def test_audit_dry_run_has_no_side_effect_and_retention_is_bounded():
    audit = AuditControl(AuditContext("demo", "AR-0102", 3, "sha256:" + "b" * 64, "audit-2"), max_entries=2)
    result = audit.dry_run("save", sequence=1, payload={"snapshot": "private"})
    assert result["dry_run"] is True
    assert audit.entries() == ()
    audit.record("one", timestamp="2026-09-24T00:00:00Z")
    audit.record("two", timestamp="2026-09-24T00:00:01Z")
    audit.record("three", timestamp="2026-09-24T00:00:02Z")
    assert [entry.event_type for entry in audit.entries()] == ["two", "three"]


def test_tui_exposes_revision_bound_audit_view_and_records_decision():
    audit = audit_from_context(context())
    app = build_application(packet=_default_packet("design", "Choose"), audit=audit)
    app.interaction.respond("select")
    assert "select" in app.awtui_audit.text
    assert "AR-0102" in app.awtui_audit.text
    assert "proposal" not in app.awtui_audit.text


def test_invalid_audit_context_is_rejected():
    with pytest.raises(ValueError):
        AuditContext("demo", "AR-0102", 0, "sha256:" + "a" * 64, "s")
