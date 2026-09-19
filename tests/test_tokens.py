from datetime import datetime, timedelta, timezone
import json

import pytest

from awtui.tokens import TOKEN_LENGTH, TokenError, TokenStore, resolve_batch_token


NOW = datetime(2026, 9, 20, tzinfo=timezone.utc)


def issue(store, **overrides):
    values = {"project_id": "demo", "session_id": "s1", "task_revision": 3, "packet_digest": "sha256:" + "a" * 64, "session_file": "/state/request.json", "event_file": "/state/events.jsonl", "ssh_host": "ai-ws", "ttl_seconds": 60, "now": NOW}
    values.update(overrides)
    return store.issue(**values)


def test_token_is_short_opaque_and_resolves_complete_batch(tmp_path):
    store = TokenStore(tmp_path / "tokens.json")
    token = issue(store)
    assert len(token) == TOKEN_LENGTH
    assert token.isalnum() and token.upper() == token
    record = store.resolve(token, project_id="demo", session_id="s1", task_revision=3, packet_digest="sha256:" + "a" * 64, now=NOW)
    assert record.session_file == "/state/request.json"
    assert json.loads((tmp_path / "tokens.json").read_text())["tokens"][0]["token_digest"] != token


@pytest.mark.parametrize("field,value", [("project_id", "other"), ("session_id", "other"), ("task_revision", 4), ("packet_digest", "sha256:" + "b" * 64)])
def test_token_rejects_cross_context_or_stale_revision(tmp_path, field, value):
    store = TokenStore(tmp_path / "tokens.json")
    token = issue(store)
    context = {"project_id": "demo", "session_id": "s1", "task_revision": 3, "packet_digest": "sha256:" + "a" * 64, "now": NOW}
    context[field] = value
    with pytest.raises(TokenError, match="mismatch"):
        store.resolve(token, **context)


def test_token_expiry_and_revocation_are_fail_closed(tmp_path):
    store = TokenStore(tmp_path / "tokens.json")
    token = issue(store, ttl_seconds=1)
    with pytest.raises(TokenError, match="expired"):
        store.resolve(token, now=NOW + timedelta(seconds=1))
    token = issue(store)
    store.revoke(token)
    with pytest.raises(TokenError, match="no longer active"):
        store.resolve(token, now=NOW)


def test_launcher_resolver_binds_ssh_alias(tmp_path):
    store = TokenStore(tmp_path / "tokens.json")
    token = issue(store)
    assert resolve_batch_token(tmp_path / "tokens.json", token, ssh_host="ai-ws", now=NOW).event_file == "/state/events.jsonl"
    with pytest.raises(TokenError, match="ssh_host mismatch"):
        resolve_batch_token(tmp_path / "tokens.json", token, ssh_host="other", now=NOW)


def test_invalid_issue_inputs_and_unknown_tokens_are_rejected(tmp_path):
    store = TokenStore(tmp_path / "tokens.json")
    with pytest.raises(TokenError):
        issue(store, ttl_seconds=0)
    with pytest.raises(TokenError, match="unknown"):
        store.resolve("AAAAAAAA")
