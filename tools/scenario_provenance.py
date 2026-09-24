#!/usr/bin/env python3
"""Build and validate the public provenance manifest for scenario evidence.

The manifest deliberately contains only repository-relative paths, hashes,
tool versions, and the public generation command.  It never records a host
path, environment variable, prompt, or transcript.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parents[1]
MANIFEST = Path("artifacts/scenario-provenance.json")
_VERSION = re.compile(r'^version\s*=\s*"([^"]+)"', re.MULTILINE)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _relative_files(root: Path, paths: list[Path]) -> list[Path]:
    return sorted({path.relative_to(root) for path in paths if path.is_file()})


def _renderer_files(root: Path) -> list[Path]:
    # Hash every Python renderer/helper module, plus the generators and the
    # corpus validator.  A renderer change therefore cannot silently leave
    # committed evidence looking fresh.
    paths = list((root / "src/awtui").rglob("*.py"))
    paths += [root / "tools" / name for name in (
        "run_scenarios.py", "run_gui_scenarios.py", "generate_scenario_docs.py",
        "check_scenario_docs.py", "validate_scenarios.py", "scenario_provenance.py",
    )]
    return _relative_files(root, paths)


def _file_record(root: Path, path: Path) -> dict[str, str]:
    return {"path": path.as_posix(), "sha256": _sha256(root / path)}


def _artifact_paths(root: Path) -> list[Path]:
    results = json.loads((root / "artifacts/scenario-results.json").read_text(encoding="utf-8"))
    paths = [Path("docs/SCENARIOS.md")]
    for result in results.get("results", []):
        paths.extend(Path(result[key]) for key in ("screenshot", "recording", "gui_screenshot"))
    return sorted(set(paths))


def build(root: Path = ROOT) -> dict[str, Any]:
    pyproject = (root / "pyproject.toml").read_text(encoding="utf-8")
    match = _VERSION.search(pyproject)
    if not match:
        raise ValueError("pyproject.toml has no public package version")
    input_path = Path("scenarios/corpus.json")
    renderer_paths = _renderer_files(root)
    renderer_digest = hashlib.sha256(
        b"".join(path.as_posix().encode() + b"\0" + (root / path).read_bytes() for path in renderer_paths)
    ).hexdigest()
    artifact_paths = _artifact_paths(root)
    missing = [path.as_posix() for path in artifact_paths if not (root / path).is_file()]
    if missing:
        raise ValueError("missing generated artifacts: " + ", ".join(missing))
    return {
        "schema_version": 1,
        "source_release": {"project": "agent-workflow-ui", "version": match.group(1)},
        "input": _file_record(root, input_path),
        "renderer": {
            "version": "sha256:" + renderer_digest,
            "files": [_file_record(root, path) for path in renderer_paths],
        },
        "generation_command": "python tools/run_scenarios.py && python tools/run_gui_scenarios.py --output-dir artifacts/gui-screenshots && python tools/generate_scenario_docs.py && python tools/scenario_provenance.py --write",
        "artifacts": [_file_record(root, path) for path in artifact_paths],
    }


def write(root: Path = ROOT) -> dict[str, Any]:
    manifest = build(root)
    target = root / MANIFEST
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def check(root: Path = ROOT) -> list[str]:
    target = root / MANIFEST
    if not target.is_file():
        return [f"missing {MANIFEST.as_posix()}"]
    try:
        actual = json.loads(target.read_text(encoding="utf-8"))
        expected = build(root)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        return [f"invalid scenario provenance: {error}"]
    if actual != expected:
        return ["scenario provenance manifest is stale; regenerate scenario artifacts and manifest"]
    errors: list[str] = []
    for record in actual.get("artifacts", []):
        path = root / record.get("path", "")
        if not path.is_file():
            errors.append(f"manifest artifact is missing: {record.get('path')}")
        elif _sha256(path) != record.get("sha256"):
            errors.append(f"manifest hash does not match: {record.get('path')}")
    return errors


if __name__ == "__main__":
    import argparse
    import sys

    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    if args.write:
        write()
        print(f"wrote {MANIFEST.as_posix()}")
    else:
        problems = check()
        if problems:
            print("\n".join(problems))
            raise SystemExit(1)
        print("scenario provenance is fresh")
