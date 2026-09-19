# Short decision-batch token contract

AR-0073 defines the opaque token used by the compact `awui` launcher. A
Coordinator issues a token for one complete decision batch and stores the
registry in a private state directory. The registry stores only a SHA-256
digest of the token; the token itself is returned once to the user or agent.

Each token is bound to `project_id`, `session_id`, `task_revision`,
`packet_digest`, and the authoritative SSH alias. It also carries the session
and event-file paths, an issue time, an expiry time, and an `active`/`revoked`
status. Resolution fails closed for an unknown, malformed, expired, revoked,
cross-project, cross-host, or stale-revision token. The default lifetime is
15 minutes and the maximum is 24 hours.

Python callers use:

```python
from awtui.tokens import TokenStore, resolve_batch_token

token = TokenStore(".runtime/awui-tokens.json").issue(
    project_id="demo", session_id="session-1", task_revision=3,
    packet_digest="sha256:...", session_file="/state/request.json",
    event_file="/state/events.jsonl", ssh_host="ai-ws",
)
record = resolve_batch_token(".runtime/awui-tokens.json", token, ssh_host="ai-ws")
# record.session_file and record.event_file are the only files the launcher uses.
```

The launcher must use the resolved paths, not construct paths from the token.
The token registry is private (`0600`) and updates are atomic.
