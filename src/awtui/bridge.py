"""Coordinator/TUI bridge: explicit trigger and AR persistence projection."""
from __future__ import annotations

from typing import Any

from .dashboard import BoardRequest, RollupPage

BRIDGE_VERSION = "1.0"


def board_request(*, project_id: str, ar_id: str, task_revision: int,
                  packet_digest: str, rollup_revision: int,
                  pages: list[dict[str, Any]], hierarchy: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Build the revision-bound company dashboard request envelope."""
    value = BoardRequest.from_dict({"schema_version": "1.0", "kind": "coordinator-board-request",
        "project_id": project_id, "ar_id": ar_id, "task_revision": task_revision,
        "packet_digest": packet_digest, "rollup_revision": rollup_revision,
        "pages": pages, "hierarchy": hierarchy or []})
    return value.as_dict()


def board_response(request: dict[str, Any], *, page_id: str) -> dict[str, Any]:
    """Build a navigation response bound to the exact rollup snapshot."""
    parsed = BoardRequest.from_dict(request)
    if page_id not in {page.page_id for page in parsed.pages}:
        raise ValueError("board response selects an unknown page")
    return {"schema_version": BRIDGE_VERSION, "kind": "coordinator-board-response",
            "project_id": parsed.project_id, "ar_id": parsed.ar_id,
            "task_revision": parsed.task_revision, "packet_digest": parsed.packet_digest,
            "rollup_revision": parsed.rollup_revision, "page_id": page_id}


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
    if event.get("event_type") not in {"directive", "select", "add-proposal", "clarify", "reject", "request-more-evidence", "save", "reopen", "reconciled"}:
        raise ValueError("event is not a decision response")
    payload = event.get("payload") or {}
    if event.get("event_type") == "directive" and (not isinstance(payload.get("directive"), str) or not payload["directive"].strip()):
        raise ValueError("directive response requires non-empty directive text")
    updated = dict(ar)
    bridge = dict(ar.get("interaction", {}))
    disposition = payload.get("disposition", event["event_type"])
    if event.get("event_type") == "save":
        snapshot = payload.get("snapshot")
        if not isinstance(snapshot, dict) or payload.get("snapshot_digest", "").split(":", 1)[0] != "sha256":
            raise ValueError("save response requires a revision-bound snapshot")
        updated["decision_session"] = {"snapshot": snapshot, "snapshot_digest": payload["snapshot_digest"], "exit": bool(payload.get("exit", False))}
    resolved = disposition in {"directive", "select", "selected", "reconciled"}
    bridge.update({"schema_version": BRIDGE_VERSION, "decision_status": "resolved" if resolved else "pending", "interaction_required": not resolved, "last_response_event": response_event_ref})
    updated["interaction"] = bridge
    updated["decision"] = {"request_id": payload.get("request_id", bridge.get("decision_request_ref")), "disposition": disposition, "selected_candidate": payload.get("selected_candidate"), "selected": payload.get("selected"), "user_proposal": payload.get("user_proposal")}
    if disposition == "directive":
        updated["directive"] = payload["directive"].strip()
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
    resolved = disposition in {"directive", "select", "selected", "rejected", "reject", "reconciled"}
    return {
        "schema_version": BRIDGE_VERSION,
        "kind": "coordinator-tui-response",
        "project_id": request["project_id"],
        "ar_id": request["ar"]["ar_id"],
        "task_revision": request["ar"]["task_revision"],
        "decision_request_ref": request["interaction"]["decision_request_ref"],
        "event": {"session_id": event["session_id"], "sequence": event["sequence"], "event_type": event["event_type"], "payload": payload},
        "ar_update": {"decision_status": "resolved" if resolved else "pending", "ar_status": ar_status, "description_append": description_append, "specification_update": {"request_id": request["interaction"]["decision_request_ref"], "point_id": payload.get("point_id", request["interaction"]["decision_request_ref"]), "disposition": disposition, "directive": payload.get("directive"), "selected_candidate": payload.get("selected_candidate"), "selected": payload.get("selected"), "user_proposal": payload.get("user_proposal")}},
    }
