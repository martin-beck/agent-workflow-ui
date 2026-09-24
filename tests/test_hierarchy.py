import pytest

from awtui.bridge import board_request
from awtui.dashboard import BoardRequest, HierarchyNavigator
from awtui.live import build_application


def request():
    return board_request(
        project_id="company", ar_id="AR-0084", task_revision=3,
        packet_digest="sha256:packet", rollup_revision=9,
        pages=[{"page_id": "company", "title": "Company", "status": "healthy"}],
        hierarchy=[
            {"node_id": "company", "title": "Company", "kind": "company", "level": 0},
            {"node_id": "platform", "title": "Platform team", "kind": "team", "level": 1, "parent_id": "company"},
            {"node_id": "task-1", "title": "Task one", "kind": "task", "level": 2, "parent_id": "platform"},
        ],
    )


def test_hierarchy_navigation_is_bounded_and_revision_bound():
    navigator = HierarchyNavigator(BoardRequest.from_dict(request()))
    assert navigator.current.node_id == "company"
    navigator.drill_down()
    assert navigator.current.node_id == "platform"
    navigator.drill_down("task-1")
    assert navigator.current.node_id == "task-1"
    with pytest.raises(ValueError):
        navigator.drill_down()
    assert navigator.response()["rollup_revision"] == 9
    navigator.drill_up()
    assert navigator.current.node_id == "platform"


def test_hierarchy_rejects_depth_beyond_contract():
    value = request()
    value["hierarchy"].append({"node_id": "too-deep", "title": "Too deep", "kind": "task", "level": 4, "parent_id": "task-1"})
    with pytest.raises(ValueError, match="depth"):
        BoardRequest.from_dict(value)


def test_live_dashboard_exposes_hierarchy_controls():
    app = build_application(board_request=request())
    assert app.awtui_hierarchy.current.node_id == "company"
    assert "Platform team" in app.awtui_dashboard.text
    assert "]: hierarchy" in app.awtui_footer.text
