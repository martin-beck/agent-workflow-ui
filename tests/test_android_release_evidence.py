from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_android_workflow_publishes_bound_release_evidence() -> None:
    workflow = (ROOT / ".github/workflows/android.yml").read_text(encoding="utf-8")
    assert 'sha256sum "$apk"' in workflow
    assert "build-metadata.txt" in workflow
    assert "runtime-dependencies.txt" in workflow
    assert "SPDX-2.3" in workflow
    assert "*sbom.spdx.json" in workflow


def test_android_release_docs_describe_unsigned_compatibility_artifacts() -> None:
    readme = (ROOT / "android/README.md").read_text(encoding="utf-8")
    assert "SPDX 2.3 SBOM" in readme
    assert "No signing key" in readme
