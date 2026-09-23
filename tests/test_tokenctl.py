from __future__ import annotations

import json

from awtui.tokenctl import main
from awtui.tokens import TokenStore


def test_tokenctl_issues_and_consumes_dynamic_batch(tmp_path, capsys):
    registry = tmp_path / "tokens.json"
    request = tmp_path / "request.json"
    request.write_text(json.dumps({
        "project_id": "demo", "session_id": "s1",
        "ar": {"task_revision": 3},
        "packet_digest": "sha256:" + "a" * 64,
        "decisions": [{"point_id": "p1"}],
    }), encoding="utf-8")
    assert main(["issue", "--registry", str(registry), "--request", str(request),
                 "--session-file", "/state/request.json", "--event-file",
                 "/state/events.jsonl", "--ssh-host", "ai-ws"]) == 0
    token = capsys.readouterr().out.strip()
    assert main(["consume", "--registry", str(registry), "--token", token,
                 "--ssh-host", "ai-ws"]) == 0
    assert TokenStore(registry)._read()[0]["status"] == "consumed"


def test_tokenctl_publish_writes_authority_request_before_returning_token(tmp_path, capsys):
    registry = tmp_path / ".runtime" / "tokens.json"
    source = tmp_path / "source.json"
    target = tmp_path / ".runtime" / "request.json"
    source.write_text(json.dumps({
        "project_id": "demo", "session_id": "s2", "ar": {"task_revision": 4},
        "packet_digest": "sha256:" + "e" * 64, "decisions": [{"point_id": "p1"}],
    }), encoding="utf-8")
    assert main(["publish", "--registry", str(registry), "--request", str(source),
                 "--session-file", str(target), "--event-file", "/state/events.jsonl",
                 "--ssh-host", "ai-ws"]) == 0
    token = capsys.readouterr().out.strip()
    assert target.exists()
    assert TokenStore(registry).resolve(token, ssh_host="ai-ws").session_id == "s2"
