# Android service

The project-side service is started with TLS credentials and an isolated state
file:

```text
awui-android-service --state .runtime/android-service.json \
  --host 0.0.0.0 --port 8765 --certfile service.crt --keyfile service.key
```

The service exposes `/v1/health`, `/v1/register`, and `/v1/events`. It stores
only device public keys, credential digests, capabilities, revocation state,
last sequence, and redacted event envelopes. Bootstrap redemption is atomic and
one-time. Every event is checked against project, session, task revision,
packet digest, device identity, and sequence before acknowledgement.

Production deployments should place this adapter behind the project’s normal
authenticated reverse proxy and firewall. The development adapter refuses to
start without a certificate and key; it does not claim public-network safety
by itself.
