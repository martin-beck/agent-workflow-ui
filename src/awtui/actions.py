"""Shared, user-visible action contract for the terminal and Qt renderers."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Action:
    id: str
    label: str
    shortcut: str
    description: str
    editing_safe: bool = False


# Keep this list intentionally small and stable.  Both renderers use it for
# help, key hints, and shortcut registration, so a newly added action cannot
# silently exist in one UI only.
ACTIONS: tuple[Action, ...] = (
    Action("move-decision", "Next/previous decision", "↑ / ↓", "Move through decisions in the batch."),
    Action("move-proposal", "Next/previous proposal", "← / →", "Inspect proposals for the active decision."),
    Action("switch-document", "Switch document", "Tab / w / d", "Switch between rendered Design and Work plan."),
    Action("page-document", "Scroll document", "PageUp / PageDown", "Scroll without changing the active decision or highlight."),
    Action("select", "Select proposal", "Enter", "Record the active proposal as the current answer."),
    Action("reject", "Reject", "r", "Reject the active proposal and leave the decision unresolved."),
    Action("clarify", "Clarify", "c", "Request clarification; this does not answer the decision."),
    Action("more-evidence", "Request more evidence", "m", "Keep the decision open and request evidence."),
    Action("add-proposal", "Add proposal", "a", "Open the four-field own-proposal editor."),
    Action("edit-proposal", "Edit own proposal", "e", "Re-open the existing user-authored proposal."),
    Action("save", "Save", "s", "Persist the current revision-bound selections."),
    Action("reopen", "Reopen decision", "o", "Make an answered decision selectable again."),
    Action("help", "Show help", "?", "Show all available actions and focus guidance."),
    Action("quit", "Quit", "q / Esc", "Close the session; unresolved or unsaved work is guarded."),
)


def action(action_id: str) -> Action:
    return next(item for item in ACTIONS if item.id == action_id)


def help_text(*, gui: bool = False) -> str:
    lines = ["AGENT WORKFLOW — KEYBOARD AND ACCESSIBILITY HELP", "", "Focus order: decisions → proposals → document panes → helper → actions.", "Tab moves focus; Shift+Tab moves backwards. In proposal editing, Tab/Enter/↑/↓ changes fields and typed keys are never actions.", ""]
    for item in ACTIONS:
        shortcut = item.shortcut if not gui else item.shortcut.replace(" / ", ", ")
        lines.append(f"{shortcut:<22} {item.label}: {item.description}")
    return "\n".join(lines)


def footer_text() -> str:
    return "  ".join(f"{item.shortcut}: {item.label}" for item in ACTIONS)
