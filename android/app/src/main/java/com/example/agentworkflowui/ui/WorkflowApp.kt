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
import androidx.compose.runtime.saveable.listSaver
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import com.example.agentworkflowui.data.AndroidBridgeClient
import com.example.agentworkflowui.data.DeviceIdentity
import com.example.agentworkflowui.data.RegistrationStore
import com.example.agentworkflowui.data.SshTunnelManager
import com.example.agentworkflowui.ui.scanner.QrScanner
import com.example.agentworkflowui.theme.AgentWorkflowUITheme
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONObject

internal data class Proposal(val label: String, val rationale: String = "",
                            val implications: String = "", val tradeoffs: String = "",
                            val confidence: String = "", val reversibility: String = "",
                            val evidence: List<String> = emptyList())
internal data class Decision(val id: String, val title: String, val context: String,
                            val proposals: List<Proposal>, val anchor: String = "",
                            val highlights: Map<String, String> = emptyMap(),
                            val helper: String = "", val selected: Int? = null,
                            val own: String = "")

private val decisionSaver = listSaver<List<Decision>, String>(
  save = { decisions -> decisions.flatMap { decision ->
    listOf(decision.id, decision.title, decision.context, decision.selected?.toString() ?: "",
      decision.own, decision.proposals.joinToString("\u001f") { it.label }, decision.anchor,
      decision.highlights["design"] ?: "", decision.highlights["workplan"] ?: "", decision.helper)
  } },
  restore = { values -> values.chunked(10).mapNotNull { fields ->
    if (fields.size < 10) null else Decision(fields[0], fields[1], fields[2],
      fields[5].split("\u001f").filter(String::isNotEmpty).map(::Proposal),
      anchor = fields[6], highlights = mapOf("design" to fields[7], "workplan" to fields[8]),
      helper = fields[9], selected = fields[3].toIntOrNull(), own = fields[4])
  } }
)

private fun defaultDecisions() = emptyList<Decision>()

private fun proposalFromJson(value: Any?): Proposal {
  if (value is String) return Proposal(value)
  val json = value as? JSONObject ?: return Proposal("")
  val evidence = buildList {
    val refs = json.optJSONArray("evidence_refs") ?: json.optJSONArray("evidence")
    if (refs != null) for (i in 0 until refs.length()) add(refs.optString(i))
  }
  return Proposal(json.optString("label", json.optString("title", "Proposal")),
    json.optString("rationale"), json.optString("implications", json.optString("impact")),
    json.optString("tradeoffs", json.optString("trade_offs")),
    if (json.has("confidence")) json.optString("confidence") else "",
    json.optString("reversibility"), evidence)
}

internal fun decisionsFromBatch(batch: JSONObject): List<Decision> {
  val values = batch.optJSONArray("decisions") ?: return emptyList()
  return buildList {
    for (index in 0 until values.length()) {
      val value = values.getJSONObject(index)
      val proposals = value.optJSONArray("proposals") ?: org.json.JSONArray()
      val highlights = buildMap {
        value.optJSONObject("highlights")?.let { map ->
          map.keys().forEach { key -> put(key, map.optString(key)) }
        }
        value.optString("highlight").takeIf(String::isNotBlank)?.let { putIfAbsent("design", it) }
      }
      add(Decision(value.optString("id", "D-${index + 1}"),
        value.optString("title", "Decision ${index + 1}"),
        value.optString("context", "AR decision"),
        buildList { for (proposalIndex in 0 until proposals.length()) add(proposalFromJson(proposals.opt(proposalIndex))) },
        value.optString("anchor", value.optString("point_id")), highlights,
        value.optString("helper", value.optString("question"))))
    }
  }
}

