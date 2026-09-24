import pytest

from awtui.bridge import board_request, board_response
from awtui.dashboard import (
    BoardRequest,
    BoardRevisionMismatch,
    accept_board_response,
    render_dashboard,
)
from awtui.live import build_application


def sample_request():
    return board_request(
        project_id="company", ar_id="AR-0083", task_revision=2,
        packet_digest="sha256:packet", rollup_revision=7,
        pages=[
            {"page_id": "company", "title": "Company", "status": "healthy", "completed": 4, "total": 6},
            {"page_id": "bottlenecks", "title": "Bottlenecks", "status": "attention", "blocked": 2,
             "bottlenecks": ["AR-0042 awaits review"]},
        ],
    )


def test_board_request_is_versioned_and_rendered():
    request = BoardRequest.from_dict(sample_request())
    assert request.rollup_revision == 7
    rendered = render_dashboard(request)
    assert "Company dashboard" in rendered
    assert "AR-0042 awaits review" in rendered


def test_board_response_is_bound_to_exact_snapshot():
    request = BoardRequest.from_dict(sample_request())
    response = board_response(sample_request(), page_id="bottlenecks")
    assert accept_board_response(request, response) == "bottlenecks"
    stale = dict(response, rollup_revision=8)
    with pytest.raises(BoardRevisionMismatch):
        accept_board_response(request, stale)


def test_dashboard_is_visible_in_live_application():
    request = sample_request()
    app = build_application(board_request=request)
    assert app.awtui_board_request.rollup_revision == 7
    assert "Company dashboard" in app.awtui_dashboard.text
    assert "AR-0042 awaits review" in app.awtui_dashboard.text
    assert "b: dashboard" in app.awtui_footer.text
