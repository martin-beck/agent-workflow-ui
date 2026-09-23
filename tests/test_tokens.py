from datetime import datetime, timedelta, timezone
import json

import pytest

from awtui.tokens import TOKEN_LENGTH, TokenError, TokenStore, issue_for_batch, publish_batch, resolve_batch_token


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


def test_consumption_is_single_use_and_records_completion(tmp_path):
    store = TokenStore(tmp_path / "tokens.json")
    token = issue(store)
    record = store.consume(token, ssh_host="ai-ws", now=NOW)
    assert record.status == "consumed"
    assert json.loads((tmp_path / "tokens.json").read_text())["tokens"][0]["status"] == "consumed"
    with pytest.raises(TokenError, match="no longer active"):
        store.consume(token, ssh_host="ai-ws", now=NOW)


def test_failed_or_cancelled_sessions_remain_retryable(tmp_path):
    store = TokenStore(tmp_path / "tokens.json")
    token = issue(store)
    assert store.resolve(token, ssh_host="ai-ws", now=NOW).status == "active"


def test_consumption_rejects_wrong_host_and_expiry(tmp_path):
    store = TokenStore(tmp_path / "tokens.json")
    token = issue(store, ttl_seconds=1)
    with pytest.raises(TokenError, match="ssh_host mismatch"):
        store.consume(token, ssh_host="other", now=NOW)
    with pytest.raises(TokenError, match="expired"):
        store.consume(token, ssh_host="ai-ws", now=NOW + timedelta(seconds=1))


def test_issue_for_batch_requires_complete_nonempty_packet(tmp_path):
    request = {
        "project_id": "demo", "session_id": "s1",
        "ar": {"task_revision": 3},
        "packet_digest": "sha256:" + "a" * 64,
        "decisions": [{"point_id": "p1"}],
    }
    token = issue_for_batch(tmp_path / "tokens.json", request,
                            session_file="/state/request.json",
                            event_file="/state/events.jsonl", ssh_host="ai-ws", now=NOW)
    assert len(token) == TOKEN_LENGTH
    with pytest.raises(TokenError, match="at least one"):
        issue_for_batch(tmp_path / "other.json", {**request, "decisions": []},
                        session_file="/state/request.json", event_file="/state/events.jsonl", ssh_host="ai-ws")


def test_publish_batch_durably_binds_request_and_registry(tmp_path):
    registry = tmp_path / ".runtime" / "awui-tokens.json"
    request_path = tmp_path / ".runtime" / "awui-session.json"
    request = {"project_id": "demo", "session_id": "batch-1", "ar": {"task_revision": 7},
               "packet_digest": "sha256:" + "b" * 64,
               "decisions": [{"point_id": "p1"}, {"point_id": "p2"}]}
    token = publish_batch(registry, request_path, request, session_file=str(request_path),
                          event_file=str(tmp_path / ".runtime" / "events.jsonl"),
                          ssh_host="ai-ws", now=NOW)
    assert json.loads(request_path.read_text()) == request
    assert resolve_batch_token(registry, token, ssh_host="ai-ws", now=NOW).session_id == "batch-1"
    assert oct(request_path.stat().st_mode & 0o777) == "0o600"
    assert oct(registry.stat().st_mode & 0o777) == "0o600"
    assert token not in registry.read_text()


def test_publication_journal_recovers_partial_authority_restart(tmp_path):
    registry = tmp_path / ".runtime" / "awui-tokens.json"
    request_path = tmp_path / ".runtime" / "awui-session.json"
    request = {"project_id": "demo", "session_id": "restart-1", "ar": {"task_revision": 2},
               "packet_digest": "sha256:" + "c" * 64, "decisions": [{"point_id": "p1"}]}
    token = publish_batch(registry, request_path, request, session_file=str(request_path),
                          event_file="/state/events.jsonl", ssh_host="ai-ws", now=NOW)
    journal = registry.with_name(f".{registry.name}.publication.json")
    journal.write_text(json.dumps({"schema_version": 1, "request_path": str(request_path),
                                   "registry_path": str(registry), "request": request,
                                   "registry": json.loads(registry.read_text())}), encoding="utf-8")
    request_path.unlink()
    assert TokenStore(registry).resolve(token, ssh_host="ai-ws", now=NOW).session_id == "restart-1"
    assert json.loads(request_path.read_text()) == request
    assert not journal.exists()


def test_publish_batch_rejects_relative_authority_paths(tmp_path):
    request = {"project_id": "demo", "session_id": "s1", "ar": {"task_revision": 1},
               "packet_digest": "sha256:" + "d" * 64, "decisions": [{"point_id": "p1"}]}
    with pytest.raises(TokenError, match="absolute"):
        publish_batch(tmp_path / "tokens.json", "request.json", request,
                      session_file="/state/request.json", event_file="/state/events.jsonl",
                      ssh_host="ai-ws")