@Composable
@OptIn(ExperimentalMaterial3Api::class)
fun WorkflowApp(initialBatch: JSONObject? = null) {
  AgentWorkflowUITheme {
    val snackbars = remember { SnackbarHostState() }
    var registered by remember { mutableStateOf(false) }
    var endpoint by remember { mutableStateOf("") }
    var sshBootstrap by remember { mutableStateOf("") }
    var tunnelEndpoint by remember { mutableStateOf("") }
    var projectId by remember { mutableStateOf("") }
    var deviceId by remember { mutableStateOf("") }
    var credential by remember { mutableStateOf("") }
    var connectionState by remember { mutableStateOf("Not registered") }
    var sessionId by remember { mutableStateOf("") }
    var taskRevision by remember { mutableIntStateOf(0) }
    var packetDigest by remember { mutableStateOf("") }
    var designDocument by rememberSaveable { mutableStateOf(initialBatch?.optString("design_markdown") ?: "") }
    var workplanDocument by rememberSaveable { mutableStateOf(initialBatch?.optString("workplan_markdown") ?: "") }
    val scope = androidx.compose.runtime.rememberCoroutineScope()
    var showScanner by remember { mutableStateOf(false) }
    var current by rememberSaveable { mutableIntStateOf(0) }
    var tab by rememberSaveable { mutableIntStateOf(0) }
    var saved by rememberSaveable { mutableStateOf(false) }
    var decisions by rememberSaveable(stateSaver = decisionSaver) {
      mutableStateOf(initialBatch?.let(::decisionsFromBatch) ?: defaultDecisions())
    }
    val context = LocalContext.current
    LaunchedEffect(Unit) {
      RegistrationStore(context).load()?.let { registration ->
        projectId = registration.projectId
        endpoint = registration.endpoint
        sshBootstrap = registration.sshBootstrap
        deviceId = registration.deviceId
        credential = registration.credential
        registered = true
      }
    }
    LaunchedEffect(registered, endpoint, deviceId, credential, sshBootstrap) {
      if (!registered) return@LaunchedEffect
      var tunnel: com.example.agentworkflowui.data.SshTunnelHandle? = null
      try {
        while (true) {
          runCatching {
            if (sshBootstrap.isNotBlank() && tunnel?.connected != true) {
              tunnel?.close()
              tunnel = withContext(Dispatchers.IO) {
                SshTunnelManager().connect(JSONObject(sshBootstrap))
              }
              tunnelEndpoint = tunnel!!.endpoint
            }
            val routedEndpoint = tunnel?.endpoint ?: endpoint
            val client = AndroidBridgeClient(routedEndpoint)
            if (sshBootstrap.isNotBlank() && credential.isBlank() && tunnel != null) {
              val issued = withContext(Dispatchers.IO) {
                val challenge = client.sshChallenge(deviceId)
                client.releaseSshCredential(challenge, DeviceIdentity.sshSessionProof(challenge))
              }
              credential = issued.getString("credential")
              RegistrationStore(context).save(RegistrationStore.Registration(
                projectId, endpoint, deviceId, credential, sshBootstrap))
            }
            val response = if (credential.isNotBlank()) {
              withContext(Dispatchers.IO) { client.session(deviceId, credential) }
            } else JSONObject().put("status", "idle")
          connectionState = if (response.optString("status") == "pending") "Connected • decision pending" else "Connected • waiting"
          response.optJSONObject("batch")?.let { batch ->
            sessionId = batch.optString("session_id")
            taskRevision = batch.optInt("task_revision")
            packetDigest = batch.optString("packet_digest")
            designDocument = batch.optString("design_markdown")
            workplanDocument = batch.optString("workplan_markdown")
            val live = decisionsFromBatch(batch)
            decisions = live
            current = current.coerceAtMost((live.lastIndex).coerceAtLeast(0))
          }
          }.onFailure {
            if (sshBootstrap.isNotBlank()) {
              tunnel?.close(); tunnel = null; tunnelEndpoint = ""
              connectionState = "SSH reconnect pending"
            } else connectionState = "Reconnect pending"
          }
          kotlinx.coroutines.delay(5_000)
        }
      } finally {
        tunnel?.close()
        tunnelEndpoint = ""
      }
    }
    val active = decisions.getOrNull(current)
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
            OutlinedButton(onClick = { showScanner = true }, modifier = Modifier.semantics {
              contentDescription = if (registered) "Replace registered phone" else "Register this phone"
            }) { Text(if (registered) "Replace phone" else "Register phone") }
            Spacer(Modifier.width(8.dp))
            Button(onClick = {
              if (!registered || sessionId.isBlank() || packetDigest.isBlank()) {
                saved = true
              } else {
                scope.launch {
                  runCatching {
                    withContext(Dispatchers.IO) {
                      val activeEndpoint = if (sshBootstrap.isNotBlank()) {
                        require(tunnelEndpoint.isNotBlank()) { "SSH tunnel is disconnected; decision event not sent" }
                        tunnelEndpoint
                      } else endpoint
                      val journal = RegistrationStore(context).eventJournal()
                      decisions.forEach { decision ->
                        val answer = decision.own.ifBlank {
                          decision.selected?.let { decision.proposals[it].label } ?: return@forEach
                        }
                        journal.reserve(sessionId, decision.id, answer,
                          binding = "$taskRevision:$packetDigest") { sequence ->
                          JSONObject().put("schema_version", "1.0")
                            .put("kind", "android-decision-event").put("project_id", projectId)
                            .put("session_id", sessionId).put("task_revision", taskRevision)
                            .put("packet_digest", packetDigest).put("sequence", sequence)
                            .put("event_type", "select")
                            .put("payload", JSONObject().put("decision_id", decision.id).put("answer", answer))
                            .toString()
                        }
                      }
                      val client = AndroidBridgeClient(activeEndpoint)
                      // Send every durable outbox item in sequence order. A retry
                      // uses the exact same sequence and payload and is accepted
                      // idempotently by AndroidDeviceRegistry.
                      journal.pending(sessionId).forEach { pending ->
                        client.sendEvent(deviceId, credential, JSONObject(pending.event))
                        journal.acknowledge(sessionId, pending.sequence)
                      }
                    }
                  }.onSuccess { saved = true }.onFailure { connectionState = "Save failed; retry" }
                }
              }
            }, modifier = Modifier.semantics {
              contentDescription = if (saved) "Decisions saved" else "Save selected decisions"
            }) { Text(if (saved) "Saved" else "Save") }
          }
        }
        Text("${decisions.count { it.selected != null || it.own.isNotBlank() }} / ${decisions.size} decisions answered",
          modifier = Modifier.padding(horizontal = 12.dp).semantics {
            contentDescription = "Decision progress: ${decisions.count { it.selected != null || it.own.isNotBlank() }} of ${decisions.size} answered"
          }, color = MaterialTheme.colorScheme.primary)
        if (active == null) {
          Text(if (registered) "No decision batch is pending." else "Register this phone to receive an authoritative decision batch.",
            modifier = Modifier.padding(24.dp).semantics { contentDescription = "No pending decisions" })
        } else Row(Modifier.fillMaxWidth().height(300.dp).padding(12.dp)) {
          LazyColumn(Modifier.weight(0.38f)) {
            items(decisions) { decision ->
              val index = decisions.indexOf(decision)
              Card(Modifier.fillMaxWidth().padding(bottom = 6.dp).clickable { current = index }) {
                Column(Modifier.padding(10.dp)) {
                  Text(if (decision.selected != null || decision.own.isNotBlank()) "✓ ${decision.title}" else decision.title,
                    fontWeight = if (index == current) FontWeight.Bold else FontWeight.Normal,
                    color = if (index == current) MaterialTheme.colorScheme.primary else Color.Unspecified)
                  Text(decision.context, style = MaterialTheme.typography.labelSmall,
                    modifier = Modifier.semantics { contentDescription = "Decision context: ${decision.context}" })
                }
              }
            }
          }
          Spacer(Modifier.width(8.dp))
          Column(Modifier.weight(0.62f).verticalScroll(rememberScrollState())) {
            val document = if (tab == 0) designDocument else workplanDocument
            val highlight = active.highlights[if (tab == 0) "design" else "workplan"]
            Text(if (tab == 0) "DESIGN DOCUMENT" else "WORK PLAN", fontWeight = FontWeight.Bold,
              modifier = Modifier.semantics {
                contentDescription = "Rendered ${if (tab == 0) "design document" else "work plan"}"
              })
            Spacer(Modifier.height(6.dp))
            MarkdownDocument(document, highlight, modifier = Modifier.semantics {
              contentDescription = "${if (tab == 0) "Design" else "Work plan"} document content for ${active.title}"
            })
          }
        }
        TabRow(selectedTabIndex = tab) { Tab(tab == 0, { tab = 0 }, text = { Text("Design") }); Tab(tab == 1, { tab = 1 }, text = { Text("Work plan") }) }
        if (active != null) Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(12.dp)) {
          Text("Decision ${current + 1}: ${active.title}", style = MaterialTheme.typography.titleLarge)
          Text(active.context, style = MaterialTheme.typography.labelMedium)
          Spacer(Modifier.height(8.dp))
          active.proposals.forEachIndexed { index, proposal ->
            FilterChip(selected = active.selected == index, onClick = {
              decisions = decisions.mapIndexed { i, value -> if (i == current) value.copy(selected = index, own = "") else value }
              saved = false
            }, label = { Text(proposal.label) }, modifier = Modifier.padding(end = 8.dp).semantics {
              contentDescription = "Proposal ${index + 1}: ${proposal.label}${if (active.selected == index) ", selected" else ""}"
            })
          }
          val selectedProposal = active.selected?.let { active.proposals.getOrNull(it) }
          selectedProposal?.let { proposal ->
            Card(Modifier.fillMaxWidth().padding(top = 8.dp).semantics {
              contentDescription = "Proposal details for ${proposal.label}"
            }) { Column(Modifier.padding(12.dp)) {
              Text("Proposal details", fontWeight = FontWeight.Bold)
              ProposalDetail("Rationale", proposal.rationale)
              ProposalDetail("Implications", proposal.implications)
              ProposalDetail("Trade-offs", proposal.tradeoffs)
              ProposalDetail("Confidence", proposal.confidence)
              ProposalDetail("Reversibility", proposal.reversibility)
              ProposalDetail("Evidence", proposal.evidence.joinToString(", "))
            } }
          }
          OutlinedTextField(value = active.own, onValueChange = { text ->
            decisions = decisions.mapIndexed { i, value -> if (i == current) value.copy(selected = null, own = text) else value }
            saved = false
          }, label = { Text("Own proposal (optional)") }, modifier = Modifier.fillMaxWidth().padding(top = 8.dp).semantics {
            contentDescription = "Own proposal editor for ${active.title}"
          })
          if (active.helper.isNotBlank()) Text(active.helper, style = MaterialTheme.typography.bodySmall,
            modifier = Modifier.semantics { contentDescription = "Helper information: ${active.helper}" })
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
        RegistrationStore(context).save(RegistrationStore.Registration(
          projectId, endpoint, deviceId, credential, result.sshBootstrap))
        registered = true; showScanner = false
      })
    }
  }
}

