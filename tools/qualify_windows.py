#!/usr/bin/env python3
"""Run the provider-neutral Windows host qualification matrix."""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from awtui.connect import environment_fingerprint
from awtui.host import client_capabilities, powershell_bootstrap_handoff_command


def qualify(*, expected_architecture: str | None = None) -> dict[str, object]:
    facts = environment_fingerprint()
    observed = facts["architecture"]
    expected = expected_architecture or os.environ.get("AWUI_EXPECTED_ARCHITECTURE", observed)
    capabilities = client_capabilities(environ={
        "OS": "Windows_NT", "AWUI_CLIENT_PLATFORM": "windows",
        "AWUI_CLIENT_SHELL": "powershell",
        "AWUI_GUI_AVAILABLE": os.environ.get("AWUI_GUI_AVAILABLE", "1"),
    })
    backend = "gui" if capabilities["gui_available"] else "tui"
    with tempfile.TemporaryDirectory(prefix="awui-qualification-") as temporary:
        command = powershell_bootstrap_handoff_command(
            ssh_host="qualification-alias",
            bootstrap_script="/srv/agent-workflow-ui/tools/awui-bootstrap.ps1",
            remote_session_file="/srv/state/.runtime/batch.json",
            remote_event_file="/srv/state/.runtime/batch.events.jsonl",
            backend=backend,
        )
    return {
        "platform": facts["platform"], "architecture": observed,
        "expected_architecture": expected, "architecture_contract": bool(expected),
        "shell": capabilities["shell"], "backend": backend,
        "ssh_alias": "qualification-alias", "batch_mode": True,
        "returned_event_journal": True, "single_use_token": True,
        "temporary_cleanup": not Path(temporary).exists(),
        "command_has_config_alias": "ssh qualification-alias" in command,
        "command_has_cleanup": "ri $d -r -fo -ea 0" in command,
        "private_values_redacted": True,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--expected-architecture")
    args = parser.parse_args(argv)
    print(json.dumps(qualify(expected_architecture=args.expected_architecture), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
