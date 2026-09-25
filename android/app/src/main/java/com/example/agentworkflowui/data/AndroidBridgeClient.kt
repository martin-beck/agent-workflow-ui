package com.example.agentworkflowui.data

import java.net.HttpURLConnection
import java.net.URL
import org.json.JSONObject

/** Small revision-bound client shared by registration and decision screens. */
class AndroidBridgeClient(
  private val endpoint: String,
  private val transport: HttpTransport = UrlConnectionTransport,
) {
  fun register(qr: JSONObject, publicKey: String, proofSignature: String,
               capabilities: List<String>, consent: Boolean): JSONObject =
    post("/v1/register", JSONObject().put("qr", qr).put("device_public_key", publicKey)
      .put("proof_signature", proofSignature).put("consent", consent)
      .put("capabilities", capabilities))

  /** Raw JSON seam used by JVM protocol qualification (Android's JSONObject is not JVM-backed). */
  fun register(qrJson: String, publicKey: String, proofSignature: String,
               capabilities: List<String>, consent: Boolean): JSONObject {
    val encodedCapabilities = capabilities.joinToString(",") { "\"${escape(it)}\"" }
    val body = "{\"qr\":$qrJson,\"device_public_key\":\"${escape(publicKey)}\"," +
      "\"proof_signature\":\"${escape(proofSignature)}\",\"consent\":$consent,\"capabilities\":[$encodedCapabilities]}"
    return postRaw("/v1/register", body)
  }

  fun sendEvent(deviceId: String, credential: String, event: JSONObject): JSONObject =
    post("/v1/events", event.put("device_id", deviceId), credential)

  fun sendEvent(deviceId: String, credential: String, eventJson: String): JSONObject =
    postRaw("/v1/events", eventJson.trimEnd().removeSuffix("}") + ",\"device_id\":\"${escape(deviceId)}\"}", credential)

  fun session(deviceId: String, credential: String): JSONObject {
    val response = transport.execute(
      method = "GET",
      url = endpoint.trimEnd('/') + "/v1/session",
      headers = mapOf("Authorization" to "Bearer $credential", "X-Device-Id" to deviceId),
      body = null,
    )
    return response.jsonOrThrow("session")
  }

  fun sshChallenge(deviceId: String): JSONObject {
    val response = transport.execute("GET", endpoint.trimEnd('/') + "/v1/ssh/challenge?device_id=$deviceId",
      emptyMap(), null)
    return response.jsonOrThrow("SSH challenge")
  }

  fun releaseSshCredential(challenge: JSONObject, signature: String): JSONObject =
    post("/v1/ssh/credential", JSONObject().put("device_id", challenge.getString("device_id"))
      .put("challenge_id", challenge.getString("challenge_id")).put("nonce", challenge.getString("nonce"))
      .put("expires_at", challenge.getString("expires_at")).put("signature", signature))

  private fun post(path: String, body: JSONObject, credential: String? = null): JSONObject {
    return postRaw(path, body.toString(), credential)
  }

  private fun postRaw(path: String, body: String, credential: String? = null): JSONObject {
    val headers = buildMap {
      put("Content-Type", "application/json")
      credential?.let { put("Authorization", "Bearer $it") }
    }
    return transport.execute(
      method = "POST",
      url = endpoint.trimEnd('/') + path,
      headers = headers,
      body = body.toString(),
    ).jsonOrThrow(path)
  }

  private fun BridgeResponse.jsonOrThrow(operation: String): JSONObject {
    if (statusCode !in 200..299) error("workflow service rejected $operation request: $body")
    return JSONObject(body)
  }

  private fun escape(value: String): String = value.replace("\\", "\\\\").replace("\"", "\\\"")
}

/** Minimal transport seam so protocol tests never need a live Android service. */
fun interface HttpTransport {
  fun execute(method: String, url: String, headers: Map<String, String>, body: String?): BridgeResponse
}

data class BridgeResponse(val statusCode: Int, val body: String)

private object UrlConnectionTransport : HttpTransport {
  override fun execute(method: String, url: String, headers: Map<String, String>, body: String?): BridgeResponse {
    val connection = (URL(url).openConnection() as HttpURLConnection).apply {
      requestMethod = method
      connectTimeout = 10_000
      readTimeout = 20_000
      doOutput = body != null
      headers.forEach { (key, value) -> setRequestProperty(key, value) }
    }
    body?.let { connection.outputStream.use { stream -> stream.write(it.toByteArray()) } }
    val status = connection.responseCode
    val stream = if (status in 200..299) connection.inputStream else connection.errorStream
    val response = stream.bufferedReader().use { it.readText() }
    connection.disconnect()
    return BridgeResponse(status, response)
  }
}
