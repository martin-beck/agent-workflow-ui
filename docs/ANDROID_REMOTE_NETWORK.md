# Android remote/network qualification

`awtui.android_client.AndroidRemoteClient` is the transport-neutral client for
localhost, LAN, and SSH-forwarded HTTPS endpoints. The endpoint is supplied by
the registration QR payload; SSH host names and port forwarding are resolved by
the user's existing `ssh_config`, never by guessing or rewriting credentials.

The client keeps the batch's `session_id`, `task_revision`, and `packet_digest`
on every event. A reconnect therefore cannot submit an event to a different
decision revision, and retries remain idempotent through the service journal.
Run `pytest -q tests/test_android_remote_network.py` for the offline/reconnect
and local-network fixtures. Production deployments must use a trusted CA (the
test-only `verify_tls=False` option is never enabled by the Android app).
