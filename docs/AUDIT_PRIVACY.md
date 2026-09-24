# Audit, privacy, and operator controls

Every live decision session has a revision-bound operator audit view.  Press
`v` in the TUI or choose **Audit** in the GUI to inspect accepted and rejected
operations, sequence numbers, retention limits, and the active AR revision.

The audit stream is intentionally not the decision journal.  It stores only
operational metadata and a digest of an event payload.  Proposal wording,
Markdown documents, prompts, host paths, credentials, and event payloads are
never copied into an audit export.  `AuditControl.export()` is the only export
path and always returns a redacted, revision-bound `awui-audit-export`; asking
for an unredacted export fails closed.

Before a support or operator action is submitted, `dry_run()` can validate the
event type, sequence, and session context without recording or sending an
event.  The Coordinator transport remains authoritative: an audit entry can
report a rejected event, but it cannot accept, persist, or advance one.

Retention is bounded by entry count and may additionally be bounded by age.
The default limit is 500 entries per session.  This keeps diagnostics useful
without turning long-running sessions into a second copy of private history.
