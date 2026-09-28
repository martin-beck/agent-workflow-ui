package com.example.agentworkflowui.data

import java.net.URI

/** Validates untrusted QR endpoint and SSH rendezvous metadata before use. */
object EndpointPolicy {
  fun requireHttps(value: String): String = requireEndpoint(value, allowLoopbackHttp = false)

  /** Allow only the HTTP URL manufactured by our authenticated loopback SSH tunnel. */
  fun requireTunnelEndpoint(value: String): String = requireEndpoint(value, allowLoopbackHttp = true)

  private fun requireEndpoint(value: String, allowLoopbackHttp: Boolean): String {
    val normalized = value.trim().removeSuffix("/")
    require(normalized.isNotEmpty()) { "service endpoint is empty" }
    val uri = runCatching { URI(normalized) }.getOrElse { error("service endpoint is malformed") }
    val secure = uri.scheme.equals("https", ignoreCase = true)
    val loopback = uri.host == "127.0.0.1" || uri.host == "localhost" || uri.host == "[::1]" || uri.host == "::1"
    require(secure || (allowLoopbackHttp && uri.scheme.equals("http", ignoreCase = true) && loopback)) {
      "service endpoint must use HTTPS unless it is an authenticated loopback tunnel"
    }
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
    require(rendezvous.optString("port").toIntOrNull() in 1..65535) { "SSH rendezvous port is invalid" }
    require(rendezvous.optString("host_key_fingerprint").isNotBlank()) {
      "SSH rendezvous host-key fingerprint is missing"
    }
    require(rendezvous.optString("forward_port").toIntOrNull() in 1..65535) {
      "SSH rendezvous forward port is invalid"
    }
    return endpoint
  }
}
