# Keyboard and accessibility guide

The GUI and TUI use the same action contract. The `?` command opens this map
inside either renderer; the GUI also exposes it as the **Help (?)** button.

| Shortcut | Action | Meaning |
| --- | --- | --- |
| Up / Down | Next/previous decision | Move through the complete batch. |
| Left / Right | Next/previous proposal | Inspect alternatives without answering. |
| Tab / `w` / `d` | Switch document | Change between rendered Design and Work plan. |
| PageUp / PageDown | Scroll document | Scroll while retaining the active decision and highlight. |
| Enter | Select proposal | Record the current proposal. |
| `r` | Reject | Reject the proposal without answering the decision. |
| `c` | Clarify | Ask for clarification; the decision remains unresolved. |
| `m` | More evidence | Request evidence and keep the decision open. |
| `a` | Add proposal | Open the four-field own-proposal editor. |
| `e` | Edit own proposal | Re-open the existing user-authored proposal. |
| `s` | Save | Persist the current revision-bound selections. |
| `o` | Reopen | Make an answered decision selectable again. |
| `?` | Help | Show this action map and focus guidance. |
| `q` / Escape | Quit | Guard unresolved or unsaved work before closing. |

## Focus and editing

The normal focus order is decisions, proposals, document panes, helper, then
action buttons. `Tab` and `Shift+Tab` move between focusable controls in the
GUI. While editing an own proposal, `Tab`, `Enter`, and Up/Down move between
label, rationale, confidence, and trade-offs. All printable characters,
including action letters such as `c`, `m`, and `s`, remain ordinary input in
those fields. The final Enter presents a Yes/No confirmation before the
proposal is added or replaced.

The TUI uses a high-contrast footer and focus border. The GUI uses visible
focus borders, accessible names, tooltips, and the same action labels. Both
renderers expose the complete batch count and saved/unsaved status.
