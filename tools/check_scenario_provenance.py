#!/usr/bin/env python3
"""Fail closed when scenario inputs, renderers, docs, or evidence drift."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))
from tools.scenario_provenance import check  # noqa: E402


if __name__ == "__main__":
    problems = check(Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parents[1])
    if problems:
        print("\n".join(problems), file=sys.stderr)
        raise SystemExit(1)
    print("scenario provenance is fresh")
