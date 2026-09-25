# Android bridge contract

The Android application is a renderer of the existing Coordinator/AWG decision
session. It does not own AR identity, task revisions, proposal authority, or
quality gates.

Registration starts on the project side and displays a short-lived QR payload.
The QR contains only the HTTPS service endpoint, project id, one-time bootstrap
id, expiry, and nonce. It contains no reusable credential or decision packet.
The phone generates a device key pair locally, shows the project identity and
requested capabilities, and sends the public key plus the QR fields to redeem
the bootstrap. The service returns a device id and session credential only
after one-time validation and explicit user consent.

Every Android request/event carries the project id, device id, session id,
task revision, packet digest, bridge version, and monotonically increasing
sequence. Coordinator rejects stale, replayed, cross-project, revoked, or
cross-device messages. The same canonical snapshot and journal rules used by
the TUI and GUI apply to Android.

The registration service must use HTTPS, bounded expiry, atomic redemption,
revocation, and redacted device metadata. External network/device operation is
qualified separately from local protocol tests.
