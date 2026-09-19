#!/usr/bin/env python3
"""Capture one real Qt GUI screenshot for every documented scenario.

The screenshots use the same Markdown and decision packet as the live replay;
they are intentionally generated from the corpus so the documentation cannot
drift to a single hand-written demo.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "src"))


def capture(root: Path = ROOT, output_dir: Path | None = None) -> list[Path]:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from awtui.gui import build_gui_application
    from awtui.scenario_helper import demo_decisions

    corpus = json.loads((root / "scenarios/corpus.json").read_text(encoding="utf-8"))
    out = output_dir or root / "docs/gui-screenshots"
    out.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for scenario in corpus["scenarios"]:
        design = (f"# Design document\n\n## Design boundary\n{scenario['title']} design boundary.\n\n"
                  "## Validation path\nIndependent evidence is recorded before implementation.")
        workplan = (f"# Workplan\n\n## Rollout step\n{scenario['title']} rollout step.\n\n"
                    "## Verification\nThe selected decision is verified by the coordinator.")
        window = build_gui_application(
            design_document=design,
            workplan=workplan,
            decisions=demo_decisions(scenario),
        )
        window.window.resize(1440, 900)
        window.window.show()
        window.app.processEvents()
        target = out / f"{scenario['id']}.png"
        if not window.window.grab().save(str(target), "PNG"):
            raise RuntimeError(f"could not save GUI screenshot: {target}")
        window.close_without_prompt()
        window.app.processEvents()
        paths.append(target)
    return paths


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=None)
    args = parser.parse_args()
    paths = capture(ROOT, args.output_dir)
    print(f"captured {len(paths)} GUI scenario screenshots")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
