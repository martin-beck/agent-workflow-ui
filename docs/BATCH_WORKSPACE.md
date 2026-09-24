# Batch decision workspace

Large Coordinator batches stay in one revision-bound session. Every decision
keeps its AR identity, group, dependency list, evidence references, and
document anchor while the user narrows the view.

The GUI provides a text filter, group selector, and **Unresolved only**
checkbox. The status line reports answered, unresolved, and blocked counts.
Selecting a point opens its proposals and the helper pane shows implications,
evidence references, and the dependency that is blocking the point, if any.

The TUI has the same semantics. `g` cycles groups, `u` toggles unresolved-only
mode, and `x` clears the filters. The footer and decision pane show the active
filter and progress. Dependency order is authoritative; moving between points
never drops or renumbers a point, and a blocked point cannot be selected until
its prerequisites have a selected response.

Filtering is a view operation only. It does not alter the packet, response
identity, revision binding, or event journal. Reopening a selected point keeps
the batch identity and makes all proposals available again.
