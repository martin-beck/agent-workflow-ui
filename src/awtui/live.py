"""Full-screen live interaction for Agent Workflow discussion packets."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import sys
from prompt_toolkit.application import Application
from prompt_toolkit.styles import Style
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.keys import Keys
from prompt_toolkit.layout import ConditionalContainer, Dimension, HSplit, Layout, VSplit, DynamicContainer
from prompt_toolkit.application.current import get_app
from prompt_toolkit.filters import Condition
from prompt_toolkit.layout.processors import Processor, Transformation
from prompt_toolkit.widgets import Frame, TextArea
from .discussion import DiscussionPacket, DecisionResponse, PacketPoint, Proposal
from .markdown import render_markdown
from .transport import LiveSessionTransport, EventAcknowledgement

RECORDED_CONTROLS = {"\n": "select", "\r": "select", "r": "reject", "c": "clarify", "m": "request-more-evidence", "a": "add-proposal", "s": "safe-exit", "o": "reopen"}


class _ActiveHighlightProcessor(Processor):
    """Paint the selected decision's source phrase in the document pane.

    Rich supplies the document's terminal Markdown rendering, while this
    prompt-toolkit processor adds the interaction-specific visual state.  The
    source buffer remains plain text so scrolling, searching, and tests keep
    their normal offsets.
    """

    def __init__(self, phrase):
        self._phrase = phrase

    def apply_transformation(self, transformation_input):
        phrase = (self._phrase() or "").casefold()
        fragments = transformation_input.fragments
        if not phrase:
            return Transformation(fragments)
        line = "".join(text for _style, text in fragments)
        start = line.casefold().find(phrase)
        if start < 0:
            return Transformation(fragments)
        end = start + len(phrase)
        transformed = []
        offset = 0
        for style, text in fragments:
            fragment_end = offset + len(text)
            if fragment_end <= start or offset >= end:
                transformed.append((style, text))
            else:
                before = max(0, start - offset)
                after = max(0, fragment_end - end)
                if before:
                    transformed.append((style, text[:before]))
                match_end = len(text) - after if after else len(text)
                transformed.append(("bg:ansigreen fg:ansiwhite bold", text[before:match_end]))
                if after:
                    transformed.append((style, text[-after:]))
            offset = fragment_end
        return Transformation(transformed)

def dispatch_recorded_input(keys: str, on_event) -> list[str]:
    emitted = []
    for key in keys:
        if key in RECORDED_CONTROLS:
            emitted.append(RECORDED_CONTROLS[key]); on_event(RECORDED_CONTROLS[key])
        elif key in {"q", "\x1b"}:
            break
    return emitted

class LiveInteraction:
    """Mutable view-model for point/proposal selection and batch responses."""
    def __init__(self, packet: DiscussionPacket):
        self.packet, self.point_index, self.proposal_index = packet, 0, 0
        self.document_mode = packet.document
        self.responses: dict[str, DecisionResponse] = {}
        self.input_mode = False
        self.saved = False
        self.exit_confirm = False
        self.exit_confirm_index = 0
        self.editing_proposal_index: int | None = None
    @property
    def point(self): return self.packet.points[self.point_index]
    @property
    def proposal(self): return self.point.proposals[self.proposal_index]
    def active_highlight(self, document_mode: str | None = None) -> str:
        mode = document_mode or self.document_mode
        return self.point.document_highlights.get(mode, self.point.highlight or self.point.question)
    def move_point(self, delta: int):
        self.point_index = max(0, min(len(self.packet.points)-1, self.point_index + delta)); self.proposal_index = 0
    def move_proposal(self, delta: int):
        # A previously selected proposal is provisional until the user leaves
        # the current choice.  Moving left/right explicitly re-opens the
        # decision so every candidate is visible and the next Enter can
        # replace the prior answer.  This avoids navigating hidden candidates
        # while retaining the compact, selected-only view at rest.
        if delta and self.point.point_id in self.responses:
            del self.responses[self.point.point_id]
        self.proposal_index = max(0, min(len(self.point.proposals)-1, self.proposal_index + delta))
    def add_proposal(self, proposal: Proposal):
        proposals = list(self.point.proposals)
        if self.editing_proposal_index is not None:
            proposals[self.editing_proposal_index] = proposal
        else:
            proposals.append(proposal)
        point = replace(self.point, proposals=tuple(proposals))
        self.packet = replace(self.packet, points=self.packet.points[:self.point_index] + (point,) + self.packet.points[self.point_index+1:])
        self.responses.pop(self.point.point_id, None)
        self.proposal_index = len(point.proposals)-1
        if self.editing_proposal_index is not None:
            self.proposal_index = self.editing_proposal_index
            self.editing_proposal_index = None
        self.saved = False
        self._refresh_callback()
    def respond(self, disposition: str) -> DecisionResponse:
        user = self.proposal if self.proposal.label.startswith("User: ") else None
        response = DecisionResponse(self.point.point_id, disposition, self.proposal.label if disposition == "select" else None, user, user is not None)
        self.responses[self.point.point_id] = response
        self.saved = False
        self._refresh_callback()
        return response
    def render_points(self) -> str:
        lines = []
        selected = sum(response.disposition == "select" for response in self.responses.values())
        clarification = sum(response.disposition == "clarify" for response in self.responses.values())
        unresolved = len(self.packet.points) - selected
        save_state = "saved" if self.saved else "unsaved"
        lines.append(f"Overall: {selected}/{len(self.packet.points)} selected | {clarification} clarification requested | {unresolved} remaining | state {save_state}")
        lines.append("")
        for i, point in enumerate(self.packet.points):
            response = self.responses.get(point.point_id)
            user_proposal = next((proposal for proposal in point.proposals if proposal.label.startswith("User: ")), None)
            if response and response.disposition == "select":
                status = "✅ answered"
            elif response and response.disposition == "clarify":
                status = "⚠ clarification requested"
            elif response and response.disposition == "reject":
                status = "↩ rejected"
            else:
                status = "✎ proposal" if user_proposal else "unresolved"
            lines.append(f"{'▶' if i == self.point_index else ' '} {point.point_id} [{status}]  {point.anchor}")
        lines += ["", f"Decision: {self.point.question}"]
        response = self.responses.get(self.point.point_id)
        user_proposal = next((proposal for proposal in self.point.proposals if proposal.label.startswith("User: ")), None)
        if response and response.selected:
            visible = [(self.proposal_index, self.proposal)] if self.proposal.label == response.selected else [(index, proposal) for index, proposal in enumerate(self.point.proposals) if proposal.label == response.selected]
        elif user_proposal:
            visible = [(index, user_proposal) for index, proposal in enumerate(self.point.proposals) if proposal is user_proposal]
        else:
            visible = list(enumerate(self.point.proposals))
        lines += [f"  {'▶' if i == self.proposal_index else ' '} {p.label}" for i, p in visible]
        return "\n".join(lines)
    def render_helper(self) -> str:
        p = self.proposal
        response = self.responses.get(self.point.point_id)
        prefix = "Clarification requested: this decision is not answered.\n\n" if response and response.disposition == "clarify" else ""
        return prefix + f"Proposal {self.proposal_index + 1}/{len(self.point.proposals)}: {p.label}\n\nRationale: {p.rationale}\nConfidence: {p.confidence:.2f}\nTrade-offs: {p.tradeoffs}\n\nAnchor: {self.point.anchor}\nHighlight: {self.active_highlight()}\nImplications: {self.point.implications}\nEvidence gap: {self.point.evidence_gap or 'none recorded'}\nHuman intent is separate from implementation and quality evidence."

    def exit_requirements(self) -> list[str]:
        missing = [point.point_id for point in self.packet.points if self.responses.get(point.point_id, None) is None or self.responses[point.point_id].disposition != "select"]
        requirements = []
        if missing:
            requirements.append("select a proposal for: " + ", ".join(missing))
        if not self.saved:
            requirements.append("save the current decision state (s)")
        return requirements

    def switch_document(self):
        self.document_mode = "workplan" if self.document_mode != "workplan" else "design"
        self._manual_document_switch = True
        self._refresh_callback()

    # Compatibility names used by scenario drivers and a convenient public UI API.
    def move(self, delta: int):
        self.move_point(delta)
        self._refresh_callback()

    def next_proposal(self, delta: int):
        self.move_proposal(delta)
        self._refresh_callback()

    def _refresh_callback(self):
        if hasattr(self, "_refresh"): self._refresh()

    def begin_edit_proposal(self) -> bool:
        """Load the current user proposal into the four-field editor."""
        if not self.proposal.label.startswith("User: "):
            return False
        self.editing_proposal_index = self.proposal_index
        return True

def _default_packet(document: str, points: str) -> DiscussionPacket:
    p = Proposal("Review in context", "Inspect the highlighted material", .7, "Requires human review")
    q = Proposal("Request evidence", "Ask for evidence before deciding", .8, "Delays the decision")
    return DiscussionPacket("interactive", 1, (PacketPoint("point-1", "document:1", points, (p, q), "Review downstream effects", "Evidence is synthetic", highlight=points),), document=document)

def _packet_from_decisions(decisions, design_document: str, workplan: str) -> DiscussionPacket:
    points = []
    for raw in decisions:
        proposals = tuple(Proposal(p.get("label", "Proposal"), p.get("rationale", "No rationale recorded"), float(p.get("confidence", .5)), p.get("tradeoffs", "No trade-offs recorded")) for p in raw.get("proposals", []))
        while len(proposals) < 2:
            proposals += (Proposal("Request evidence", "Gather missing evidence", .5, "Delays decision"),)
        points.append(PacketPoint(raw["point_id"], raw.get("anchor", "document:1"), raw.get("question", "What should happen?"), proposals, raw.get("helper", raw.get("implications", "Review downstream implications")), raw.get("evidence_gap", ""), highlight=raw.get("highlight", raw.get("question", "")), document_highlights=dict(raw.get("highlights", {}))))
    return DiscussionPacket("interactive", 1, tuple(points), "design")


def _standalone_demo_decisions() -> list[dict]:
    return [{
        "point_id": f"standalone-{index}",
        "anchor": anchor,
        "question": question,
        "highlight": {"design:L4": "Design boundary", "workplan:L8": "Rollout step", "design:L16": "Validation path"}[anchor],
        "highlights": {"design": "Design boundary" if anchor == "design:L4" else "Validation path" if anchor == "design:L16" else "Design boundary", "workplan": "Rollout step"},
        "proposals": [
            {"label": "Conservative", "rationale": "Minimize change", "confidence": .8, "tradeoffs": "slower delivery"},
            {"label": "Expedite", "rationale": "Shorten feedback loop", "confidence": .6, "tradeoffs": "higher review load"},
        ],
        "helper": "Review the highlighted document anchor and downstream implications.",
        "evidence_gap": "Standalone demo evidence is synthetic.",
    } for index, (anchor, question) in enumerate((("design:L4", "Which design boundary?"), ("workplan:L8", "Which rollout step?"), ("design:L16", "Which validation path?")), 1)]


def run_application(application, *, output_fn=print) -> int:
    """Run a live app while restoring the terminal and redacting failures."""
    try:
        application.run()
        return 0
    except KeyboardInterrupt:
        output_fn("TUI interrupted; terminal restored.")
        return 130
    except Exception as error:  # noqa: BLE001 - public boundary intentionally redacts details
        output_fn(f"TUI stopped ({type(error).__name__}); terminal restored.")
        return 1


def build_application(*, document: str = "Awaiting AR context", points: str = "No discussion points", helper: str = "Select a point for implications and evidence", on_event=None, packet: DiscussionPacket | None = None, workplan: str = "Awaiting workplan", design_document: str | None = None, decisions=None, transport: LiveSessionTransport | None = None) -> Application:
    design_document = design_document if design_document is not None else document
    packet = packet or (_packet_from_decisions(decisions, design_document, workplan) if decisions else None)
    interaction = LiveInteraction(packet or _default_packet(design_document, points))
    interaction.proposal_edit_index = 0
    interaction.proposal_confirm = False
    document_view = TextArea(
        text=render_markdown(design_document),
        read_only=True,
        scrollbar=True,
        input_processors=[_ActiveHighlightProcessor(lambda: interaction.active_highlight() if packet else "")],
    )
    points_view = TextArea(text=interaction.render_points() if packet else points, read_only=True, scrollbar=True)
    helper_view = TextArea(text=interaction.render_helper() if packet else helper, read_only=True, scrollbar=True)
    editor_fields = [
        TextArea(text="", multiline=False, height=1, prompt="Label: "),
        TextArea(text="", multiline=False, height=1, prompt="Rationale: "),
        TextArea(text="", multiline=False, height=1, prompt="Confidence (0..1): "),
        TextArea(text="", multiline=False, height=1, prompt="Trade-offs: "),
    ]
    # ``editor`` remains the public first-field alias used by scenario drivers.
    editor = editor_fields[0]
    editor_form = ConditionalContainer(
        HSplit(editor_fields, height=Dimension(min=4, max=4, preferred=4)),
        filter=Condition(lambda: interaction.input_mode and not interaction.proposal_confirm),
    )
    confirmation_view = TextArea(text="", read_only=True, height=3)
    confirmation = ConditionalContainer(
        confirmation_view,
        filter=Condition(lambda: interaction.input_mode and interaction.proposal_confirm),
    )
    footer = TextArea(text="↑/↓: decision  ←/→: proposal  tab/w/d: workplan/design  page-up/page-down: scroll document  enter: select  r: reject  c: clarify  m: evidence  a: add  e: edit own  s: save  o: reopen  q: quit", read_only=True, height=1, style="class:footer")
    bindings = KeyBindings()
    def refresh():
        for field in editor_fields:
            field.visible = interaction.input_mode and not interaction.proposal_confirm
        editor.visible = interaction.input_mode and not interaction.proposal_confirm
        points_view.text = interaction.render_points() if packet else points
        if interaction.input_mode:
            if interaction.proposal_confirm:
                options = ("Yes", "No")
                choices = "    ".join(("▶ " if i == getattr(interaction, "confirm_index", 0) else "  ") + value for i, value in enumerate(options))
                confirmation_view.text = f"Confirm own proposal?\n{choices}\nUse ←/→/↑/↓, then Enter."
                helper_view.text = "Review the four proposal fields. Enter confirms; Escape cancels."
            else:
                helper_view.text = (
                    f"Own proposal field {interaction.proposal_edit_index + 1}/4. "
                    "Tab/Enter/↑/↓ switches fields; action keys are entered as text."
                )
        else:
            helper_view.text = interaction.render_helper() if packet else helper
        if interaction.exit_confirm:
            requirements = interaction.exit_requirements()
            complete_unsaved = not interaction.exit_requirements()[:-1] and not interaction.saved
            options = ("No, stay", "Save + exit" if complete_unsaved else "Yes, exit")
            choices = "    ".join(("▶ " if i == interaction.exit_confirm_index else "  ") + value for i, value in enumerate(options))
            helper_view.text = "Work remains:\n- " + "\n- ".join(requirements) + f"\n\nExit the TUI anyway?\n{choices}\nUse ←/→/↑/↓, then Enter."
        document = workplan if interaction.document_mode == "workplan" else design_document
        rendered = render_markdown(document)
        if packet:
            point = interaction.point
            phrase = interaction.active_highlight()
            # If the selected phrase is only present in the other authoritative
            # document, follow its anchor.  This keeps normal manual w/d
            # inspection possible when both documents contain the phrase.
            follow_anchor = not getattr(interaction, "_manual_document_switch", False)
            interaction._manual_document_switch = False
            if follow_anchor and phrase.casefold() not in rendered.casefold():
                target = point.anchor.split(":", 1)[0].lower()
                if target in {"workplan", "plan"} and interaction.document_mode != "workplan":
                    interaction.document_mode = "workplan"
                    rendered = render_markdown(workplan)
                elif target == "design" and interaction.document_mode != "design":
                    interaction.document_mode = "design"
                    rendered = render_markdown(design_document)
            # Keep the active context visible above the rendered Markdown and
            # locate the phrase in the rendered buffer so prompt-toolkit
            # scrolls the read-only pane to the selected decision.
            prefix = f"▶ ACTIVE DECISION ANCHOR: {point.anchor}\n▶ HIGHLIGHT TARGET\n\n"
            document_view.text = prefix + rendered
            # Search the rendered Markdown body, not the explanatory marker,
            # so the viewport lands on the actual source text.
            body_start = len(prefix)
            position = document_view.text.casefold().find(phrase.casefold(), body_start)
            if position < 0:
                # A live AR may refer to text not present in a stale document;
                # retain an explicit, visible marker rather than failing.
                document_view.text += f"\n\n▶ HIGHLIGHT NOT FOUND IN DOCUMENT: {phrase}"
                position = document_view.text.casefold().find(phrase.casefold())
            document_view.buffer.cursor_position = max(0, position)
            # BufferControl renders search matches with its configured
            # highlight style.  Keeping the search state on the rendered
            # Markdown (rather than inserting marker characters) preserves
            # valid Markdown/text while making the active phrase visibly
            # highlighted in every live terminal.
            document_view.control.search_state.text = phrase
            document_view.control.search_state.ignore_case = True
        else:
            document_view.text = rendered
            document_view.buffer.cursor_position = 0
            document_view.control.search_state.text = ""
    def emit(event, event_type):
        response = None
        previous_response = interaction.responses.get(interaction.point.point_id) if packet else None
        if packet and event_type in {"select", "reject", "clarify"}:
            response = interaction.respond(event_type)
        acknowledgement: EventAcknowledgement | None = None
        if transport is not None:
            payload = {"point_id": interaction.point.point_id}
            if response is not None:
                payload.update({"disposition": response.disposition, "selected": response.selected})
                request_id = getattr(interaction, "point_request_ids", {}).get(interaction.point.point_id, getattr(interaction, "request_id", None))
                if request_id:
                    payload["request_id"] = request_id
                candidate_id = getattr(interaction, "candidate_ids", {}).get(interaction.point.point_id, {}).get(response.selected)
                if candidate_id:
                    payload["selected_candidate"] = candidate_id
                if response.user_proposal is not None:
                    payload["user_proposal"] = {"label": response.user_proposal.label, "evaluated": response.user_proposal_evaluated}
            acknowledgement = transport.submit(event_type, **payload)
            if not acknowledgement.accepted:
                if packet and event_type in {"select", "reject", "clarify"}:
                    if previous_response is None:
                        interaction.responses.pop(interaction.point.point_id, None)
                    else:
                        interaction.responses[interaction.point.point_id] = previous_response
                refresh()
                helper_view.text = f"Event not accepted: {acknowledgement.reason}"
                return
        if event_type == "safe-exit":
            interaction.saved = True
        refresh()
        if response is not None and response.disposition == "clarify":
            helper_view.text = (
                "Clarification requested: this decision is not answered.\n\n"
                "Review the highlighted document context, then select a proposal, "
                "add your own proposal, or request evidence."
            )
        if on_event is not None: on_event(event_type)
        if transport is not None:
            application.awtui_last_acknowledgement = acknowledgement
    def cancel_proposal_input(event):
        interaction.input_mode = False
        interaction.proposal_confirm = False
        for field in editor_fields: field.text = ""
        event.app.layout.focus(points_view)
        refresh()

    @bindings.add("q")
    @bindings.add("escape")
    def quit_app(event):
        if interaction.input_mode and event.key_sequence[0].key == "escape":
            cancel_proposal_input(event)
        elif event.key_sequence[0].key == "escape":
            # Escape is the explicit immediate-cancel affordance; q remains
            # the guarded exit path that explains unsaved/unresolved work.
            event.app.exit(result=130)
        elif interaction.exit_confirm:
            interaction.exit_confirm = False
            refresh()
        elif interaction.exit_requirements():
            interaction.exit_confirm = True
            interaction.exit_confirm_index = 0
            refresh()
        elif interaction.input_mode:
            event.app.current_buffer.insert_text(event.key_sequence[0].key)
        elif not event.app.is_done:
            event.app.exit(result=0)
    def focus_proposal_field(event, index):
        interaction.proposal_edit_index = index % len(editor_fields)
        event.app.layout.focus(editor_fields[interaction.proposal_edit_index])
        refresh()

    def move_proposal_field(event, delta):
        if interaction.proposal_confirm:
            interaction.confirm_index = (getattr(interaction, "confirm_index", 0) + delta) % 2
            refresh()
            return
        focus_proposal_field(event, interaction.proposal_edit_index + delta)

    @bindings.add("up")
    def up(event):
        if interaction.input_mode:
            move_proposal_field(event, -1)
        elif interaction.exit_confirm:
            interaction.exit_confirm_index = (interaction.exit_confirm_index - 1) % 2; refresh()
        else:
            interaction.move_point(-1); refresh()
    @bindings.add("down")
    def down(event):
        if interaction.input_mode:
            move_proposal_field(event, 1)
        elif interaction.exit_confirm:
            interaction.exit_confirm_index = (interaction.exit_confirm_index + 1) % 2; refresh()
        else:
            interaction.move_point(1); refresh()
    @bindings.add("left")
    def left(event):
        if interaction.input_mode:
            if interaction.proposal_confirm: move_proposal_field(event, -1)
            else: event.app.current_buffer.cursor_left()
        elif interaction.exit_confirm:
            interaction.exit_confirm_index = (interaction.exit_confirm_index - 1) % 2; refresh()
        else:
            interaction.move_proposal(-1); refresh()
    @bindings.add("right")
    def right(event):
        if interaction.input_mode:
            if interaction.proposal_confirm: move_proposal_field(event, 1)
            else: event.app.current_buffer.cursor_right()
        elif interaction.exit_confirm:
            interaction.exit_confirm_index = (interaction.exit_confirm_index + 1) % 2; refresh()
        else:
            interaction.move_proposal(1); refresh()
    def page_document(event, delta):
        """Scroll the document pane while preserving active decision state."""
        buffer = document_view.buffer
        step = max(1, len(document_view.text) // 3)
        buffer.cursor_position = max(0, min(len(document_view.text), buffer.cursor_position + delta * step))
        event.app.layout.focus(document_view)
    @bindings.add(Keys.PageUp)
    def page_up(event): page_document(event, -1)
    @bindings.add(Keys.PageDown)
    def page_down(event): page_document(event, 1)
    @bindings.add("tab")
    def toggle_document(event):
        if interaction.input_mode:
            move_proposal_field(event, 1)
        else:
            interaction.switch_document()
    @bindings.add("s-tab")
    def reverse_proposal_field(event):
        if interaction.input_mode: move_proposal_field(event, -1)
    @bindings.add("w")
    def workplan_key(event):
        if interaction.input_mode: event.app.current_buffer.insert_text("w")
        else: interaction.document_mode = "workplan"; interaction._manual_document_switch = True; refresh()
    @bindings.add("d")
    def design_key(event):
        if interaction.input_mode: event.app.current_buffer.insert_text("d")
        else: interaction.document_mode = "design"; interaction._manual_document_switch = True; refresh()
    @bindings.add("enter")
    def enter(event):
        if interaction.exit_confirm:
            if interaction.exit_confirm_index == 1 and not interaction.exit_requirements()[:-1] and not interaction.saved:
                emit(event, "safe-exit")
                event.app.exit(result=0)
            elif interaction.exit_confirm_index == 1:
                event.app.exit(result=0)
            else:
                interaction.exit_confirm = False
                refresh()
            return
        if interaction.input_mode:
            if not interaction.proposal_confirm:
                if interaction.proposal_edit_index < len(editor_fields) - 1:
                    move_proposal_field(event, 1)
                    return
                raw = [field.text.strip() for field in editor_fields]
                try:
                    if any(not value for value in raw) or not 0 <= float(raw[2]) <= 1: raise ValueError
                    interaction.confirm_index = 0
                    interaction.proposal_confirm = True
                    refresh()
                except (ValueError, TypeError):
                    helper_view.text = "Invalid proposal: complete every field; confidence must be between 0 and 1."
                return
            if getattr(interaction, "confirm_index", 0) == 0:
                raw = [field.text.strip() for field in editor_fields]
                proposal = Proposal("User: " + raw[0], raw[1], float(raw[2]), raw[3])
                interaction.add_proposal(proposal)
                interaction.input_mode = False
                interaction.proposal_confirm = False
                for field in editor_fields: field.text = ""
                event.app.layout.focus(points_view)
                emit(event, "add-proposal")
            else:
                interaction.proposal_confirm = False
                interaction.proposal_edit_index = 0
                event.app.layout.focus(editor_fields[0])
                refresh()
            return
        emit(event, "select")
    for key, event_type in (("r", "reject"), ("c", "clarify"), ("m", "request-more-evidence"), ("s", "safe-exit"), ("o", "reopen")):
        @bindings.add(key)
        def control(event, event_type=event_type, key=key):
            if interaction.input_mode:
                event.app.current_buffer.insert_text(key)
                return
            emit(event, event_type)
    @bindings.add("a")
    def add(event):
        if event.app is None:
            emit(event, "add-proposal")
            return
        if interaction.input_mode:
            event.app.current_buffer.insert_text("a")
            return
        interaction.input_mode = True
        interaction.editing_proposal_index = None
        interaction.proposal_confirm = False
        interaction.proposal_edit_index = 0
        event.app.layout.focus(editor_fields[0])
        refresh()

    @bindings.add("e")
    def edit(event):
        if interaction.input_mode:
            event.app.current_buffer.insert_text("e")
            return
        if not interaction.begin_edit_proposal():
            helper_view.text = "Select a user proposal (✎) before editing it."
            return
        proposal = interaction.proposal
        fields = (proposal.label.removeprefix("User: "), proposal.rationale, str(proposal.confidence), proposal.tradeoffs)
        for field, value in zip(editor_fields, fields):
            field.text = value
        interaction.input_mode = True
        interaction.proposal_confirm = False
        interaction.proposal_edit_index = 0
        event.app.layout.focus(editor_fields[0])
        refresh()
    # Keep the pane geometry independent of the amount of text in a document,
    # proposal, or helper message.  The weighted dimensions are deliberately
    # attached to the containers (rather than inferred from TextArea content):
    # each pane keeps its allocation while the terminal is resized, and
    # prompt-toolkit reflows the complete layout on SIGWINCH.  Minimums make
    # narrow terminals degrade as a whole instead of allowing one pane to
    # consume all available space.
    pane_width = Dimension(min=28, max=120, weight=1)
    narrow_pane_width = Dimension(min=1, max=120, weight=1)
    document_row_height = Dimension(min=8, max=40, preferred=8, weight=3)
    actual_document_row_height = Dimension(min=8, max=80, weight=4)
    helper_height = Dimension(min=6, max=12, preferred=9, weight=1)
    document_frame = Frame(document_view, title="Design / Workplan", width=pane_width, style="class:document-pane")
    points_frame = Frame(points_view, title="Decisions and proposals", width=pane_width, style="class:decision-pane")
    helper_frame = Frame(helper_view, title="Helper: rationale, implications, evidence", style="class:helper-pane", width=Dimension(weight=1), height=helper_height)
    horizontal_documents = VSplit([document_frame, points_frame], padding=0, width=Dimension(weight=1), height=actual_document_row_height)
    vertical_documents = HSplit(
        [
            Frame(document_view, title="Design / Workplan", width=narrow_pane_width, style="class:document-pane"),
            Frame(points_view, title="Decisions and proposals", width=narrow_pane_width, style="class:decision-pane"),
        ], padding=0, width=Dimension(weight=1), height=actual_document_row_height
    )
    responsive_documents = DynamicContainer(
        lambda: vertical_documents if get_app().output.get_size().columns < 100 else horizontal_documents
    )
    # Preserve the public geometry inspection surface while DynamicContainer
    # chooses the narrow-terminal arrangement at render time.
    responsive_documents.width = Dimension(weight=1)
    responsive_documents.height = document_row_height
    responsive_documents.children = horizontal_documents.children
    body = HSplit(
        [responsive_documents, helper_frame, editor_form, confirmation, footer],
        width=Dimension(weight=1),
        height=Dimension(weight=1),
    )
    application = Application(
        layout=Layout(body), key_bindings=bindings, full_screen=True,
        erase_when_done=True,
        style=Style.from_dict({
            "frame.border": "ansiblue",
            "frame.label": "bold ansicyan",
            "document-pane.frame.border": "ansigreen",
            "decision-pane.frame.border": "ansiyellow",
            "helper-pane.frame.border": "ansimagenta",
            "footer": "bg:#202530 #d7f9ff",
        }),
    )
    interaction._refresh = refresh
    refresh()
    application.awtui_panes = (document_view, points_view, helper_view)
    application.awtui_footer = footer
    application.awtui_layout_dimensions = {
        "document_row": document_row_height,
        "pane_width": pane_width,
        "helper": helper_height,
    }
    application.awtui_responsive_documents = responsive_documents
    application.editor = editor
    application.editor_fields = tuple(editor_fields)
    application.confirmation_view = confirmation_view
    application.interaction = interaction; application.awtui_state = interaction
    return application


def build_application_from_context(context: dict, *, decisions=None, on_event=None, record_event=None) -> Application:
    """Build the live UI from a Coordinator/AWG context, always rendering Markdown documents."""
    documents = context.get("documents", {})
    transport = LiveSessionTransport(context, record_event) if record_event is not None else None
    application = build_application(
        design_document=documents.get("design", "# Design document\n\nNo design document supplied."),
        workplan=documents.get("workplan", "# Workplan\n\nNo workplan supplied."),
        decisions=decisions,
        on_event=on_event,
        transport=transport,
    )
    application.interaction.request_id = context.get("request_id")
    application.interaction.candidate_ids = {
        item.get("point_id"): {proposal.get("label"): proposal.get("candidate_id") for proposal in item.get("proposals", []) if proposal.get("candidate_id")}
        for item in (decisions or [])
    }
    return application


def build_directive_application(context: dict, *, directive: str = "", on_event=None,
                                record_event=None) -> Application:
    """Build the revision-bound board-instruction entry view.

    Directives are intentionally separate from proposal selection: the user
    enters free-form board intent, then explicitly submits it as one
    ``directive`` event carrying the same session boundary and sequence
    guarantees as a decision event.
    """
    transport = LiveSessionTransport(context, record_event) if record_event is not None else None
    editor = TextArea(text=directive, multiline=True, scrollbar=True, wrap_lines=True)
    status = TextArea(text="Enter a board instruction. Ctrl-S submits; Escape cancels.", read_only=True, height=3)
    footer = TextArea(text="Ctrl-S: submit directive   Enter: new line   Escape: cancel", read_only=True, height=1, style="class:footer")
    bindings = KeyBindings()

    def submit(event):
        value = editor.text.strip()
        if not value:
            status.text = "Directive is required before submission."
            return
        kwargs = {"request_id": context.get("request_id", context.get("decision_request_ref", "")), "directive": value}
        acknowledgement = transport.submit("directive", **kwargs) if transport is not None else None
        if acknowledgement is not None and not acknowledgement.accepted:
            status.text = f"Directive not accepted: {acknowledgement.reason}"
            return
        if on_event is not None:
            on_event("directive")
        event.app.exit(result=0)

    @bindings.add("c-s")
    def submit_directive(event):
        submit(event)

    @bindings.add("escape")
    def cancel(event):
        event.app.exit(result=130)

    application = Application(
        layout=Layout(HSplit([
            Frame(editor, title="Board instruction", height=Dimension(weight=1)),
            Frame(status, title="Contract", height=Dimension(min=3, max=3)), footer,
        ])),
        key_bindings=bindings, full_screen=True, erase_when_done=True,
        style=Style.from_dict({"frame.border": "ansiblue", "frame.label": "bold ansicyan", "footer": "bg:#202530 #d7f9ff"}),
    )
    application.directive_editor = editor
    application.directive_status = status
    return application


def build_application_from_awg_request(request: dict, *, project_id: str, session_id: str, documents: dict[str, str] | None = None, on_event=None, record_event=None) -> Application:
    """Build the live TUI directly from Guidance's decision-request schema."""
    from .awg import envelope_requests_to_tui, request_to_tui
    if isinstance(request.get("batch"), list):
        context, decisions = envelope_requests_to_tui(request, project_id=project_id, session_id=session_id, documents=documents or request.get("documents"))
    else:
        context, decisions = request_to_tui(request, project_id=project_id, session_id=session_id, documents=documents)
    application = build_application_from_context(context, decisions=decisions, on_event=on_event, record_event=record_event)
    application.interaction.point_request_ids = {item["point_id"]: item.get("request_id", context.get("request_id")) for item in decisions}
    return application


