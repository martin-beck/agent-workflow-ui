#!/usr/bin/env python3
"""Check generated scenario documentation, screenshots, and live recordings."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))
from tools.scenario_provenance import check as check_provenance
SCREENSHOT_LINK = re.compile(r"^- \*\*Screenshot:\*\* \[open terminal capture\]\(([^)]+)\)$", re.MULTILINE)
RECORDING_LINK = re.compile(r"^- \*\*Live recording:\*\* \[play asciinema recording\]\(([^)]+)\)$", re.MULTILINE)
GUI_LINK = re.compile(r"^- \*\*GUI capture:\*\* \[open GUI screenshot\]\(([^)]+)\)$", re.MULTILINE)
SCENARIO_ID = re.compile(r"^- \*\*Scenario ID:\*\* `([^`]+)`$", re.MULTILINE)


def check(root: Path = ROOT) -> list[str]:
    corpus = json.loads((root / "scenarios/corpus.json").read_text(encoding="utf-8"))
    results = json.loads((root / "artifacts/scenario-results.json").read_text(encoding="utf-8"))
    docs_path = root / "docs/SCENARIOS.md"
    docs = docs_path.read_text(encoding="utf-8")
    expected_ids = [item["id"] for item in corpus["scenarios"]]
    result_by_id = {item["id"]: item for item in results.get("results", [])}
    errors: list[str] = []
    doc_ids = SCENARIO_ID.findall(docs)
    if doc_ids != expected_ids:
        errors.append("SCENARIOS.md scenario order/IDs do not match corpus")
    links = SCREENSHOT_LINK.findall(docs)
    expected_links = [f"screenshots/{item['id']}.svg" for item in corpus["scenarios"]]
    if links != expected_links:
        errors.append("SCENARIOS.md screenshot links do not match scenario IDs")
    if len(links) != len(expected_ids):
        errors.append("SCENARIOS.md does not contain exactly one screenshot per scenario")
    recording_links = RECORDING_LINK.findall(docs)
    expected_recordings = [f"recordings/{item['id']}.cast" for item in corpus["scenarios"]]
    if recording_links != expected_recordings:
        errors.append("SCENARIOS.md asciinema recording links do not match scenario IDs")
    gui_links = GUI_LINK.findall(docs)
    expected_gui = [f"gui-screenshots/{item['id']}.png" for item in corpus["scenarios"]]
    if gui_links != expected_gui:
        errors.append("SCENARIOS.md GUI screenshot links do not match scenario IDs")
    expected_files = {root / "docs" / link for link in expected_links}
    actual_files = set((root / "docs/screenshots").glob("*.svg"))
    if actual_files != expected_files:
        errors.append("docs/screenshots contains stale or missing SVG artifacts")
    expected_casts = {root / "docs" / link for link in expected_recordings}
    actual_casts = set((root / "docs/recordings").glob("*.cast"))
    if actual_casts != expected_casts:
        errors.append("docs/recordings contains stale or missing asciinema artifacts")
    expected_gui_files = {root / "docs" / link for link in expected_gui}
    actual_gui_files = set((root / "docs/gui-screenshots").glob("*.png"))
    if actual_gui_files != expected_gui_files:
        errors.append("docs/gui-screenshots contains stale or missing PNG artifacts")
    for cast in sorted(expected_casts):
        try:
            lines = cast.read_text(encoding="utf-8").splitlines()
            header = json.loads(lines[0])
            if header.get("version") != 2 or not any(json.loads(line)[1] == "o" for line in lines[1:]):
                errors.append(f"{cast.name}: invalid or empty asciinema v2 recording")
        except (OSError, IndexError, ValueError, TypeError, KeyError):
            errors.append(f"{cast.name}: cannot parse asciinema recording")
    for scenario_id, result in result_by_id.items():
        expected = root / result["screenshot"]
        if expected not in expected_files or not expected.is_file():
            errors.append(f"{scenario_id}: result screenshot is missing")
        recording = root / result.get("recording", "")
        if recording not in expected_casts or not recording.is_file():
            errors.append(f"{scenario_id}: result recording is missing")
        gui = root / result.get("gui_screenshot", f"docs/gui-screenshots/{scenario_id}.png")
        if gui not in expected_gui_files or not gui.is_file():
            errors.append(f"{scenario_id}: GUI screenshot is missing")
    if set(result_by_id) != set(expected_ids):
        errors.append("scenario-results IDs do not match corpus")
    if "../docs/" in docs or "file://" in docs:
        errors.append("SCENARIOS.md contains an invalid or non-portable link")
    errors.extend(check_provenance(root))
    return errors


if __name__ == "__main__":
    problems = check(Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT)
    if problems:
        print("\n".join(problems), file=sys.stderr)
        raise SystemExit(1)
    print("scenario documentation and artifacts valid")
