from __future__ import annotations

import json
from pathlib import Path

import pytest

from awtui import shortcut
from awtui.tokens import TokenStore


def test_shortcut_resolves_remote_registry_and_starts_one_batch(tmp_path, monkeypatch):
    registry = tmp_path / "registry.json"
    token = TokenStore(registry).issue(
        project_id="p", session_id="s", task_revision=4, packet_digest="d",
        session_file="/state/.runtime/request.json", event_file="/state/.runtime/events.jsonl", ssh_host="ai-ws",
    )
    calls = []
    monkeypatch.setattr(shortcut.subprocess, "run", lambda argv, **kwargs: type("R", (), {"returncode": 0, "stdout": registry.read_bytes()})())
    monkeypatch.setattr(shortcut, "connect", lambda **kwargs: calls.append(kwargs) or 0)
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"schema_version": "1", "ssh_host": "ai-ws", "remote_state_root": "/state"}))
    assert shortcut.run(config=config, token=token) == 0
    assert calls == [{"session_file": "/state/.runtime/request.json", "ssh_host": "ai-ws", "remote_event_file": "/state/.runtime/events.jsonl"}]


def test_shortcut_rejects_unsafe_host_and_root(tmp_path):
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"schema_version": "1", "ssh_host": "bad;host", "remote_state_root": "/state"}))
    with pytest.raises(ValueError):
        shortcut.run(config=config, token="ABCDEFGH")
