from awtui.discussion import DecisionResponse
from awtui.live import LiveInteraction, _default_packet
from awtui.persistence import DurableSessionPersistence, session_snapshot
from awtui.transport import LiveSessionTransport


def _context():
    return {"project_id": "demo", "ar_id": "AR-0097", "task_revision": 4,
            "packet_digest": "sha256:" + "a" * 64, "session_id": "save-1"}


def test_snapshot_contains_complete_batch_and_is_deterministic():
    interaction = LiveInteraction(_default_packet("design", "Choose"))
    interaction.respond("select")
    snapshot = session_snapshot(interaction)
    assert snapshot["responses"]["point-1"]["selected"] == "Review in context"
    assert snapshot["unresolved"] == []
    assert session_snapshot(interaction) == snapshot


def test_save_requires_ack_and_repeated_identical_save_is_idempotent():
    delivered = []
    transport = LiveSessionTransport(_context(), delivered.append)
    interaction = LiveInteraction(_default_packet("design", "Choose"))
    interaction.respond("select")
    events = []
    persistence = DurableSessionPersistence(interaction, transport=transport, on_event=events.append)
    first = persistence.save()
    second = persistence.save()
    assert first.accepted is True
    assert second is None
    assert len(delivered) == 1
    assert delivered[0]["event_type"] == "save"
    assert delivered[0]["payload"]["snapshot"]["responses"]
    assert events[0]["payload"] == delivered[0]["payload"]


def test_rejected_save_does_not_mark_session_saved():
    interaction = LiveInteraction(_default_packet("design", "Choose"))
    interaction.respond("select")
    transport = LiveSessionTransport(_context(), lambda _event: False)
    result = DurableSessionPersistence(interaction, transport=transport).save()
    assert result.accepted is False
    assert interaction.saved is False
