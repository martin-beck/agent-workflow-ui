#!/usr/bin/env python3
"""Run one complete dynamic-token decision session through an SSH host."""
from __future__ import annotations

import argparse
import json
import os
import stat
import subprocess
import tempfile
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from awtui.shortcut import run
from awtui.tokens import TokenStore


def _run(argv: list[str]) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(argv, text=True, capture_output=True, check=False)
    if result.returncode:
        raise RuntimeError(f"command failed ({result.returncode}): {' '.join(argv)}\n{result.stderr}")
    return result


def qualify(*, ssh_host: str, remote_dir: str) -> dict[str, object]:
    if not ssh_host or not remote_dir.startswith("/") or ".." in Path(remote_dir).parts:
        raise ValueError("unsafe SSH alias or remote directory")
    root = remote_dir.rstrip("/")
    remote_request = f"{root}/request.json"
    remote_registry = f"{root}/.runtime/awui-tokens.json"
    remote_events = f"{root}/events.jsonl"
    request = {
        "schema_version": "1.0", "kind": "coordinator-tui-request",
        "project_id": "token-e2e", "session_id": "token-e2e-1",
        "ar": {"ar_id": "AR-0099", "task_revision": 4},
        "packet_digest": "sha256:" + "a" * 64,
        "decisions": [{"point_id": "p1"}, {"point_id": "p2"}],
    }
    with tempfile.TemporaryDirectory(prefix="awui-token-e2e-") as directory:
        local = Path(directory)
        request_file = local / "request.json"
        registry = local / "awui-tokens.json"
        config = local / "config.json"
        request_file.write_text(json.dumps(request), encoding="utf-8")
        token = TokenStore(registry).issue(
            project_id="token-e2e", session_id="token-e2e-1", task_revision=4,
            packet_digest=request["packet_digest"], session_file=remote_request,
            event_file=remote_events, ssh_host=ssh_host,
        )
        config.write_text(json.dumps({"schema_version": "1", "ssh_host": ssh_host, "remote_state_root": root}), encoding="utf-8")
        _run(["ssh", ssh_host, "mkdir", "-p", f"{root}/.runtime"])
        _run(["scp", str(request_file), f"{ssh_host}:{remote_request}"])
        _run(["scp", str(registry), f"{ssh_host}:{remote_registry}"])
        shim = local / "awui-live"
        shim.write_text(
            "#!/usr/bin/env python3\n"
            "import json, pathlib, sys\n"
            "a=sys.argv\n"
            "out=pathlib.Path(a[a.index('--output-json')+1])\n"
            "req=pathlib.Path(a[a.index('--session-file')+1])\n"
            "data=json.loads(req.read_text())\n"
            "event={'project_id':data['project_id'],'ar_id':data['ar']['ar_id'],"
            "'task_revision':data['ar']['task_revision'],'packet_digest':data['packet_digest'],"
            "'session_id':data['session_id'],'sequence':1,'event_type':'select',"
            "'payload':{'point_id':'p1','disposition':'select','selected_candidate':'candidate-a'}}\n"
            "out.write_text(json.dumps(event)+'\\n')\n",
            encoding="utf-8",
        )
        shim.chmod(shim.stat().st_mode | stat.S_IXUSR)
        old_path = os.environ.get("PATH", "")
        os.environ["PATH"] = f"{local}{os.pathsep}{old_path}"
        try:
            code = run(config=config, token=token, ssh_host=ssh_host)
        finally:
            os.environ["PATH"] = old_path
        if code != 0:
            raise RuntimeError(f"tokenized launcher returned {code}")
        fetched = json.loads(_run(["ssh", ssh_host, "cat", "--", remote_registry]).stdout)
        if fetched["tokens"][0]["status"] != "consumed":
            raise RuntimeError("successful remote batch did not consume its token")
        _run(["ssh", ssh_host, "test", "-s", remote_events])
        try:
            run(config=config, token=token, ssh_host=ssh_host)
        except SystemExit as error:
            if "no longer active" not in str(error):
                raise RuntimeError(f"unexpected replay rejection: {error}") from error
        else:
            raise RuntimeError("replayed token was accepted")
        _run(["ssh", ssh_host, "rm", "-rf", "--", root])
    return {"status": "resolved-and-consumed", "host": ssh_host, "decisions": 2}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ssh-host", required=True)
    parser.add_argument("--remote-dir", required=True)
    args = parser.parse_args(argv)
    print(json.dumps(qualify(ssh_host=args.ssh_host, remote_dir=args.remote_dir), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
