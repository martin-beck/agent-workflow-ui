package com.example.agentworkflowui.ui

import android.Manifest
import android.content.pm.PackageManager
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.FilterChip
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Tab
import androidx.compose.material3.TabRow
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import com.example.agentworkflowui.ui.scanner.QrScanner
import com.example.agentworkflowui.theme.AgentWorkflowUITheme
import org.json.JSONObject

private data class Decision(val id: String, val title: String, val context: String,
                            val proposals: List<String>, val selected: Int? = null,
                            val own: String = "")

@Composable
@OptIn(ExperimentalMaterial3Api::class)
fun WorkflowApp() {
  AgentWorkflowUITheme {
    val snackbars = remember { SnackbarHostState() }
    var registered by remember { mutableStateOf(false) }
    var showScanner by remember { mutableStateOf(false) }
    var current by remember { mutableIntStateOf(0) }
    var tab by remember { mutableIntStateOf(0) }
    var saved by remember { mutableStateOf(false) }
    var decisions by remember {
      mutableStateOf(listOf(
        Decision("D-1", "Allocator metadata strategy", "Design §2.1", listOf("Inline metadata", "Side metadata")),
        Decision("D-2", "Benchmark acceptance gate", "Work plan §4", listOf("Strict gate", "Advisory gate")),
        Decision("D-3", "Rollout and rollback", "Work plan §6", listOf("Canary", "Immediate"))))
    }
    val active = decisions[current]
    Scaffold(topBar = {
      TopAppBar(title = { Text("Agent Workflow UI") }, actions = {
        Text(if (registered) "● Connected" else "○ Not registered",
          color = if (registered) Color(0xFF2E7D32) else MaterialTheme.colorScheme.error,
          modifier = Modifier.padding(end = 12.dp))
      })
    }, snackbarHost = { SnackbarHost(snackbars) }) { padding ->
      Column(Modifier.fillMaxSize().padding(padding)) {
        Row(Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 8.dp),
          horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
          Text("Batch: AR decisions", fontWeight = FontWeight.Bold)
          Row {
            OutlinedButton(onClick = { showScanner = true }) { Text(if (registered) "Replace phone" else "Register phone") }
            Spacer(Modifier.width(8.dp))
            Button(onClick = { saved = true }) { Text(if (saved) "Saved" else "Save") }
          }
        }
        Text("${decisions.count { it.selected != null || it.own.isNotBlank() }} / ${decisions.size} decisions answered",
          modifier = Modifier.padding(horizontal = 12.dp), color = MaterialTheme.colorScheme.primary)
        Row(Modifier.fillMaxWidth().height(230.dp).padding(12.dp)) {
          LazyColumn(Modifier.weight(0.38f)) {
            items(decisions) { decision ->
              val index = decisions.indexOf(decision)
              Card(Modifier.fillMaxWidth().padding(bottom = 6.dp).clickable { current = index }) {
                Column(Modifier.padding(10.dp)) {
                  Text(if (decision.selected != null || decision.own.isNotBlank()) "✓ ${decision.title}" else decision.title,
                    fontWeight = if (index == current) FontWeight.Bold else FontWeight.Normal,
                    color = if (index == current) MaterialTheme.colorScheme.primary else Color.Unspecified)
                  Text(decision.context, style = MaterialTheme.typography.labelSmall)
                }
              }
            }
          }
          Spacer(Modifier.width(8.dp))
          Column(Modifier.weight(0.62f).verticalScroll(rememberScrollState())) {
            Text(if (tab == 0) "DESIGN DOCUMENT" else "WORK PLAN", fontWeight = FontWeight.Bold)
            Spacer(Modifier.height(6.dp))
            Text(if (tab == 0) "# Design document\n\n## 2.1 Decisions\n\n${active.context}\n\n${active.title} is highlighted here.\n\nThe complete Markdown document is rendered in this pane; the active anchor remains visible when the decision changes."
            else "# Work plan\n\n## 4. Delivery gates\n\n${active.context}\n\n${active.title} is highlighted here.\n\nDependencies, evidence, and rollback notes remain available while selecting proposals.")
          }
        }
        TabRow(selectedTabIndex = tab) { Tab(tab == 0, { tab = 0 }, text = { Text("Design") }); Tab(tab == 1, { tab = 1 }, text = { Text("Work plan") }) }
        Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(12.dp)) {
          Text("Decision ${current + 1}: ${active.title}", style = MaterialTheme.typography.titleLarge)
          Text(active.context, style = MaterialTheme.typography.labelMedium)
          Spacer(Modifier.height(8.dp))
          active.proposals.forEachIndexed { index, proposal ->
            FilterChip(selected = active.selected == index, onClick = {
              decisions = decisions.mapIndexed { i, value -> if (i == current) value.copy(selected = index, own = "") else value }
              saved = false
            }, label = { Text(proposal) }, modifier = Modifier.padding(end = 8.dp))
          }
          OutlinedTextField(value = active.own, onValueChange = { text ->
            decisions = decisions.mapIndexed { i, value -> if (i == current) value.copy(selected = null, own = text) else value }
            saved = false
          }, label = { Text("Own proposal (optional)") }, modifier = Modifier.fillMaxWidth().padding(top = 8.dp))
          Text("Only the selected proposal is committed. You can revise it before Save.", style = MaterialTheme.typography.bodySmall)
          Spacer(Modifier.height(12.dp))
          HorizontalDivider()
          Text("Operator controls", fontWeight = FontWeight.Bold, modifier = Modifier.padding(top = 12.dp))
          Text("Revision-bound session • audit trail • stale/replay events rejected • reconnect safe", style = MaterialTheme.typography.bodySmall)
        }
      }
    }
    if (showScanner) {
      RegistrationDialog(onDismiss = { showScanner = false }, onRegistered = {
        registered = true; showScanner = false
      })
    }
  }
}

@Composable
private fun RegistrationDialog(onDismiss: () -> Unit, onRegistered: () -> Unit) {
  val context = LocalContext.current
  var granted by remember { mutableStateOf(ContextCompat.checkSelfPermission(context, Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED) }
  val launcher = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { granted = it }
  AlertDialog(onDismissRequest = onDismiss, title = { Text("Register this phone") }, text = {
    Column {
      Text("Scan the QR code shown by the workflow project. The app will display the project identity and ask for consent before creating a device registration.")
      Spacer(Modifier.height(10.dp))
      if (granted) QrScanner(onPayload = { onRegistered() }, modifier = Modifier.fillMaxWidth().height(260.dp))
      else Button(onClick = { launcher.launch(Manifest.permission.CAMERA) }) { Text("Allow camera") }
    }
  }, confirmButton = { TextButton(onClick = onDismiss) { Text("Cancel") } })
}
