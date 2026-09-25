package com.example.agentworkflowui.ui

import androidx.activity.ComponentActivity
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
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
}
