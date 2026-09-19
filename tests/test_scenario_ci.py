from pathlib import Path


def test_ci_replays_and_checks_generated_artifacts():
    workflow = (Path(__file__).parents[1] / ".github/workflows/scenarios.yml").read_text(encoding="utf-8")
    for command in ("validate_scenarios.py", "run_scenarios.py", "run_gui_scenarios.py", "run_connect_e2e.py", "gui-scenario-screenshots", "generate_scenario_docs.py", "check_scenario_docs.py", "asciinema --version", "asciinema play", "run_ssh_roundtrip.py", "GUI and TUI connector invocations", "openssh-server", "git diff --check", "git diff --exit-code"):
        assert command in workflow
    assert "permissions:" in workflow
    assert "cache: pip" in workflow
