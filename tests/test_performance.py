import json

from awtui.performance import DEFAULT_BUDGETS, FIXTURE_DECISIONS, FIXTURE_DOCUMENT_CHARS, run_benchmark


def test_release_scale_benchmark_has_explicit_fixture_and_passes():
    report = run_benchmark()
    assert report["schema_version"] == 1
    assert report["benchmark"] == "awui-release-scale-v1"
    assert report["fixture"] == {"decisions": FIXTURE_DECISIONS, "document_chars": FIXTURE_DOCUMENT_CHARS}
    assert report["budgets"] == DEFAULT_BUDGETS
    assert report["passed"] is True, json.dumps(report, indent=2)
    assert report["failures"] == []
    assert all(report["gates"].values())
    assert {item["name"] for item in report["measurements"]} == {
        "graph_projection", "markdown_render", "anchor_navigation", "journal_write", "event_handoff",
    }


def test_release_scale_budget_can_be_tightened_for_regression_checks():
    report = run_benchmark(budgets={"graph_seconds": 0.0})
    assert report["passed"] is False
    assert "graph_projection" in report["failures"]
