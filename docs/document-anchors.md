# Document anchors and synchronized navigation

Decision packets carry the Markdown phrase for compatibility and an optional
`highlight_ranges` map for precision:

```json
"highlight_ranges": {
  "design": [{
    "anchor": "allocator-boundary",
    "text": "Choose the allocator boundary.",
    "occurrence": 1,
    "start": 148,
    "end": 176
  }]
}
```

`occurrence` is zero-based and is resolved against the rendered document,
case-insensitively. `start` and `end` are provenance metadata; frontends
re-resolve the occurrence after Markdown rendering so wrapping and terminal
width changes cannot move the target to a different repeated phrase.

The TUI paints every range for the active decision and moves the document
viewport to the first range. Page Up/Page Down changes the viewport without
changing the selected ranges. The GUI uses the same ranges for its
`QTextEdit` selections and scrolls to the first range. Switching decisions
re-resolves the ranges in both document panes, so a design phrase and a
different work-plan phrase never produce a false “highlight not found”.

AR graph projection emits this metadata automatically. Integrations that
construct packets directly may omit it and retain legacy first-occurrence
behavior, or provide the map explicitly when phrases repeat.
