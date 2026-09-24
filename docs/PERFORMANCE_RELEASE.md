# Performance and release qualification

AR-0104 adds a deterministic scale qualification for the renderer-neutral
paths shared by the Qt GUI and prompt-toolkit TUI. It uses a synthetic,
public-safe fixture of 256 decisions and 96,000-character Design and Work plan
documents. The fixture contains no project prompts, host names, credentials,
or private transcripts.

Run it locally from a checkout with the pinned dependencies:

```text
python3 tools/awui-benchmark --output artifacts/release-scale-benchmark.json
```

The release budgets are:

| Operation | Maximum latency | Scope |
| --- | ---: | --- |
| AR graph projection | 3.0 s | 256 decisions and two long Markdown documents |
| Rich Markdown rendering | 5.0 s | both 96,000-character documents |
| Anchor navigation | 2.0 s | all decision changes and occurrence lookup |
| Journal write | 3.0 s | one atomic checkpoint for the complete batch |
| Event handoff bookkeeping | 2.0 s | 256 sequence/idempotency records |
| Peak process allocation | 192 MiB | complete benchmark process |

The benchmark reports only timings, sizes, budgets, and pass/fail status. Any
latency or memory budget failure fails the release workflow. A green benchmark
does not claim a particular external terminal, display server, SSH host, or
unqualified architecture; those remain covered by the platform and remote
qualification jobs.

## Integrated release gates

The benchmark also checks that the current release contains evidence for the
operator-facing control surfaces:

- UX and keyboard/accessibility guidance;
- precise document anchors and synchronized navigation;
- privacy-safe audit controls;
- deterministic resilience qualification; and
- the compatibility and rollback boundary.

The compatibility report remains the source of truth for exact tag/commit
identity. For rollback, install the previous exact tag recorded by the
umbrella compatibility lock, restore the prior session artifact, and rerun
the same benchmark and release-contract tests before reopening a decision
session. No benchmark result authorizes bypassing revision, quality, or audit
gates.
