"""Coordinator/TUI bridge: explicit trigger and AR persistence projection."""
from __future__ import annotations

from typing import Any

BRIDGE_VERSION = "1.0"


def interaction_state(*, request_id: str, decision_class: str, status: str = "pending", deadline: str | None = None) -> dict[str, Any]:
    """Return the Coordinator-owned AR metadata that requests human input."""
    if not request_id.startswith("AWG-"):
        raise ValueError("decision_request_ref must be an AWG request id")
    if status not in {"pending", "in_progress", "resolved", "superseded"}:
        raise ValueError("invalid decision status")
    value: dict[str, Any] = {"schema_version": BRIDGE_VERSION, "interaction_required": status in {"pending", "in_progress"}, "decision_status": status, "decision_request_ref": request_id, "decision_class": decision_class}
    if deadline is not None:
        value["oracle_deadline"] = deadline
    return value


def apply_tui_response(ar: dict[str, Any], event: dict[str, Any], *, response_event_ref: str) -> dict[str, Any]:
    """Project an accepted TUI event into an AR metadata update.

    The returned copy is suitable for persistence in the AR front-matter. It
    never marks implementation complete; it records only human disposition,
    selected proposal, and the resulting description/specification text.
    """
    if event.get("event_type") not in {"select", "add-proposal", "clarify", "reject", "request-more-evidence", "reopen", "reconciled"}:
        raise ValueError("event is not a decision response")
    payload = event.get("payload") or {}
    updated = dict(ar)
    bridge = dict(ar.get("interaction", {}))
    disposition = payload.get("disposition", event["event_type"])
    bridge.update({"schema_version": BRIDGE_VERSION, "decision_status": "resolved" if disposition in {"select", "selected", "reconciled"} else "pending", "interaction_required": disposition not in {"select", "selected", "reconciled"}, "last_response_event": response_event_ref})
    updated["interaction"] = bridge
    updated["decision"] = {"request_id": payload.get("request_id", bridge.get("decision_request_ref")), "disposition": disposition, "selected_candidate": payload.get("selected_candidate"), "selected": payload.get("selected"), "user_proposal": payload.get("user_proposal")}
    if "description" in payload:
        updated["description"] = payload["description"]
    if "specification" in payload:
        updated["specification"] = payload["specification"]
    return updated


def tui_to_coordinator_response(request: dict[str, Any], event: dict[str, Any], *, description_append: str = "", ar_status: str = "open") -> dict[str, Any]:
    """Wrap a revision-bound TUI event as the Coordinator persistence command."""
    if request.get("kind") != "coordinator-tui-request":
        raise ValueError("not a Coordinator/TUI request")
    if event.get("session_id") != request.get("session_id"):
        raise ValueError("response session does not match request")
    payload = event.get("payload") or {}
    disposition = payload.get("disposition", event.get("event_type"))
    resolved = disposition in {"select", "selected", "rejected", "reject", "reconciled"}
    return {
        "schema_version": BRIDGE_VERSION,
        "kind": "coordinator-tui-response",
        "project_id": request["project_id"],
        "ar_id": request["ar"]["ar_id"],
        "task_revision": request["ar"]["task_revision"],
        "decision_request_ref": request["interaction"]["decision_request_ref"],
        "event": {"session_id": event["session_id"], "sequence": event["sequence"], "event_type": event["event_type"], "payload": payload},
        "ar_update": {"decision_status": "resolved" if resolved else "pending", "ar_status": ar_status, "description_append": description_append, "specification_update": {"request_id": request["interaction"]["decision_request_ref"], "point_id": payload.get("point_id", request["interaction"]["decision_request_ref"]), "disposition": disposition, "selected_candidate": payload.get("selected_candidate"), "selected": payload.get("selected"), "user_proposal": payload.get("user_proposal")}},
    }
