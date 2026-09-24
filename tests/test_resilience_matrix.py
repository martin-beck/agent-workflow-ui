import json

import pytest

from awtui.resilience import FaultPlan, run_matrix


def test_fault_plan_is_deterministic_and_rejects_unknown_boundaries():
    plan = FaultPlan({"fetch": 1})
    with pytest.raises(RuntimeError, match="fetch"):
        plan.trip("fetch")
    plan.trip("fetch")
    with pytest.raises(ValueError, match="unknown"):
        FaultPlan({"secret": 1})


def test_public_resilience_matrix_covers_failure_boundaries(tmp_path):
    report = run_matrix(artifact_dir=tmp_path)
    assert report["schema_version"] == 1
    assert report["case_count"] >= 10
    assert report["all_cleanup_safe"] is True
    assert report["all_revision_bound"] is True
    assert report["markdown_adapter_exercised"] is True
    assert report["journal_resume_exercised"] is True
    assert {case["boundary"] for case in report["cases"]} >= {"fetch", "render", "input", "save", "upload", "rename", "ack", "resume"}
    assert all(set(case) == {"accepted", "boundary", "case_id", "cleanup_safe", "disposition", "fault", "outcome", "replayable"} for case in report["cases"])
    loaded = json.loads((tmp_path / "resilience-matrix.json").read_text())
    assert loaded == report


def test_matrix_does_not_mark_failed_action_as_accepted(tmp_path):
    report = run_matrix(artifact_dir=tmp_path)
    for case in report["cases"]:
        if case["outcome"] == "action-required":
            assert case["accepted"] is False
            assert case["disposition"] == "reopen-required"

