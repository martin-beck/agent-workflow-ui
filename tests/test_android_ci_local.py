from pathlib import Path
import subprocess


ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "tools" / "android-ci-local.sh"


def test_local_android_runner_help_is_available():
    result = subprocess.run([str(SCRIPT), "--help"], capture_output=True, text=True)
    assert result.returncode == 0
    assert "--docker" in result.stdout
    assert "API-34" in result.stdout


def test_local_android_runner_rejects_unknown_options():
    result = subprocess.run([str(SCRIPT), "--not-a-mode"], capture_output=True, text=True)
    assert result.returncode == 2
    assert "unknown option" in result.stderr
