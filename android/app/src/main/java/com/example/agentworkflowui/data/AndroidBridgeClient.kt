package com.example.agentworkflowui.data

import java.net.HttpURLConnection
import java.net.URL
import org.json.JSONObject

/** Small revision-bound client shared by registration and decision screens. */
class AndroidBridgeClient(private val endpoint: String) {
  fun register(qr: JSONObject, publicKey: String, capabilities: List<String>): JSONObject =
    post("/v1/register", JSONObject().put("qr", qr).put("device_public_key", publicKey)
      .put("capabilities", capabilities))

  fun sendEvent(deviceId: String, credential: String, event: JSONObject): JSONObject =
    post("/v1/events", event.put("device_id", deviceId), credential)

  private fun post(path: String, body: JSONObject, credential: String? = null): JSONObject {
    val connection = (URL(endpoint.trimEnd('/') + path).openConnection() as HttpURLConnection).apply {
      requestMethod = "POST"
      connectTimeout = 10_000
      readTimeout = 20_000
      doOutput = true
      setRequestProperty("Content-Type", "application/json")
      credential?.let { setRequestProperty("Authorization", "Bearer $it") }
    }
    connection.outputStream.use { it.write(body.toString().toByteArray()) }
    val stream = if (connection.responseCode in 200..299) connection.inputStream else connection.errorStream
    val response = stream.bufferedReader().use { it.readText() }
    if (connection.responseCode !in 200..299) error("workflow service rejected request: $response")
    return JSONObject(response)
  }
}
