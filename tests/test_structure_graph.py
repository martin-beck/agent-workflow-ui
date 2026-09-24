import pytest

from awtui.graph import structure_graph_to_tui
from awtui.live import build_application_from_structure_graph


def graph():
    return {
        "ar_id": "AR-0005", "task_revision": 3, "request_id": "AWG-GRAPH-001",
        "nodes": [
            {"node_id": "design-root", "document": "design", "markdown": "# Design\n\nBoundary decision text", "anchors": [{"anchor": "boundary", "text": "Boundary decision text"}]},
            {"node_id": "plan-root", "document": "workplan", "markdown": "# Workplan\n\nRollout decision text", "anchors": [{"anchor": "rollout", "text": "Rollout decision text"}]},
        ],
        "decisions": [{"point_id": "boundary", "node_id": "design-root", "anchor": "boundary", "question": "Choose boundary", "proposals": [{"candidate_id": "C-BOUNDARY", "label": "Keep boundary", "rationale": "Stable", "confidence": .8, "tradeoffs": "Slower", "impact": "low", "reversibility": "easy"}, {"candidate_id": "C-REWORK", "label": "Rework boundary", "rationale": "Flexible", "confidence": .5, "tradeoffs": "Risk", "impact": "high", "reversibility": "difficult"}]}],
    }


def test_graph_generates_authoritative_documents_and_anchor_highlight():
    documents, decisions = structure_graph_to_tui(graph())
    assert documents["design"].endswith("Boundary decision text")
    assert documents["workplan"].endswith("Rollout decision text")
    assert decisions[0]["anchor"] == "design:boundary"
    assert decisions[0]["highlight"] == "Boundary decision text"


def test_graph_highlight_must_exist_in_referenced_source_node():
    value = graph()
    value["decisions"][0]["anchor"] = "missing"
    with pytest.raises(ValueError, match="highlight is absent"):
        structure_graph_to_tui(value)


def test_repeated_anchor_text_gets_distinct_occurrence_ranges():
    value = {
        "nodes": [
            {"node_id": "d", "document": "design",
             "markdown": "# Design\n\nChoose the boundary.\n\nChoose the boundary.",
             "anchors": [
                 {"anchor": "first", "text": "Choose the boundary."},
                 {"anchor": "second", "text": "Choose the boundary."},
             ]},
            {"node_id": "w", "document": "workplan", "markdown": "# Workplan\n\nShip", "anchors": [{"anchor": "ship", "text": "Ship"}]},
        ],
        "decisions": [
            {"point_id": "one", "node_id": "d", "anchor": "first", "proposals": [{"label": "A"}]},
            {"point_id": "two", "node_id": "d", "anchor": "second", "proposals": [{"label": "A"}]},
        ],
    }
    documents, decisions = structure_graph_to_tui(value)
    assert decisions[0]["highlight_ranges"]["design"][0]["occurrence"] == 0
    assert decisions[1]["highlight_ranges"]["design"][0]["occurrence"] == 1
    assert decisions[0]["highlight_ranges"]["design"][0]["start"] < decisions[1]["highlight_ranges"]["design"][0]["start"]


def test_graph_build_wires_candidate_identity_into_tui_state():
    app = build_application_from_structure_graph(graph(), project_id="demo", session_id="session-1")
    assert app.awtui_state.candidate_ids["boundary"]["Keep boundary"] == "C-BOUNDARY"
    assert "Boundary decision text" in app.awtui_panes[0].text
