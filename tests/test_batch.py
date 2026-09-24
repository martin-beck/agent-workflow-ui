from awtui.discussion import DiscussionPacket, PacketPoint, Proposal, render_batch


def _point(point_id: str) -> PacketPoint:
    proposals = (Proposal("A", "keeps scope", .8, "slower"), Proposal("B", "faster", .6, "riskier"))
    return PacketPoint(point_id, f"doc:{point_id}", "choose", proposals, "measure impact")


def test_batch_render_preserves_point_identity_and_partial_answers():
    packet = DiscussionPacket("AR-21", 3, (_point("p1"), _point("p2")))
    output = render_batch(packet, {"p1": object()}, coupling_warning="p2 depends on p1")
    assert "batch 2 points" in output
    assert "COUPLING WARNING: p2 depends on p1" in output
    assert "p1: answered" in output
    assert "p2: unresolved" in output


def test_batch_render_marks_effective_window_rollback_and_conflict():
    point = PacketPoint("p3", "doc:p3", "choose", _point("p3").proposals,
                        "impact", effective_from="r4", effective_until="r7",
                        rollback_of="p2", conflict_reason="evidence diverged")
    output = render_batch(DiscussionPacket("AR-21", 4, (point,)))
    assert "effective r4..r7" in output
    assert "rollback of p2" in output
    assert "conflict: evidence diverged" in output
