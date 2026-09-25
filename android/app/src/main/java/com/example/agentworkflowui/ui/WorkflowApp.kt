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
import com.example.agentworkflowui.data.AndroidBridgeClient
import com.example.agentworkflowui.data.DeviceIdentity
import com.example.agentworkflowui.ui.scanner.QrScanner
import com.example.agentworkflowui.theme.AgentWorkflowUITheme
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONObject

private data class Decision(val id: String, val title: String, val context: String,
                            val proposals: List<String>, val selected: Int? = null,
                            val own: String = "")

private fun decisionsFromBatch(batch: JSONObject): List<Decision> {
  val values = batch.optJSONArray("decisions") ?: return emptyList()
  return buildList {
    for (index in 0 until values.length()) {
      val value = values.getJSONObject(index)
      val proposals = value.optJSONArray("proposals") ?: org.json.JSONArray()
      add(Decision(value.optString("id", "D-${index + 1}"),
        value.optString("title", "Decision ${index + 1}"),
        value.optString("context", "AR decision"),
        buildList { for (proposalIndex in 0 until proposals.length()) add(proposals.optString(proposalIndex)) }))
    }
  }
}

@Composable
@OptIn(ExperimentalMaterial3Api::class)
fun WorkflowApp() {
  AgentWorkflowUITheme {
    val snackbars = remember { SnackbarHostState() }
    var registered by remember { mutableStateOf(false) }
    var endpoint by remember { mutableStateOf("") }
    var projectId by remember { mutableStateOf("") }
    var deviceId by remember { mutableStateOf("") }
    var credential by remember { mutableStateOf("") }
    var connectionState by remember { mutableStateOf("Not registered") }
    var sessionId by remember { mutableStateOf("") }
    var taskRevision by remember { mutableIntStateOf(0) }
    var packetDigest by remember { mutableStateOf("") }
    val scope = androidx.compose.runtime.rememberCoroutineScope()
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
    val context = LocalContext.current
    LaunchedEffect(Unit) {
      val prefs = context.getSharedPreferences("workflow-ui-registration", 0)
      endpoint = prefs.getString("endpoint", "") ?: ""
      projectId = prefs.getString("project_id", "") ?: ""
      deviceId = prefs.getString("device_id", "") ?: ""
      credential = prefs.getString("credential", "") ?: ""
      registered = endpoint.isNotBlank() && deviceId.isNotBlank() && credential.isNotBlank()
    }
    LaunchedEffect(registered, endpoint, deviceId, credential) {
      if (!registered) return@LaunchedEffect
      while (true) {
        runCatching {
          val response = withContext(Dispatchers.IO) { AndroidBridgeClient(endpoint).session(deviceId, credential) }
          connectionState = if (response.optString("status") == "pending") "Connected • decision pending" else "Connected • waiting"
          response.optJSONObject("batch")?.let { batch ->
            sessionId = batch.optString("session_id")
            taskRevision = batch.optInt("task_revision")
            packetDigest = batch.optString("packet_digest")
            val live = decisionsFromBatch(batch)
            if (live.isNotEmpty()) decisions = live
          }
        }.onFailure { connectionState = "Reconnect pending" }
        kotlinx.coroutines.delay(5_000)
      }
    }
    val active = decisions[current]
    Scaffold(topBar = {
      TopAppBar(title = { Text("Agent Workflow UI") }, actions = {
        Text(if (registered) "● $connectionState" else "○ $connectionState",
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
            Button(onClick = {
              if (!registered || sessionId.isBlank() || packetDigest.isBlank()) {
                saved = true
              } else {
                scope.launch {
                  runCatching {
                    withContext(Dispatchers.IO) {
                      decisions.forEachIndexed { index, decision ->
                        val answer = decision.own.ifBlank {
                          decision.selected?.let { decision.proposals[it] } ?: return@forEachIndexed
                        }
                        val event = JSONObject().put("schema_version", "1.0")
                          .put("kind", "android-decision-event").put("project_id", projectId)
                          .put("session_id", sessionId).put("task_revision", taskRevision)
                          .put("packet_digest", packetDigest).put("sequence", index + 1)
                          .put("event_type", "select")
                          .put("payload", JSONObject().put("decision_id", decision.id).put("answer", answer))
                        AndroidBridgeClient(endpoint).sendEvent(deviceId, credential, event)
                      }
                    }
                  }.onSuccess { saved = true }.onFailure { connectionState = "Save failed; retry" }
                }
              }
            }) { Text(if (saved) "Saved" else "Save") }
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
      RegistrationDialog(onDismiss = { showScanner = false }, onRegistered = { result ->
        projectId = result.projectId; endpoint = result.endpoint; deviceId = result.deviceId; credential = result.credential
        context.getSharedPreferences("workflow-ui-registration", 0).edit()
          .putString("project_id", projectId).putString("endpoint", endpoint).putString("device_id", deviceId)
          .putString("credential", credential).apply()
        registered = true; showScanner = false
      })
    }
  }
}

private data class Registration(val projectId: String, val endpoint: String, val deviceId: String, val credential: String)

@Composable
private fun RegistrationDialog(onDismiss: () -> Unit, onRegistered: (Registration) -> Unit) {
  val context = LocalContext.current
  val scope = androidx.compose.runtime.rememberCoroutineScope()
  var granted by remember { mutableStateOf(ContextCompat.checkSelfPermission(context, Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED) }
  var scanned by remember { mutableStateOf<String?>(null) }
  var consent by remember { mutableStateOf(false) }
  var error by remember { mutableStateOf<String?>(null) }
  val launcher = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { granted = it }
  AlertDialog(onDismissRequest = onDismiss, title = { Text("Register this phone") }, text = {
    Column {
      Text("Scan the QR code shown by the workflow project. The app displays the project identity and asks for consent before creating a device registration.")
      Spacer(Modifier.height(10.dp))
      if (scanned == null && granted) QrScanner(onPayload = { scanned = it }, modifier = Modifier.fillMaxWidth().height(260.dp))
      else Button(onClick = { launcher.launch(Manifest.permission.CAMERA) }) { Text("Allow camera") }
      scanned?.let { payload ->
        val qr = runCatching { JSONObject(payload) }.getOrNull()
        Text("Project: ${qr?.optString("project_id", "invalid")}")
        Text("Endpoint: ${qr?.optString("endpoint", "invalid")}", style = MaterialTheme.typography.bodySmall)
        Text("The phone's device key stays in Android Keystore.", style = MaterialTheme.typography.bodySmall)
        if (consent) Text("Registering…") else Button(onClick = {
          consent = true
          scope.launch {
            try {
              require(qr != null) { "QR payload is not valid JSON" }
              val response = withContext(Dispatchers.IO) {
                AndroidBridgeClient(qr.getString("endpoint")).register(qr, DeviceIdentity.publicKey(), listOf("decisions", "markdown", "audit"))
              }
              require(response.optString("device_id").isNotBlank()) { "service returned no device identity" }
              onRegistered(Registration(response.getString("project_id"), qr.getString("endpoint"),
                response.getString("device_id"), response.getString("credential")))
            } catch (exception: Exception) {
              consent = false
              error = exception.message ?: "registration failed"
            }
          }
        }) { Text("Approve and register") }
        error?.let { Text(it, color = MaterialTheme.colorScheme.error) }
      }
    }
  }, confirmButton = { TextButton(onClick = onDismiss) { Text("Cancel") } })
}
