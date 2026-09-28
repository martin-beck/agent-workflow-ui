package com.example.agentworkflowui.ui

import androidx.test.ext.junit.runners.AndroidJUnit4
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class WorkflowContentTest {
  @Test
  fun parsesAuthoritativeDecisionDocumentsAndPerDocumentHighlights() {
    val batch = JSONObject("""
      {"design_markdown":"# Design\\n\\nBoundary phrase",
       "workplan_markdown":"# Work plan\\n\\nRollout phrase",
       "decisions":[{"id":"d1","title":"Boundary","anchor":"design:L3",
         "highlights":{"design":"Boundary phrase","workplan":"Rollout phrase"},
         "helper":"Review rollback evidence",
         "proposals":[{"label":"Keep","rationale":"Stable","implications":"No migration",
           "tradeoffs":"Less flexible","confidence":0.8,"reversibility":"easy",
           "evidence_refs":["test:1"]}]}]}
    """.trimIndent())
    val decision = decisionsFromBatch(batch).single()
    assertEquals("design:L3", decision.anchor)
    assertEquals("Boundary phrase", decision.highlights["design"])
    assertEquals("Rollout phrase", decision.highlights["workplan"])
    assertEquals("Review rollback evidence", decision.helper)
    assertEquals("Stable", decision.proposals.single().rationale)
    assertEquals("test:1", decision.proposals.single().evidence.single())
  }

  @Test
  fun missingDecisionsRemainEmptyInsteadOfInventingFallbackContent() {
    assertTrue(decisionsFromBatch(JSONObject("{\"design_markdown\":\"# real\"}" )).isEmpty())
  }

  @Test
  fun stringProposalsRemainCompatibleWithBridgePayloads() {
    val parsed = decisionsFromBatch(JSONObject("""
      {"decisions":[{"id":"d1","proposals":["A","B"]}]}
    """.trimIndent()))
    assertEquals(listOf("A", "B"), parsed.single().proposals.map { it.label })
  }
}
