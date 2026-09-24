"""AWG discussion packet projection used by the terminal renderer."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Proposal:
    label: str
    rationale: str
    confidence: float
    tradeoffs: str


@dataclass(frozen=True)
class PacketPoint:
    point_id: str
    anchor: str
    question: str
    proposals: tuple[Proposal, ...]
    implications: str
    evidence_gap: str = ""
    unresolved: bool = True
    # Text to bring into view when this decision is active.  It is optional
    # so packets produced by older Agent Workflow integrations remain valid.
    highlight: str = ""
    # Optional document-specific targets used when a human switches between
    # the design and work-plan panes.  Older packets continue to use
    # ``highlight`` as their fallback target.
    document_highlights: dict[str, str] = field(default_factory=dict)
    # Stable occurrence-aware ranges.  Each entry is a list because one
    # decision may refer to several source fragments in the same document.
    highlight_ranges: dict[str, tuple[dict[str, object], ...]] = field(default_factory=dict)
    # Coordinator checkpoint metadata.  These fields are optional so packets
    # from older bridge versions remain renderable.
    effective_from: str = ""
    effective_until: str = ""
    rollback_of: str = ""
    conflict_reason: str = ""
    # Batch workspace metadata.  These values are supplied by the Coordinator
    # projection and are descriptive only; responses remain revision-bound.
    ar_ref: str = ""
    group: str = ""
    depends_on: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    blocked_reason: str = ""

    def __post_init__(self):
        if not self.point_id or not self.anchor or len(self.proposals) < 2:
            raise ValueError("packet points require identity, anchor, and two proposals")
        if any(not 0 <= p.confidence <= 1 for p in self.proposals):
            raise ValueError("proposal confidence must be between zero and one")


@dataclass(frozen=True)
class DiscussionPacket:
    ar_id: str
    task_revision: int
    points: tuple[PacketPoint, ...]
    document: str = "design"

    def __post_init__(self):
        if not self.points or len({p.point_id for p in self.points}) != len(self.points):
            raise ValueError("packet requires unique discussion points")

    def active(self, index: int = 0) -> PacketPoint:
        return self.points[max(0, min(index, len(self.points) - 1))]

    def dependency_block(self, point: PacketPoint, responses: dict[str, "DecisionResponse"] | None = None) -> str:
        """Return a stable explanation when a point cannot yet be selected."""
        if point.blocked_reason:
            return point.blocked_reason
        responses = responses or {}
        missing = [dependency for dependency in point.depends_on if dependency not in responses or responses[dependency].disposition != "select"]
        return "waiting for: " + ", ".join(missing) if missing else ""

    def status(self, point: PacketPoint, responses: dict[str, "DecisionResponse"] | None = None) -> str:
        responses = responses or {}
        if point.point_id in responses:
            return getattr(responses[point.point_id], "disposition", "select")
        return "blocked" if self.dependency_block(point, responses) else "unresolved"

    def ordered_points(self, responses: dict[str, "DecisionResponse"] | None = None) -> tuple[PacketPoint, ...]:
        """Stable dependency-first order, retaining packet order for ties."""
        pending = list(self.points)
        result: list[PacketPoint] = []
        known = {point.point_id for point in pending}
        while pending:
            ready = [point for point in pending if all(dep not in known or dep in {item.point_id for item in result} for dep in point.depends_on)]
            if not ready:
                # Preserve all identities even for malformed/cyclic input; the
                # blocked explanation makes the problem actionable in the UI.
                result.extend(pending)
                break
            result.extend(ready)
            pending = [point for point in pending if point not in ready]
        return tuple(result)

    def filtered_points(self, responses: dict[str, "DecisionResponse"] | None = None, *, query: str = "", group: str = "", include_answered: bool = True) -> tuple[PacketPoint, ...]:
        responses = responses or {}
        query = query.casefold().strip()
        return tuple(point for point in self.ordered_points(responses) if
            (not group or point.group == group) and
            (include_answered or point.point_id not in responses) and
            (not query or query in " ".join((point.point_id, point.ar_ref, point.group, point.question, point.anchor)).casefold()))

    def groups(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(point.group for point in self.points if point.group))

    def summary(self, responses: dict[str, "DecisionResponse"] | None = None) -> dict[str, int]:
        responses = responses or {}
        counts = {key: 0 for key in ("total", "answered", "unresolved", "blocked", "clarify", "rejected")}
        counts["total"] = len(self.points)
        for point in self.points:
            state = self.status(point, responses)
            if state == "select": counts["answered"] += 1
            elif state == "clarify": counts["clarify"] += 1
            elif state == "reject": counts["rejected"] += 1
            elif state == "blocked": counts["blocked"] += 1
            else: counts["unresolved"] += 1
        return counts

    def batch_status(self, responses: dict[str, "DecisionResponse"] | None = None) -> tuple[str, ...]:
        """Return stable per-point status lines for a batched live view."""
        responses = responses or {}
        lines = []
        for point in self.points:
            state = self.status(point, responses)
            if state == "select":
                state = "answered"
            if point.rollback_of:
                state += f" | rollback of {point.rollback_of}"
            if point.conflict_reason:
                state += f" | conflict: {point.conflict_reason}"
            if point.effective_from or point.effective_until:
                window = f"{point.effective_from or 'open'}..{point.effective_until or 'open'}"
                state += f" | effective {window}"
            lines.append(f"{point.point_id}: {state}")
        return tuple(lines)


def render_batch(packet: DiscussionPacket, responses: dict[str, "DecisionResponse"] | None = None, *, coupling_warning: str = "") -> str:
    """Render an identity-preserving batch, including partial progress and coupling warnings."""
    summary = packet.summary(responses)
    lines = [f"AR {packet.ar_id} revision {packet.task_revision} | batch {len(packet.points)} points | progress {summary['answered']}/{summary['total']} answered"]
    if coupling_warning:
        lines.append(f"COUPLING WARNING: {coupling_warning}")
    lines.extend(packet.batch_status(responses))
    return "\n".join(lines)


def render_guardrails(*, authority: str, evidence_gap: str, limitations: str) -> str:
    """Show contestability context so approval cannot be mistaken for proof."""
    return "\n".join((
        f"authority: {authority}",
        f"evidence gap: {evidence_gap or 'none recorded'}",
        "affordances: reject | clarify | request-more-evidence",
        f"limitations: {limitations}",
        "decision is human intent; implementation, quality, and independent review remain separate evidence",
    ))


@dataclass(frozen=True)
class DecisionResponse:
    point_id: str
    disposition: str
    selected: str | None = None
    user_proposal: Proposal | None = None
    user_proposal_evaluated: bool = False

    def __post_init__(self):
        if self.disposition not in {"select", "reject", "clarify"}:
            raise ValueError("invalid decision disposition")
        if self.user_proposal is not None and not self.user_proposal_evaluated:
            raise ValueError("user proposal must be evaluated before selection")


class DecisionSession:
    def __init__(self, packet: DiscussionPacket):
        self.packet = packet
        self.responses: dict[str, DecisionResponse] = {}

    def respond(self, response: DecisionResponse) -> None:
        if response.point_id not in {point.point_id for point in self.packet.points}:
            raise ValueError("response point is not in packet")
        if response.disposition == "select" and not response.selected:
            raise ValueError("selection requires a proposal")
        self.responses[response.point_id] = response

    def unanswered(self) -> tuple[str, ...]:
        return tuple(point.point_id for point in self.packet.points if point.point_id not in self.responses)