def build_application_from_structure_graph(graph: dict, *, project_id: str, session_id: str, on_event=None, record_event=None) -> Application:
    """Build the TUI from authoritative AR graph nodes and anchors."""
    from .graph import structure_graph_to_tui
    from .awg import request_digest
    documents, decisions = structure_graph_to_tui(graph)
    context = {
        "project_id": project_id,
        "ar_id": graph.get("ar_id", "AR-GRAPH"),
        "task_revision": graph.get("task_revision", 1),
        "packet_digest": graph.get("packet_digest", request_digest(graph)),
        "session_id": session_id,
        "contract_versions": {"awg": "0.2", "tui": "1", "awq": "1", "coordinator": "1"},
        "request_id": graph.get("request_id"),
        "documents": documents,
    }
    return build_application_from_context(context, decisions=decisions, on_event=on_event, record_event=record_event)


def run_application(application: Application, *, output_fn=print) -> int:
    """Run the app and report a concise status after terminal cleanup.

    prompt-toolkit restores raw mode, resize handlers, the renderer, and the
    alternate screen in its ``finally`` path. Disabling its interactive error
    screen means this boundary reports only a safe summary after that cleanup,
    without tracebacks, packet contents, prompts, or host paths.
    """
    try:
        result = application.run(set_exception_handler=False, handle_sigint=True)
    except KeyboardInterrupt:
        output_fn("TUI interrupted; terminal restored.")
        return 130
    except EOFError:
        output_fn("TUI input closed; terminal restored.")
        return 0
    except BaseException as error:
        output_fn(f"TUI stopped ({type(error).__name__}); terminal restored.")
        return 1
    return int(result or 0)


