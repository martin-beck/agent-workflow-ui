"""Stable, occurrence-aware document anchors shared by the GUI and TUI.

Text is intentionally retained in the packet for older bridges, but a phrase
alone is not an address: the same phrase may occur several times in a
design.  These helpers resolve an anchor by occurrence and return offsets in
the rendered document so both frontends use the same target.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ResolvedAnchor:
    text: str
    start: int
    end: int
    occurrence: int = 0


def find_occurrences(document: str, phrase: str) -> tuple[ResolvedAnchor, ...]:
    """Return every non-overlapping, case-insensitive occurrence of phrase."""
    if not isinstance(document, str) or not isinstance(phrase, str) or not phrase:
        return ()
    folded, needle = document.casefold(), phrase.casefold()
    result: list[ResolvedAnchor] = []
    cursor = 0
    while True:
        start = folded.find(needle, cursor)
        if start < 0:
            break
        result.append(ResolvedAnchor(document[start:start + len(phrase)], start, start + len(phrase), len(result)))
        cursor = start + len(phrase)
    return tuple(result)


def resolve_occurrence(document: str, phrase: str, occurrence: int = 0) -> ResolvedAnchor | None:
    matches = find_occurrences(document, phrase)
    if not matches:
        return None
    return matches[max(0, min(int(occurrence), len(matches) - 1))]


def anchor_metadata(document: str, *, anchor: str, phrase: str, occurrence: int = 0) -> dict[str, object]:
    """Create serializable range metadata for a rendered document."""
    match = resolve_occurrence(document, phrase, occurrence)
    if match is None:
        raise ValueError(f"anchor {anchor!r} text is absent from its source document")
    return {"anchor": anchor, "text": phrase, "occurrence": match.occurrence,
            "start": match.start, "end": match.end}
