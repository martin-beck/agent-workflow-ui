# Agent Workflow UI v0.6.5 compatibility release

This patch release adds `awui-android-pair`, which health-checks the configured
HTTPS service, starts it when absent with deployment-supplied TLS credentials,
waits for `/v1/health`, and then creates the one-time Android pairing QR.
Healthy existing services are reused; no private key or TLS key is placed in
the QR payload.

The SSH rendezvous remains configurable with `--ssh-host` / `AWUI_SSH_HOST`.
`node26` remains an opt-in qualification fixture only.

Required release checks include the full Python suite, hosted Android
`x86_64`/`arm64-v8a` builds, Windows qualification, scenario replay, and the
release-contract workflow.
