"""AWG decision adapter preserving explicit oracle authority."""
from __future__ import annotations

import hashlib
import json
from typing import Any

from .discussion import DecisionResponse


def request_digest(request: dict[str, Any]) -> str:
    """Return the canonical digest used to bind a Guidance request to a TUI session."""
    encoded = json.dumps(request, sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def request_to_tui(request: dict[str, Any], *, project_id: str, session_id: str, documents: dict[str, str] | None = None) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Adapt an AWG ``decision-request`` (schema 0.2) to TUI inputs.

    The original request is never rewritten. Candidate IDs are retained in
    each decision entry so the response adapter can return stable AWG identity
    instead of relying on a human-facing action label.
    """
    required = {"schema_version", "request_id", "context", "formal_check", "candidates"}
    if not required <= request.keys() or request.get("schema_version") != "0.2":
        raise ValueError("not an AWG decision-request schema 0.2 payload")
    awg_context = request["context"]
    if not isinstance(awg_context, dict) or not awg_context.get("task_ref"):
        raise ValueError("AWG request context.task_ref is required")
    context = {
        "project_id": project_id,
        "ar_id": awg_context["task_ref"],
        "task_revision": awg_context["task_revision"],
        "packet_digest": request_digest(request),
        "session_id": session_id,
        "contract_versions": {"awg": "0.2", "tui": "1", "awq": "1", "coordinator": "1"},
        "request_id": request["request_id"],
        "quality_refs": awg_context.get("quality_refs", []),
        "evidence_refs": awg_context.get("evidence_refs", []),
        "formal_check": request["formal_check"],
        "documents": documents or {},
    }
    decisions = [{
        "point_id": request["request_id"],
        "anchor": f"{request['decision_class']}:1",
        "question": awg_context["objective"],
        "highlights": {"design": awg_context["objective"], "workplan": awg_context["objective"]},
        "proposals": [{
            "candidate_id": candidate["candidate_id"],
            "label": candidate["action"],
            "rationale": candidate["rationale"],
            "confidence": candidate["confidence"],
            "tradeoffs": "; ".join(candidate["tradeoffs"]),
            "impact": candidate["impact"],
            "reversibility": candidate["reversibility"],
        } for candidate in request["candidates"]],
        "ar_id": awg_context["task_ref"],
        "group": request.get("decision_class", "decision"),
        "evidence_refs": list(awg_context.get("evidence_refs", [])),
        "depends_on": list(awg_context.get("depends_on", [])),
        "blocked_reason": str(awg_context.get("blocked_reason", "")),
        "helper": "Review impact, reversibility, assumptions, and downstream effects before selecting.",
        "evidence_gap": "; ".join(awg_context.get("evidence_refs", [])),
    }]
    return context, decisions


def requests_to_tui(
    requests: list[dict[str, Any]], *, project_id: str, session_id: str,
    documents: dict[str, str] | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Project a complete Coordinator batch into one revision-bound packet."""
    if not requests:
        raise ValueError("a TUI batch requires at least one AWG request")
    contexts: list[dict[str, Any]] = []
    points: list[dict[str, Any]] = []
    for request in requests:
        request = request.get("guidance_request", request)
        context, mapped = request_to_tui(request, project_id=project_id, session_id=session_id, documents=documents)
        contexts.append(context)
        for point in mapped:
            point["request_id"] = request["request_id"]
            points.append(point)
    first = contexts[0]
    first["batch_request_ids"] = [context["request_id"] for context in contexts]
    first["batch_ar_ids"] = [context["ar_id"] for context in contexts]
    return first, points


def envelope_requests_to_tui(
    envelope: dict[str, Any], *, project_id: str, session_id: str,
    documents: dict[str, str] | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Project every distinct request in a Coordinator envelope.

    A batch envelope historically duplicated the first request at top level
    while putting the remaining requests in ``batch``. Replacing the top
    level with ``batch`` silently dropped that first decision. Normalize by
    request ID, preserving order and avoiding duplicates.
    """
    candidates: list[dict[str, Any]] = []
    top = envelope.get("guidance_request")
    if isinstance(top, dict):
        candidates.append(top)
    batch = envelope.get("batch", [])
    if not isinstance(batch, list):
        raise ValueError("Coordinator batch must be an array")
    candidates.extend(
        entry.get("guidance_request", entry)
        for entry in batch
        if isinstance(entry, dict)
    )
    unique: list[dict[str, Any]] = []
    seen: set[str] = set()
    for request in candidates:
        request_id = request.get("request_id")
        if not isinstance(request_id, str) or not request_id:
            raise ValueError("every batch decision requires guidance_request.request_id")
        if request_id not in seen:
            seen.add(request_id)
            unique.append(request)
    if not unique:
        raise ValueError("Coordinator envelope contains no decision requests")
    return requests_to_tui(unique, project_id=project_id, session_id=session_id, documents=documents or envelope.get("documents"))


def tui_response_event(request: dict[str, Any], response: DecisionResponse, *, project_id: str, session_id: str, sequence: int) -> dict[str, Any]:
    """Project a TUI response into the canonical AWG event payload."""
    candidates = {candidate["action"]: candidate["candidate_id"] for candidate in request.get("candidates", [])}
    selected_candidate = candidates.get(response.selected) if response.selected else None
    payload = {"request_id": request["request_id"], "point_id": response.point_id, "disposition": response.disposition, "selected": response.selected, "selected_candidate": selected_candidate}
    if response.user_proposal is not None:
        payload["user_proposal"] = {"label": response.user_proposal.label, "rationale": response.user_proposal.rationale, "confidence": response.user_proposal.confidence, "tradeoffs": response.user_proposal.tradeoffs, "evaluated": response.user_proposal_evaluated}
    return {"project_id": project_id, "ar_id": request["context"]["task_ref"], "task_revision": request["context"]["task_revision"], "packet_digest": request_digest(request), "session_id": session_id, "sequence": sequence, "event_type": response.disposition, "payload": payload}


def decision_event(response: DecisionResponse, *, project_id: str, ar_id: str, task_revision: int, packet_digest: str, session_id: str, sequence: int) -> dict[str, Any]:
    """Project a TUI response into an AWG-owned event envelope."""
    payload: dict[str, Any] = {"point_id": response.point_id, "disposition": response.disposition, "selected": response.selected}
    if response.user_proposal is not None:
        payload["user_proposal"] = {"label": response.user_proposal.label, "evaluated": response.user_proposal_evaluated}
    return {"project_id": project_id, "ar_id": ar_id, "task_revision": task_revision, "packet_digest": packet_digest, "session_id": session_id, "sequence": sequence, "event_type": response.disposition, "payload": payload}