def main(argv: list[str] | None = None) -> int:
    """Run the standalone demo or attach to a Coordinator session file.

    The session-file path is intentionally an explicit opt-in.  A remote
    worker can prepare the handoff, but it never guesses which local terminal
    the user owns or spawns a shell on the user's behalf.
    """
    import argparse

    parser = argparse.ArgumentParser(prog="awtui-live")
    parser.add_argument("--session-file", type=Path, help="private Coordinator request JSON")
    parser.add_argument("--input-json", action="store_true", help="read one Coordinator request JSON object from stdin")
    parser.add_argument("--output-json", type=Path, help="atomically write the latest revision-bound event JSON")
    args = parser.parse_args(argv)
    if args.session_file is not None and args.input_json:
        parser.error("--session-file and --input-json are mutually exclusive")
    if args.session_file is not None or args.input_json:
        from .host import append_event, attach_session
        from .transport_io import read_json, write_json_file

        if args.input_json:
            request = read_json(sys.stdin)
        else:
            request = attach_session(args.session_file)
        if request.get("kind") != "coordinator-tui-request":
            parser.error("input is not a coordinator-tui-request")
        interaction = request.get("interaction") if isinstance(request.get("interaction"), dict) else {}
        documents = request.get("documents")
        event_log = args.session_file.with_suffix(".events.jsonl") if args.session_file else None

        def record_event(event: dict) -> None:
            if args.output_json is not None:
                write_json_file(event, args.output_json)
            if event_log is not None:
                append_event(event_log, event)

        if interaction.get("mode") == "directive" or request.get("directive") is not None:
            context = {
                "project_id": request["project_id"], "ar_id": request["ar"]["ar_id"],
                "task_revision": request["ar"]["task_revision"], "packet_digest": request["packet_digest"],
                "session_id": request["session_id"], "request_id": interaction.get("decision_request_ref", request.get("request_id", "")),
                "contract_versions": request.get("contract_versions", {"tui": "1"}),
            }
            application = build_directive_application(context, directive=request.get("directive", ""), record_event=record_event)
        else:
            guidance = request["guidance_request"]
            application = build_application_from_awg_request(
            guidance,
            project_id=request["project_id"],
            session_id=request["session_id"],
            documents=documents if isinstance(documents, dict) else None,
            record_event=record_event,
            )
        return run_application(application)
    return run_application(build_application(
        design_document="# Design document\n\nDefine the service boundary and validation strategy.",
        workplan="# Workplan\n\n1. Agree boundary\n2. Stage rollout\n3. Validate outcomes",
        decisions=_standalone_demo_decisions(),
    ))
