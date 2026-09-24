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


def test_batch_workspace_orders_dependencies_and_explains_blocked_points():
    proposals = _point("root").proposals
    child = PacketPoint("child", "plan:2", "child", proposals, "impact", group="rollout", ar_ref="AR-2", depends_on=("root",), evidence_refs=("evidence:child",))
    root = PacketPoint("root", "design:1", "root", proposals, "impact", group="design", ar_ref="AR-1")
    packet = DiscussionPacket("batch", 4, (child, root))
    assert [point.point_id for point in packet.ordered_points()] == ["root", "child"]
    assert packet.summary()["blocked"] == 1
    assert packet.dependency_block(child) == "waiting for: root"
    assert [point.point_id for point in packet.filtered_points(group="rollout")] == ["child"]
    assert packet.filtered_points(query="AR-1")[0].point_id == "root"


def test_batch_workspace_progress_unblocks_dependent_decision():
    proposals = _point("root").proposals
    root = PacketPoint("root", "design:1", "root", proposals, "impact")
    child = PacketPoint("child", "plan:2", "child", proposals, "impact", depends_on=("root",))
    packet = DiscussionPacket("batch", 4, (root, child))
    response = type("Response", (), {"disposition": "select"})()
    assert packet.status(child, {"root": response}) == "unresolved"
    assert packet.summary({"root": response})["blocked"] == 0
