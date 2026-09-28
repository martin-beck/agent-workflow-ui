package com.example.agentworkflowui.ui

import androidx.activity.ComponentActivity
import androidx.compose.ui.test.assertTextContains
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onNodeWithContentDescription
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performTextInput
import org.json.JSONObject
import org.junit.Rule
import org.junit.Test

/** UI coverage for a real revision-bound batch, including document parity. */
class WorkflowAppTest {
  @get:Rule val composeTestRule = createAndroidComposeRule<ComponentActivity>()

  private fun batch() = JSONObject("""
    {"session_id":"session-1","task_revision":1,"packet_digest":"sha256:test",
     "design_markdown":"# Design\\n\\nThe boundary phrase is authoritative.",
     "workplan_markdown":"# Work plan\\n\\nThe rollout phrase is authoritative.",
     "decisions":[
       {"id":"d1","title":"Boundary","context":"design:L3","anchor":"design:L3",
        "highlights":{"design":"boundary phrase","workplan":"rollout phrase"},
        "proposals":[{"label":"Keep boundary","rationale":"Stable","implications":"No migration"},{"label":"Rework boundary","tradeoffs":"More risk"}]},
       {"id":"d2","title":"Rollout","context":"workplan:L3","anchor":"workplan:L3",
        "highlights":{"design":"boundary phrase","workplan":"rollout phrase"},
        "proposals":["Canary","Immediate"]}]}
  """.trimIndent())

  @Test
  fun emptyWorkspaceDoesNotInventDecisions() {
    composeTestRule.setContent { WorkflowApp() }
    composeTestRule.onNodeWithText("No decision batch is pending.").assertExists()
    composeTestRule.onNodeWithText("Register phone").assertExists()
  }

  @Test
  fun authoritativeDocumentsAndMultipleDecisionsAreDisplayed() {
    composeTestRule.setContent { WorkflowApp(batch()) }
    composeTestRule.onNodeWithText("The boundary phrase is authoritative.").assertExists()
    composeTestRule.onNodeWithText("Boundary").assertExists()
    composeTestRule.onNodeWithText("Rollout").performClick()
    composeTestRule.onNodeWithText("The rollout phrase is authoritative.").assertExists()
  }

  @Test
  fun proposalDetailsAndOwnProposalRemainEditable() {
    composeTestRule.setContent { WorkflowApp(batch()) }
    composeTestRule.onNodeWithText("Keep boundary").performClick()
    composeTestRule.onNodeWithText("Rationale: Stable").assertExists()
    composeTestRule.onNodeWithText("Implications: No migration").assertExists()
    composeTestRule.onNodeWithContentDescription("Own proposal editor for Boundary")
      .performTextInput("Use a measured boundary")
    composeTestRule.onNodeWithContentDescription("Own proposal editor for Boundary")
      .assertTextContains("Use a measured boundary")
    composeTestRule.onNodeWithText("Rework boundary").performClick()
    composeTestRule.onNodeWithText("Proposal details").assertExists()
  }

  @Test
  fun selectionProgressCoversWholeBatch() {
    composeTestRule.setContent { WorkflowApp(batch()) }
    composeTestRule.onNodeWithContentDescription("Decision progress: 0 of 2 answered").assertExists()
    composeTestRule.onNodeWithText("Keep boundary").performClick()
    composeTestRule.onNodeWithContentDescription("Decision progress: 1 of 2 answered").assertExists()
    composeTestRule.onNodeWithText("Rollout").performClick()
    composeTestRule.onNodeWithText("Canary").performClick()
    composeTestRule.onNodeWithContentDescription("Decision progress: 2 of 2 answered").assertExists()
  }
}
