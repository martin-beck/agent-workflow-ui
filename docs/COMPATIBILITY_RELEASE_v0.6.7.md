# Agent Workflow UI v0.6.7 compatibility release

This release is the synchronized Android parity line for the Agent Workflow
decision surface. The Android development APK now consumes the same batch
session contract as the TUI and GUI: real design/work-plan Markdown, per-
decision highlights, structured proposals, selection/rejection/clarification,
evidence requests, own-proposal editing, reopen/revise, Save+Exit, and
fail-closed durable event persistence.

Pairing and reconnect validation is fail-closed. Public registration endpoints
must use HTTPS and valid rendezvous metadata. Plain HTTP is accepted only for
an authenticated loopback SSH tunnel; malformed hosts, ports, paths, queries,
fragments, and missing host-key fingerprints are rejected before registration.
The existing SSH tunnel and post-registration reconnect path remains supported.

The release is qualified by Android arm64-v8a and x86_64 builds, native
qualification, scenario replay/document refresh, and the ephemeral SSH
round-trip test. The emulator E2E job remains opt-in where no hosted emulator
is available; the hosted APK and instrumentation compilation gates are still
required.

Downstream consumers should pin the v0.6.7 tag (and its exact commit) together
with the matching Agent Workflow UI state/contract release.
