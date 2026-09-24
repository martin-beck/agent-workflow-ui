#!/usr/bin/env python3
"""Generate the public-safe deterministic AWUI resilience matrix."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))
from awtui.resilience import run_matrix


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/resilience"))
    args = parser.parse_args()
    report = run_matrix(artifact_dir=args.output_dir)
    print(json.dumps({key: report[key] for key in ("matrix", "case_count", "passed", "all_cleanup_safe", "all_revision_bound")}, sort_keys=True))
    return 0 if report["all_cleanup_safe"] and report["all_revision_bound"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
