package com.example.agentworkflowui.ui.main

/** The shared decision action vocabulary. Non-select actions deliberately do
 * not answer a decision; this mirrors the desktop renderers. */
enum class DecisionAction { SELECT, REJECT, CLARIFY, REQUEST_MORE_EVIDENCE, REOPEN }

data class ProposalDraft(
  val label: String,
  val rationale: String,
  val confidence: Double,
  val tradeoffs: String,
) {
  fun validate() {
    require(label.isNotBlank()) { "proposal label is required" }
    require(rationale.isNotBlank()) { "proposal rationale is required" }
    require(confidence in 0.0..1.0) { "proposal confidence must be between 0 and 1" }
    require(tradeoffs.isNotBlank()) { "proposal trade-offs are required" }
  }
}

data class DecisionDraft(
  val id: String,
  val selectedProposal: String? = null,
  val ownProposal: ProposalDraft? = null,
  val disposition: DecisionAction? = null,
) {
  val answered: Boolean get() = disposition == DecisionAction.SELECT && (selectedProposal != null || ownProposal != null)
  val unresolvedRequest: Boolean get() = disposition in setOf(
    DecisionAction.REJECT, DecisionAction.CLARIFY, DecisionAction.REQUEST_MORE_EVIDENCE)
  val editable: Boolean get() = !answered || disposition == DecisionAction.REOPEN

  fun apply(action: DecisionAction, proposal: String? = selectedProposal): DecisionDraft = when (action) {
    DecisionAction.SELECT -> copy(disposition = action, selectedProposal = proposal, ownProposal = null)
    DecisionAction.REOPEN -> copy(disposition = action, selectedProposal = null, ownProposal = null)
    DecisionAction.REJECT, DecisionAction.CLARIFY, DecisionAction.REQUEST_MORE_EVIDENCE ->
      copy(disposition = action, selectedProposal = null, ownProposal = null)
  }

  fun withOwnProposal(proposal: ProposalDraft): DecisionDraft {
    proposal.validate()
    return copy(disposition = DecisionAction.SELECT, selectedProposal = null, ownProposal = proposal)
  }
}

data class BatchSaveState(
  val hasBatch: Boolean = false,
  val registered: Boolean = false,
  val dirty: Boolean = false,
  val saved: Boolean = false,
  val sentEvents: Int = 0,
  val totalDecisions: Int = 0,
  val answeredDecisions: Int = 0,
) {
  val complete: Boolean get() = totalDecisions > 0 && answeredDecisions == totalDecisions
  val canSave: Boolean get() = hasBatch && registered && dirty
  val canSaveAndExit: Boolean get() = canSave && complete
  val exitWarning: String? get() = when {
    !dirty -> null
    !complete -> "Some decisions are still unresolved. Save and exit anyway?"
    !saved -> "Selections are not saved. Save and exit using the current selections?"
    else -> null
  }

  fun afterBatch(count: Int, isRegistered: Boolean): BatchSaveState = copy(
    hasBatch = true, registered = isRegistered, dirty = false, saved = false,
    sentEvents = 0, totalDecisions = count, answeredDecisions = 0)

  fun changed(answered: Int): BatchSaveState = copy(dirty = true, saved = false, answeredDecisions = answered)
  fun committed(events: Int): BatchSaveState = if (hasBatch && registered && events > 0)
    copy(dirty = false, saved = true, sentEvents = events) else this
}
