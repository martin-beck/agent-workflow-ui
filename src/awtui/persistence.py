"""Canonical, revision-bound session snapshots used by both renderers.

The UI view model is deliberately not itself a persistence layer.  This
module provides the small adapter shared by the TUI and Qt renderer so a
visible ``saved`` state always corresponds to an acknowledged transport
event (or to an explicitly supplied local event sink in standalone mode).
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Callable


def session_snapshot(interaction: Any) -> dict[str, Any]:
    """Return a deterministic, public snapshot of the complete batch."""
    responses: dict[str, Any] = {}
    for point_id in sorted(interaction.responses):
        response = interaction.responses[point_id]
        value: dict[str, Any] = {
            "point_id": response.point_id,
            "disposition": response.disposition,
            "selected": response.selected,
            "user_proposal_evaluated": response.user_proposal_evaluated,
        }
        if response.user_proposal is not None:
            value["user_proposal"] = {
                "label": response.user_proposal.label,
                "rationale": response.user_proposal.rationale,
                "confidence": response.user_proposal.confidence,
                "tradeoffs": response.user_proposal.tradeoffs,
            }
        responses[point_id] = value
    points = []
    for point in interaction.packet.points:
        points.append({
            "point_id": point.point_id,
            "proposals": [{
                "label": p.label, "rationale": p.rationale,
                "confidence": p.confidence, "tradeoffs": p.tradeoffs,
            } for p in point.proposals],
        })
    unresolved = [p.point_id for p in interaction.packet.points if p.point_id not in responses]
    return {
        "schema_version": 1,
        "ar_id": interaction.packet.ar_id,
        "task_revision": interaction.packet.task_revision,
        "responses": responses,
        "points": points,
        "unresolved": unresolved,
    }


def snapshot_digest(snapshot: dict[str, Any]) -> str:
    encoded = json.dumps(snapshot, sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


class DurableSessionPersistence:
    """Shared save adapter; state changes only after durable acknowledgement."""

    def __init__(self, interaction: Any, *, transport: Any = None,
                 on_event: Callable[[dict[str, Any]], Any] | None = None):
        self.interaction = interaction
        self.transport = transport
        self.on_event = on_event
        self._last_digest: str | None = None

    def save(self, *, exit: bool = False) -> Any:
        snapshot = session_snapshot(self.interaction)
        digest = snapshot_digest(snapshot)
        # A repeated save of identical state is already durable and must not
        # append a duplicate journal record.
        if self.interaction.saved and self._last_digest == digest:
            return None
        payload = {"snapshot": snapshot, "snapshot_digest": digest, "exit": exit}
        acknowledgement = None
        if self.transport is not None:
            acknowledgement = self.transport.submit("save", **payload)
            if not acknowledgement.accepted:
                return acknowledgement
        event = {"event_type": "save", "payload": payload}
        if self.on_event is not None:
            self.on_event(event)
        self._last_digest = digest
        self.interaction.saved = True
        return acknowledgement or event

