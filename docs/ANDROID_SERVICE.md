# Android service

The project-side service is started with TLS credentials and an isolated state
file:

```text
awui-android-service --state .runtime/android-service.json \
  --host 0.0.0.0 --port 8765 --certfile service.crt --keyfile service.key
```

The service exposes these HTTPS endpoints:

* `GET /v1/health` is an unauthenticated liveness check.
* `POST /v1/register` accepts the scanned one-time QR payload and the phone's
  Keystore public key. It returns the device id and a credential; the QR never
  contains a credential.
* `GET /v1/session` requires `Authorization: Bearer <credential>` and
  `X-Device-Id`. It returns `{"status":"pending","batch":...}` for the
  latest coordinator-published batch, or `{"status":"idle","batch":null}`.
* `POST /v1/batches` is coordinator-only and requires the configured
  `X-Workflow-Service-Key`; it publishes the complete revision-bound batch,
  including Markdown documents and decisions.
* `POST /v1/events` requires the phone credential and routes one selected
  decision event back to the coordinator. The event is acknowledged only after
  its project, session, task revision, packet digest, device identity, and
  per-session sequence have been checked.

It stores only device public keys, credential digests, capabilities, revocation
state, per-session sequence/digest state, and redacted event envelopes.
Bootstrap redemption is atomic and one-time. Exact retransmission of an
already accepted event returns an idempotent acknowledgement; reusing a
sequence with different content is rejected.

Production deployments should place this adapter behind the project’s normal
authenticated reverse proxy and firewall. The development adapter refuses to
start without a certificate and key; it does not claim public-network safety
by itself.
