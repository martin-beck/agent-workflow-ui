package com.example.agentworkflowui.data

import java.net.URI

/** Validates untrusted QR endpoint and SSH rendezvous metadata before use. */
object EndpointPolicy {
  fun requireHttps(value: String): String {
    val normalized = value.trim().removeSuffix("/")
    require(normalized.isNotEmpty()) { "service endpoint is empty" }
    val uri = runCatching { URI(normalized) }.getOrElse { error("service endpoint is malformed") }
    require(uri.scheme.equals("https", ignoreCase = true)) { "service endpoint must use HTTPS" }
    require(uri.userInfo == null) { "service endpoint must not contain user information" }
    require(!uri.host.isNullOrBlank()) { "service endpoint must contain a host" }
    require(uri.fragment == null && uri.query == null) { "service endpoint must not contain query or fragment" }
    require(uri.path.isEmpty() || uri.path == "/") { "service endpoint must not contain a path" }
    require(uri.port in -1..65535) { "service endpoint port is invalid" }
    return normalized
  }

  fun validateQr(qr: org.json.JSONObject): String {
    val endpoint = requireHttps(qr.optString("endpoint"))
    qr.optString("bootstrap_endpoint", endpoint).takeIf { it.isNotBlank() }?.let(::requireHttps)
    val rendezvous = qr.optJSONObject("ssh_rendezvous") ?: return endpoint
    require(rendezvous.optString("host").isNotBlank()) { "SSH rendezvous host is missing" }
    require(rendezvous.optInt("port", -1) in 1..65535) { "SSH rendezvous port is invalid" }
    require(rendezvous.optString("host_key_fingerprint").isNotBlank()) {
      "SSH rendezvous host-key fingerprint is missing"
    }
    require(rendezvous.optInt("forward_port", -1) in 1..65535) {
      "SSH rendezvous forward port is invalid"
    }
    return endpoint
  }
}
