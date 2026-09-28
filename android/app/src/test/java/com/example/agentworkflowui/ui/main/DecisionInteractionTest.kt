package com.example.agentworkflowui.ui.main

import junit.framework.TestCase.assertFalse
import junit.framework.TestCase.assertTrue
import org.junit.Test

class DecisionInteractionTest {
  @Test fun unresolvedActionsDoNotAnswerDecision() {
    val initial = DecisionDraft("D-1", selectedProposal = "safe")
    assertTrue(initial.apply(DecisionAction.SELECT).answered)
    listOf(DecisionAction.REJECT, DecisionAction.CLARIFY, DecisionAction.REQUEST_MORE_EVIDENCE).forEach {
      assertFalse(initial.apply(it).answered)
      assertTrue(initial.apply(it).unresolvedRequest)
    }
  }

  @Test fun reopenClearsSelectionAndAllowsReplacement() {
    val selected = DecisionDraft("D-1", selectedProposal = "safe", disposition = DecisionAction.SELECT)
    val reopened = selected.apply(DecisionAction.REOPEN)
    assertFalse(reopened.answered)
    assertTrue(reopened.editable)
    assertTrue(reopened.apply(DecisionAction.SELECT, "fast").answered)
  }

  @Test fun structuredOwnProposalIsValidatedAndRoundTrips() {
    val proposal = ProposalDraft("custom", "fits AR constraints", .8, "more review")
    val decision = DecisionDraft("D-1").withOwnProposal(proposal)
    assertTrue(decision.answered)
    assertTrue(decision.ownProposal == proposal)
  }

  @Test(expected = IllegalArgumentException::class)
  fun ownProposalRequiresAllFields() {
    DecisionDraft("D-1").withOwnProposal(ProposalDraft("custom", "", .8, "tradeoff"))
  }

  @Test fun saveStateCannotClaimSavedWithoutAuthoritativeBatch() {
    val empty = BatchSaveState().changed(0)
    assertFalse(empty.canSave)
    assertFalse(empty.committed(1).saved)
    val ready = BatchSaveState().afterBatch(2, isRegistered = true).changed(1)
    assertTrue(ready.canSave)
    assertFalse(ready.canSaveAndExit)
    assertTrue(ready.committed(1).saved)
  }
}