@Composable
private fun ProposalDetail(label: String, value: String) {
  if (value.isNotBlank()) Text("$label: $value", style = MaterialTheme.typography.bodySmall,
    modifier = Modifier.padding(top = 3.dp))
}

/** Small dependency-free Markdown renderer for the authoritative service documents.
 * It deliberately preserves source text while styling headings and the exact
 * decision phrase, so document anchors remain attributable to the batch. */
@Composable
private fun MarkdownDocument(document: String, highlight: String?, modifier: Modifier = Modifier) {
  val source = document.ifBlank { "No document was supplied by the workflow service." }
  val rendered = buildAnnotatedString {
    val target = highlight?.takeIf(String::isNotBlank) ?: ""
    var cursor = 0
    while (cursor < source.length) {
      val end = source.indexOf('\n', cursor).let { if (it < 0) source.length else it }
      val line = source.substring(cursor, end)
      val trimmed = line.trimStart()
      val lineStyle = when {
        trimmed.startsWith("### ") -> SpanStyle(fontWeight = FontWeight.Bold,
          color = MaterialTheme.colorScheme.primary)
        trimmed.startsWith("## ") -> SpanStyle(fontWeight = FontWeight.Bold,
          color = MaterialTheme.colorScheme.primary)
        trimmed.startsWith("# ") -> SpanStyle(fontWeight = FontWeight.Bold,
          color = MaterialTheme.colorScheme.primary)
        else -> SpanStyle()
      }
      withStyle(lineStyle) {
        var offset = 0
        while (offset < line.length) {
          val relative = if (target.isNotEmpty()) line.indexOf(target, offset) else -1
          if (relative < 0) { append(line.substring(offset)); break }
          append(line.substring(offset, relative))
          withStyle(SpanStyle(background = Color(0xFFFFE082), fontWeight = FontWeight.Bold)) {
            append(target)
          }
          offset = relative + target.length
        }
      }
      if (end < source.length) append('\n')
      cursor = if (end < source.length) end + 1 else source.length
    }
  }
  Text(rendered, modifier = modifier.verticalScroll(rememberScrollState()),
    style = MaterialTheme.typography.bodyMedium)
}

@Composable
private fun RegistrationDialog(onDismiss: () -> Unit, onRegistered: (RegistrationStore.Registration) -> Unit) {
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
                val bootstrapEndpoint = qr.optString("bootstrap_endpoint", qr.getString("endpoint"))
                AndroidBridgeClient(bootstrapEndpoint).register(
                  qr, DeviceIdentity.publicKey(), DeviceIdentity.enrollmentProof(qr),
                  listOf("decisions", "markdown", "audit"), consent = true)
              }
              require(response.optString("device_id").isNotBlank()) { "service returned no device identity" }
              onRegistered(RegistrationStore.Registration(response.getString("project_id"), qr.getString("endpoint"),
                response.getString("device_id"), response.optString("credential", ""),
                if (qr.has("ssh_rendezvous")) qr.toString() else ""))
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
