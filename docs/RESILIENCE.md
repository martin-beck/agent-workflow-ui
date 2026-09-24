# Resilience qualification

The UI release pipeline runs a deterministic failure matrix through the same
revision-bound transport, Markdown renderer, journal, and atomic file adapters
used by live sessions. The matrix is intentionally public-safe: it contains
case names, aggregate outcomes, and cleanup/replay booleans, never requests,
proposals, transcripts, host paths, or credentials.

Run it locally with:

```sh
python tools/run_resilience_matrix.py --output-dir artifacts/resilience
```

The matrix covers fetch, render, input, save, upload, rename,
acknowledgement, resume, duplicate-event, stale-revision, network-flap,
crash/restart journal replay, and atomic-write failure behavior. A transient
transport fault may recover only after an acknowledged retry. Renderer,
input, save, rename, and stale-revision failures remain actionable and cannot
be reported as accepted. Atomic writes retain the previous result when a
write fails before publication.

CI uploads the aggregate `resilience-matrix.json` artifact. The artifact is a
qualification result, not an authority record; Coordinator persistence and
revision checks remain the source of truth for real sessions.
