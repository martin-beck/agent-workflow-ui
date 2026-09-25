package com.example.agentworkflowui.ui

import androidx.activity.ComponentActivity
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onNodeWithText
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
}
