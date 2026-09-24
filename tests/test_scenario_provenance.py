from __future__ import annotations

import json
from pathlib import Path

from tools import scenario_provenance


ROOT = Path(__file__).parents[1]


def test_manifest_is_fresh_and_public_safe() -> None:
    assert scenario_provenance.check(ROOT) == []
    manifest = json.loads((ROOT / "artifacts/scenario-provenance.json").read_text())
    serialized = json.dumps(manifest)
    assert "/home/" not in serialized
    assert "private" not in serialized.lower()
    assert "transcript" not in serialized.lower()
    assert manifest["source_release"]["project"] == "agent-workflow-ui"
    assert manifest["input"]["path"] == "scenarios/corpus.json"
    results = json.loads((ROOT / "artifacts/scenario-results.json").read_text())
    assert len(manifest["artifacts"]) == 1 + 3 * len(results["results"])


def test_renderer_digest_is_ordered_and_stable() -> None:
    first = scenario_provenance.build(ROOT)["renderer"]["version"]
    second = scenario_provenance.build(ROOT)["renderer"]["version"]
    assert first == second
    assert first.startswith("sha256:")
    paths = scenario_provenance.build(ROOT)["renderer"]["files"]
    assert [entry["path"] for entry in paths] == sorted(entry["path"] for entry in paths)
