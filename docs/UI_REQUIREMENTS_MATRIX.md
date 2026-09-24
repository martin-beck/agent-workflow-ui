# Human-in-the-loop UI requirements

The live TUI must expose the complete AWG interaction contract, not only a
status screen. Each item below is implemented and tested by a dedicated AR.

| Requirement | Owner AR |
| --- | --- |
| Two panes, anchors, focus, resize, unresolved highlighting | AR-0018 |
| Ranked alternatives, confidence dimensions, rationale, assumptions, trade-offs, reversibility, rollback, impact, evidence gaps, dependent ARs | AR-0019 |
| Select, reject, clarify, request more evidence, add/evaluate proposal | AR-0020 |
| Batched independent points with per-point responses and coupling warnings | AR-0021 |
| Durable journal, safe exit, resume, re-ask, future request to AR mapping | AR-0006 / AR-0022 |
| Contradiction/impact view, targeted reopen, discussion-required loop | AR-0007 / AR-0023 |
| Anti-rubber-stamp framing and explicit authority/rejection affordances | AR-0024 |
| Live Coordinator/AWG/AWQ transport, event acknowledgements, stale rejection | AR-0008 / AR-0009 / AR-0010 / AR-0025 |
| Runtime PTY, interruption, recovery, accessibility, and release qualification | AR-0016 / AR-0017 / AR-0012 / AR-0013 |
| Toolkit-backed live input/output, deterministic test harness, and graceful fallback | AR-0026 |
| Revision-bound company dashboard rollup with bounded hierarchy drill-down | AR-0083 / AR-0084 |
| Board-instruction directive entry and AR persistence projection | AR-0085 |
| Paused-session resume cards and revision-bound resume events | AR-0086 |
| Rollback/conflict display with effective revision windows | AR-0087 |
| Scenario corpus, generated terminal/GUI captures, and UX documentation | AR-0088 |

The TUI never treats approval as implementation evidence, quality evidence as
user intent, or a reduced intervention rate as proof of autonomous safety.
