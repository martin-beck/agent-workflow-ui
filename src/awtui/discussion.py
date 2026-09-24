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
    # Coordinator checkpoint metadata.  These fields are optional so packets
    # from older bridge versions remain renderable.
    effective_from: str = ""
    effective_until: str = ""
    rollback_of: str = ""
    conflict_reason: str = ""

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

    def batch_status(self, responses: dict[str, "DecisionResponse"] | None = None) -> tuple[str, ...]:
        """Return stable per-point status lines for a batched live view."""
        responses = responses or {}
        lines = []
        for point in self.points:
            state = 'answered' if point.point_id in responses else 'unresolved'
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
    lines = [f"AR {packet.ar_id} revision {packet.task_revision} | batch {len(packet.points)} points"]
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
