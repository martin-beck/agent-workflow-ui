package com.example.agentworkflowui.ui

import androidx.activity.ComponentActivity
import androidx.compose.ui.test.assertTextContains
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onNodeWithContentDescription
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performTextInput
import org.junit.Rule
import org.junit.Test

/** Smoke coverage for the real decision workspace used by the emulator job. */
class WorkflowAppTest {
  @get:Rule val composeTestRule = createAndroidComposeRule<ComponentActivity>()

  @Test
  fun decisionWorkspaceShowsBatchAndRegistrationControl() {
    composeTestRule.setContent { WorkflowApp() }
    composeTestRule.onNodeWithText("Batch: AR decisions").assertExists()
    composeTestRule.onNodeWithText("Register phone").assertExists()
    composeTestRule.onNodeWithText("Allocator metadata strategy").assertExists()
  }

  @Test
  fun batchSelectionMarksDecisionAndSaveCompletes() {
    composeTestRule.setContent { WorkflowApp() }

    composeTestRule.onNodeWithText("Inline metadata").performClick()
    composeTestRule.onNodeWithText("✓ Allocator metadata strategy").assertExists()
    composeTestRule.onNodeWithText("Benchmark acceptance gate").performClick()
    composeTestRule.onNodeWithText("Strict gate").performClick()
    composeTestRule.onNodeWithText("✓ Benchmark acceptance gate").assertExists()
    composeTestRule.onNodeWithText("Save").performClick()
    composeTestRule.onNodeWithText("Saved").assertExists()
  }

  @Test
  fun designAndWorkPlanTabsRemainAvailableDuringBatchReview() {
    composeTestRule.setContent { WorkflowApp() }

    composeTestRule.onNodeWithText("Work plan").performClick()
    composeTestRule.onNodeWithText("WORK PLAN").assertExists()
    composeTestRule.onNodeWithText("Allocator metadata strategy").performClick()
    composeTestRule.onNodeWithText("Design").performClick()
    composeTestRule.onNodeWithText("DESIGN DOCUMENT").assertExists()
  }

  @Test
  fun ownProposalReplacesSelectionAndCanBeChangedBeforeSave() {
    composeTestRule.setContent { WorkflowApp() }

    // An operator may revise a decision before committing the batch.  Entering
    // an own proposal clears the previously selected canned proposal, and a
    // later canned choice clears the draft again.
    composeTestRule.onNodeWithText("Inline metadata").performClick()
    composeTestRule.onNodeWithContentDescription("Own proposal editor for Allocator metadata strategy")
      .performTextInput("Segmented metadata")
    composeTestRule.onNodeWithContentDescription("Own proposal editor for Allocator metadata strategy")
      .assertTextContains("Segmented metadata")
    composeTestRule.onNodeWithText("Side metadata").performClick()
    composeTestRule.onNodeWithText("✓ Allocator metadata strategy").assertExists()
    composeTestRule.onNodeWithText("Save").performClick()
    composeTestRule.onNodeWithText("Saved").assertExists()
  }

  @Test
  fun batchProgressShowsUnansweredDecisionBeforeFinalSave() {
    composeTestRule.setContent { WorkflowApp() }

    composeTestRule.onNodeWithContentDescription("Decision progress: 0 of 3 answered").assertExists()
    composeTestRule.onNodeWithText("Inline metadata").performClick()
    composeTestRule.onNodeWithContentDescription("Decision progress: 1 of 3 answered").assertExists()
    composeTestRule.onNodeWithText("Benchmark acceptance gate").performClick()
    composeTestRule.onNodeWithText("Strict gate").performClick()
    composeTestRule.onNodeWithContentDescription("Decision progress: 2 of 3 answered").assertExists()
    composeTestRule.onNodeWithText("Rollout and rollback").performClick()
    composeTestRule.onNodeWithText("Canary").performClick()
    composeTestRule.onNodeWithContentDescription("Decision progress: 3 of 3 answered").assertExists()
  }
}
