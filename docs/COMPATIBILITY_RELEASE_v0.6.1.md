# Agent Workflow UI v0.6.1 compatibility release

This document is the operator-facing qualification record for the `v0.6.1`
release. The release is selected by an immutable tag and commit; consumers
must verify both before installing it. The Agent Workflow umbrella records the
same tag and commit in its compatibility lock.

## Qualification matrix

| Surface | Qualified evidence | Boundary |
| --- | --- | --- |
| Linux POSIX TUI | Hosted Linux scenario/replay checks from AR-0094; revision-bound batch, routing, and artifact checks | Requires Python >= 3.11 and a supported POSIX terminal; display-specific GUI behavior is not implied |
| Windows native x64 GUI/TUI | Hosted `windows-latest` native-x64 qualification from AR-0093; resize, document, proposal, save/exit, key dispatch, and journal paths | ARM64 is reported but unqualified because no authorized native ARM64 runner is enabled |
| Windows/POSIX remote bootstrap | Hosted Windows and Linux checks from AR-0094, including bounded reconnect and cleanup paths | A real external SSH host, display server, and credential consumption remain operator prerequisites and are not certified by CI |
| Scenario evidence | AR-0095 public provenance and freshness checks for recordings, screenshots, generated Markdown, and docs | Private prompts, host identifiers, credentials, and raw logs are never release evidence |

## Required release checks

Before publishing or consuming this release, run the release workflow and
verify the exact tag target:

```text
git fetch --tags https://github.com/martin-beck/agent-workflow-ui.git
git rev-parse v0.6.1^{commit}
git rev-parse HEAD
python3 -m pytest -q tests/test_release_contract.py tests/test_windows_qualification.py
```

The tag target, package version, compatibility report, scenario provenance,
and hosted qualification checks must all refer to the same source revision.
The release is not a claim of support for unqualified architectures,
unavailable external hosts, or arbitrary SSH/display environments.

## Scale and rollback qualification

The integrated release gate also runs the public-safe AR-0104 scale fixture:

```text
python3 tools/awui-benchmark --output artifacts/release-scale-benchmark.json
```

It must pass the published budgets in
[`PERFORMANCE_RELEASE.md`](PERFORMANCE_RELEASE.md) and the UX, navigation,
audit, and resilience evidence gates. If an upgrade must be rolled back,
restore the previous exact tag and its compatibility-lock commit, restore the
prior session artifact, and rerun the release-contract and scale checks before
resuming. A failed scale or evidence gate blocks publication.
