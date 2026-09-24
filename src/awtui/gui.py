"""Premium Linux desktop renderer for the Agent Workflow decision session.

The GUI is an adapter over the same ``LiveInteraction`` view-model used by
the terminal renderer.  Qt is optional so headless/SSH environments retain a
small, reliable TUI installation.
"""
from __future__ import annotations

import sys
from typing import Any

from .discussion import Proposal
from .live import LiveInteraction, _default_packet, _packet_from_decisions
from .anchors import resolve_occurrence
from .actions import help_text
from .persistence import DurableSessionPersistence


def _qt():
    try:
        from PySide6 import QtCore, QtGui, QtWidgets
    except ImportError as error:  # pragma: no cover - depends on host install
        raise RuntimeError("GUI support requires the gui extra: pip install 'agent-workflow-ui[gui]'") from error
    return QtCore, QtGui, QtWidgets


class DecisionWindow:
    """Qt window exposing the complete batched decision interaction."""

    def __init__(self, interaction: LiveInteraction, *, title: str = "Agent Workflow", on_event=None) -> None:
        QtCore, QtGui, QtWidgets = _qt()
        self.QtCore, self.QtGui, self.QtWidgets = QtCore, QtGui, QtWidgets
        self.interaction = interaction
        self._allow_close = False
        self.on_event = on_event
        self.persistence = DurableSessionPersistence(interaction, on_event=on_event)
        self.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
        self.window = QtWidgets.QMainWindow()
        self.window.setWindowTitle(title)
        self.window.setMinimumSize(1050, 700)
        self.app.setStyle("Fusion")
        self.window.setStyleSheet(
            "QMainWindow { background:#0f1724; } QWidget { color:#e8eef7; font-size:13px; }"
            "QLabel#sectionTitle { color:#9db8d8; font-size:11px; font-weight:700; letter-spacing:1px; }"
            "QFrame, QListWidget, QTextBrowser, QLineEdit { background:#172235; border:1px solid #334862; border-radius:8px; }"
            "QListWidget::item { padding:7px 8px; border-radius:5px; }"
            "QListWidget::item:selected { background:#285a94; color:#ffffff; }"
            "QTextBrowser { padding:8px; selection-background-color:#d9a441; selection-color:#111827; }"
            "QPushButton { background:#24364f; border:1px solid #49617d; border-radius:6px; padding:8px 12px; min-width:92px; }"
            "QPushButton:hover { background:#315d89; border-color:#78b4e8; }"
            "QPushButton:focus { border:2px solid #8cc8ff; }"
            "QPushButton#primaryAction { background:#18794e; border-color:#42b883; font-weight:700; }"
            "QPushButton#primaryAction:hover { background:#239663; }"
            "QPushButton#dangerAction { background:#713842; border-color:#c8757e; }"
            "QToolTip { background:#f5f7fb; color:#172235; border:1px solid #6d89a8; padding:6px; }"
        )
        self._build()
        self._install_shortcuts()
        self._refresh()

    def _build(self) -> None:
        QtWidgets = self.QtWidgets
        central = QtWidgets.QWidget()
        root = QtWidgets.QVBoxLayout(central)
        header = QtWidgets.QLabel("AGENT WORKFLOW  /  HUMAN DECISION SESSION")
        header.setStyleSheet("font-size:16px; font-weight:700; color:#a8cbff; padding:4px;")
        header.setToolTip("Review the batch, inspect the linked Markdown context, then record each human decision.")
        root.addWidget(header)
        split = QtWidgets.QSplitter(self.QtCore.Qt.Orientation.Horizontal)
        docs = QtWidgets.QSplitter(self.QtCore.Qt.Orientation.Vertical)
        self.design = QtWidgets.QTextBrowser(); self.workplan = QtWidgets.QTextBrowser()
        self.design.setAccessibleName("Design document"); self.workplan.setAccessibleName("Work plan document")
        self.design.setToolTip("Rendered design document. The highlighted phrase follows the selected decision.")
        self.workplan.setToolTip("Rendered work plan. The highlighted phrase follows the selected decision.")
        self.design.setOpenExternalLinks(False); self.workplan.setOpenExternalLinks(False)
        docs.addWidget(self.design); docs.addWidget(self.workplan); docs.setSizes([1, 1])
        split.addWidget(docs)
        right = QtWidgets.QWidget(); right_layout = QtWidgets.QVBoxLayout(right)
        self.status = QtWidgets.QLabel(); self.status.setAccessibleName("Decision session status"); self.status.setToolTip("Shows saved state and how many decisions in this batch are selected."); right_layout.addWidget(self.status)
        filters = QtWidgets.QHBoxLayout()
        self.filter = QtWidgets.QLineEdit(); self.filter.setPlaceholderText("Filter AR, group, anchor, or question"); self.filter.setAccessibleName("Decision filter"); self.filter.setToolTip("Narrow this batch without changing authoritative order."); self.filter.textChanged.connect(self._filter_changed); filters.addWidget(self.filter)
        self.group_filter = QtWidgets.QComboBox(); self.group_filter.setAccessibleName("Decision group filter"); self.group_filter.setToolTip("Show one decision group while retaining batch identity."); self.group_filter.addItem("All groups", ""); [self.group_filter.addItem(group, group) for group in self.interaction.packet.groups()]; self.group_filter.currentIndexChanged.connect(self._filter_changed); filters.addWidget(self.group_filter)
        self.unresolved_only = QtWidgets.QCheckBox("Unresolved only"); self.unresolved_only.setAccessibleName("Unresolved decisions only"); self.unresolved_only.stateChanged.connect(self._filter_changed); filters.addWidget(self.unresolved_only)
        right_layout.addLayout(filters)
        points_title = QtWidgets.QLabel("DECISIONS IN THIS BATCH"); points_title.setObjectName("sectionTitle"); right_layout.addWidget(points_title)
        self.points = QtWidgets.QListWidget(); self.points.setAccessibleName("Batch decisions"); self.points.setToolTip("Select a decision to see its proposals and corresponding document highlights."); self.points.currentRowChanged.connect(self._select_point); right_layout.addWidget(self.points, 2)
        proposals_title = QtWidgets.QLabel("PROPOSED SOLUTIONS"); proposals_title.setObjectName("sectionTitle"); right_layout.addWidget(proposals_title)
        self.proposals = QtWidgets.QListWidget(); self.proposals.setAccessibleName("Decision proposals"); self.proposals.setToolTip("Choose a proposal, then use Select, Reject, or Clarify. A selected proposal can be reopened."); self.proposals.currentRowChanged.connect(self._select_proposal); right_layout.addWidget(self.proposals, 2)
        helper_title = QtWidgets.QLabel("DETAILS AND IMPLICATIONS"); helper_title.setObjectName("sectionTitle"); right_layout.addWidget(helper_title)
        self.helper = QtWidgets.QTextBrowser(); self.helper.setAccessibleName("Proposal details and implications"); self.helper.setToolTip("Rationale, confidence, trade-offs, evidence gaps, and the active document anchor."); right_layout.addWidget(self.helper, 3)
        buttons = QtWidgets.QHBoxLayout()
        actions = (("Select", self._select, "Record the highlighted proposal as the current human decision.", "primaryAction"), ("Reject", lambda: self._respond("reject"), "Reject this proposal and leave the decision unresolved.", "dangerAction"), ("Clarify", lambda: self._respond("clarify"), "Ask the Coordinator for clarification; this is not an acceptance.", ""), ("More evidence", self._request_evidence, "Keep this decision open and request additional evidence.", ""), ("Reopen", self._reopen, "Reopen an answered decision so another proposal can be selected.", ""), ("Edit own proposal", self._edit, "Create or edit a user-authored proposal for this decision.", ""))
        for label, callback, tip, object_name in actions:
            button = QtWidgets.QPushButton(label); button.setAccessibleName(label); button.setToolTip(tip); button.setObjectName(object_name); button.clicked.connect(callback); buttons.addWidget(button)
        right_layout.addLayout(buttons)
        bottom = QtWidgets.QHBoxLayout()
        self.document_button = QtWidgets.QPushButton("Switch document"); self.document_button.setAccessibleName("Switch document"); self.document_button.setToolTip("Switch the active document view between Design and Work plan."); self.document_button.clicked.connect(self._switch_document); bottom.addWidget(self.document_button)
        save = QtWidgets.QPushButton("Save"); save.setAccessibleName("Save"); save.setToolTip("Persist the current selections to the revision-bound event journal."); save.clicked.connect(self._save); bottom.addWidget(save)
        self.help_button = QtWidgets.QPushButton("Help (?)"); self.help_button.setAccessibleName("Keyboard and accessibility help"); self.help_button.setToolTip("Show the complete keyboard map, focus order, and editing guidance."); self.help_button.clicked.connect(self._show_help); bottom.addWidget(self.help_button)
        exit_button = QtWidgets.QPushButton("Save + Exit"); exit_button.setAccessibleName("Save and exit"); exit_button.setObjectName("primaryAction"); exit_button.setToolTip("Save all current selections and close the decision session."); exit_button.clicked.connect(self._save_exit); bottom.addWidget(exit_button)
        right_layout.addLayout(bottom)
        split.addWidget(right); split.setSizes([700, 420])
        root.addWidget(split, 1)
        self.window.setCentralWidget(central)
        self.window.closeEvent = self._close_event

    def _install_shortcuts(self) -> None:
        """Install the shared action map without stealing typed editor input."""
        QtGui = self.QtGui
        self._shortcuts = []
        bindings = {
            "?": self._show_help,
            "Up": lambda: self._move_point(-1),
            "Down": lambda: self._move_point(1),
            "Left": lambda: self._move_proposal(-1),
            "Right": lambda: self._move_proposal(1),
            "PageUp": lambda: self._scroll_documents(-1),
            "PageDown": lambda: self._scroll_documents(1),
        }
        for sequence, callback in bindings.items():
            shortcut = QtGui.QShortcut(QtGui.QKeySequence(sequence), self.window)
            shortcut.setContext(self.QtCore.Qt.ShortcutContext.WindowShortcut)
            shortcut.activated.connect(callback)
            self._shortcuts.append(shortcut)

    def _editing(self) -> bool:
        return isinstance(self.app.focusWidget(), self.QtWidgets.QLineEdit)

    def _move_point(self, delta: int) -> None:
        if self._editing(): return
        self.interaction.move_point(delta); self._refresh()

    def _move_proposal(self, delta: int) -> None:
        if self._editing(): return
        self.interaction.move_proposal(delta); self._refresh()

    def _scroll_documents(self, delta: int) -> None:
        if self._editing(): return
        for widget in (self.design, self.workplan):
            bar = widget.verticalScrollBar()
            bar.setValue(bar.value() + delta * max(1, bar.pageStep()))

    def _show_help(self) -> None:
        box = self.QtWidgets.QMessageBox(self.window)
        box.setWindowTitle("Agent Workflow keyboard and accessibility help")
        box.setAccessibleName("Keyboard and accessibility help")
        box.setText(help_text(gui=True))
        box.setInformativeText("Focus order is decisions, proposals, documents, helper, then actions. All action buttons are keyboard reachable; editor fields retain typed characters.")
        box.setStandardButtons(self.QtWidgets.QMessageBox.StandardButton.Close)
        box.exec()

    def _select_point(self, index: int) -> None:
        if index >= 0:
            visible = self.interaction.visible_points()
            if index >= len(visible): return
            self.interaction.point_index = next(i for i, point in enumerate(self.interaction.packet.points) if point.point_id == visible[index].point_id)
            self.interaction.proposal_index = 0
            self._refresh()

    def _select_proposal(self, index: int) -> None:
        if index >= 0:
            self.interaction.proposal_index = index
            self._refresh_helper()

    def _respond(self, disposition: str) -> None:
        try:
            self.interaction.respond(disposition)
        except ValueError as error:
            self.helper.setPlainText(str(error) + "\n\nReview the prerequisite decision or inspect its evidence references.")
            return
        if self.on_event is not None:
            self.on_event({"event_type": disposition, "point_id": self.interaction.point.point_id,
                           "disposition": disposition,
                           "selected": self.interaction.responses[self.interaction.point.point_id].selected})
        self._refresh()

    def _select(self) -> None:
        self._respond("select")

    def _request_evidence(self) -> None:
        self.interaction.saved = False
        self.helper.setPlainText("More evidence requested for this decision. The Coordinator will keep it unresolved until evidence is supplied.\n\nEvidence refs: " + (", ".join(self.interaction.point.evidence_refs) or "none recorded"))
        if self.on_event is not None:
            self.on_event({"event_type": "request-more-evidence", "point_id": self.interaction.point.point_id,
                           "disposition": "request-more-evidence"})

    def _filter_changed(self) -> None:
        self.interaction.set_filter(self.filter.text(), self.group_filter.currentData() or "", include_answered=not self.unresolved_only.isChecked())
        self._refresh()

    def _reopen(self) -> None:
        self.interaction.responses.pop(self.interaction.point.point_id, None)
        self.interaction.saved = False
        if self.on_event is not None:
            self.on_event({"event_type": "reopen", "point_id": self.interaction.point.point_id})
        self._refresh()

    def _switch_document(self) -> None:
        self.interaction.switch_document(); self._refresh()

    def _save(self) -> None:
        self.persistence.save(); self._refresh()

    def _save_exit(self) -> None:
        self.persistence.save(exit=True)
        if self.on_event is not None:
            self.on_event({"event_type": "safe-exit", "point_id": self.interaction.point.point_id})
        self.window.close()

    def _close_event(self, event: Any) -> None:
        if self._allow_close:
            event.accept(); return
        missing = self.interaction.exit_requirements()
        if not missing:
            event.accept(); return
        answer = self.QtWidgets.QMessageBox.question(
            self.window, "Decision session not finished",
            "The session still needs:\n• " + "\n• ".join(missing) +
            "\n\nSave the current state and exit?",
            self.QtWidgets.QMessageBox.StandardButton.Save |
            self.QtWidgets.QMessageBox.StandardButton.Cancel |
            self.QtWidgets.QMessageBox.StandardButton.Yes |
            self.QtWidgets.QMessageBox.StandardButton.No,
        )
        if answer in {self.QtWidgets.QMessageBox.StandardButton.Save, self.QtWidgets.QMessageBox.StandardButton.Yes}:
            self._save(); event.accept()
        else:
            event.ignore()

    def close_without_prompt(self) -> None:
        """Close a headless capture/test window without a user prompt."""
        self._allow_close = True
        self.window.close()
        self.app.processEvents()

    def _edit(self) -> None:
        if not self.interaction.begin_edit_proposal():
            self._new_proposal()
            return
        self._new_proposal(editing=True)

    def _new_proposal(self, *, editing: bool = False) -> None:
        QtWidgets = self.QtWidgets
        dialog = QtWidgets.QDialog(self.window); dialog.setWindowTitle("Edit proposal" if editing else "Add proposal")
        form = QtWidgets.QFormLayout(dialog)
        fields = []
        values = [self.interaction.proposal.label.removeprefix("User: ") if editing else "", self.interaction.proposal.rationale if editing else "", str(self.interaction.proposal.confidence) if editing else "0.7", self.interaction.proposal.tradeoffs if editing else ""]
        for name, value in zip(("Label", "Rationale", "Confidence (0..1)", "Trade-offs"), values):
            field = QtWidgets.QLineEdit(value); form.addRow(name, field); fields.append(field)
        ok = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.StandardButton.Ok | QtWidgets.QDialogButtonBox.StandardButton.Cancel); form.addRow(ok)
        ok.accepted.connect(dialog.accept); ok.rejected.connect(dialog.reject)
        if dialog.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            try:
                proposal = Proposal("User: " + fields[0].text().strip(), fields[1].text().strip(), float(fields[2].text()), fields[3].text().strip())
                self.interaction.add_proposal(proposal); self._refresh()
                if self.on_event is not None:
                    self.on_event({"event_type": "add-proposal", "point_id": self.interaction.point.point_id,
                                   "user_proposal": {"label": proposal.label, "rationale": proposal.rationale,
                                                      "confidence": proposal.confidence, "tradeoffs": proposal.tradeoffs}})
            except (ValueError, TypeError) as error:
                QtWidgets.QMessageBox.warning(self.window, "Invalid proposal", str(error))

    def _refresh_helper(self) -> None:
        self.helper.setPlainText(self.interaction.render_helper())

    def _highlight_document(self, widget: Any, phrase: str, occurrence: int = 0,
                            ranges: tuple[dict[str, object], ...] = ()) -> None:
        # QTextDocument.find() without a cursor always starts at the beginning.
        # Resolve the same occurrence-aware range used by the TUI instead.
        text = widget.toPlainText()
        selections = []
        targets = ranges or ({"text": phrase, "occurrence": occurrence},)
        first_cursor = None
        for target in targets:
            target_phrase = str(target.get("text", phrase))
            match = resolve_occurrence(text, target_phrase, int(target.get("occurrence", 0)))
            if match is None: continue
            cursor = self.QtGui.QTextCursor(widget.document())
            cursor.setPosition(match.start)
            cursor.setPosition(match.end, self.QtGui.QTextCursor.MoveMode.KeepAnchor)
            selection = self.QtWidgets.QTextEdit.ExtraSelection()
            selection.cursor = cursor
            selection.format.setBackground(self.QtGui.QColor("#d6a84f"))
            selection.format.setForeground(self.QtGui.QColor("#111722"))
            selections.append(selection)
            if first_cursor is None: first_cursor = cursor
        if first_cursor is not None:
            widget.setTextCursor(first_cursor)
            widget.ensureCursorVisible()
        widget.setExtraSelections(selections)

    def _refresh(self) -> None:
        self.points.blockSignals(True); self.points.clear()
        visible = self.interaction.visible_points()
        for point in visible:
            response = self.interaction.responses.get(point.point_id)
            marker = "✓" if response and response.disposition == "select" else "•"
            self.points.addItem(f"{marker} {point.point_id}  {point.anchor}")
        current_row = next((row for row, point in enumerate(visible) if point.point_id == self.interaction.point.point_id), 0)
        self.points.setCurrentRow(current_row); self.points.blockSignals(False)
        self.proposals.blockSignals(True); self.proposals.clear()
        point = self.interaction.point
        response = self.interaction.responses.get(point.point_id)
        visible = [self.interaction.proposal] if response and response.selected else list(point.proposals)
        for proposal in visible: self.proposals.addItem(proposal.label)
        self.proposals.setCurrentRow(min(self.interaction.proposal_index, max(0, len(visible) - 1))); self.proposals.blockSignals(False)
        design_document = self.interaction.packet_document("design") if hasattr(self.interaction, "packet_document") else ""
        workplan_document = self.interaction.packet_document("workplan") if hasattr(self.interaction, "packet_document") else ""
        self.design.setMarkdown(design_document)
        self.workplan.setMarkdown(workplan_document)
        for mode, widget in (("design", self.design), ("workplan", self.workplan)):
            phrase = self.interaction.point.document_highlights.get(mode, self.interaction.point.highlight or self.interaction.point.question)
            ranges = self.interaction.point.highlight_ranges.get(mode, ())
            occurrence = int(ranges[0].get("occurrence", 0)) if ranges else 0
            self._highlight_document(widget, phrase, occurrence, ranges)
        summary = self.interaction.packet.summary(self.interaction.responses)
        self.status.setText(f"Decision {self.interaction.point_index + 1}/{len(self.interaction.packet.points)}  |  {'saved' if self.interaction.saved else 'unsaved'}  |  answered {summary['answered']}/{summary['total']}  |  unresolved {summary['unresolved']}  |  blocked {summary['blocked']}")
        self._refresh_helper()

    def run(self) -> int:
        self.window.show()
        return self.app.exec()


def build_gui_application(*, design_document: str = "# Design\n\nAwaiting AR context", workplan: str = "# Work plan\n\nAwaiting AR context", decisions: list[dict[str, Any]] | None = None, on_event=None) -> DecisionWindow:
    packet = _packet_from_decisions(decisions, design_document, workplan) if decisions else _default_packet("design", "Review the design")
    interaction = LiveInteraction(packet)
    # Keep source Markdown in the shared view-model for both renderers.
    interaction.packet_document = lambda mode: design_document if mode == "design" else workplan  # type: ignore[attr-defined]
    return DecisionWindow(interaction, on_event=on_event)


def main() -> int:
    return build_gui_application().run()


if __name__ == "__main__":
    raise SystemExit(main())
