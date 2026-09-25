package com.example.agentworkflowui.data

import junit.framework.TestCase.assertEquals
import junit.framework.TestCase.assertTrue
import org.junit.Test

/**
 * Deterministic protocol qualification for the Kotlin client.
 *
 * The fake transport models the service wire contract without opening a
 * socket. This catches URL, authentication, and JSON regressions in the
 * Android-side implementation; tests/test_android_server.py covers the same
 * contract against the Python adapter.
 */
class AndroidBridgeClientTest {
  @Test
  fun registrationSessionAndEventUseTheRevisionBoundServiceContract() {
    val transport = FakeTransport(
      BridgeResponse(200, "{\"project_id\":\"p1\",\"device_id\":\"d1\",\"credential\":\"c1\"}"),
      BridgeResponse(200, "{\"status\":\"pending\",\"batch\":{\"session_id\":\"s1\"}}"),
      BridgeResponse(200, "{\"accepted\":true,\"sequence\":1}"),
    )
    val client = AndroidBridgeClient("https://workflow.example/", transport)

    client.register(
      "{\"project_id\":\"p1\",\"bootstrap_id\":\"b1\"}",
      publicKey = "public-key",
      capabilities = listOf("decisions", "markdown"),
    )
    client.session("d1", "c1")
    client.sendEvent(
      "d1",
      "c1",
      "{\"project_id\":\"p1\",\"sequence\":1,\"task_revision\":7,\"packet_digest\":\"sha256:x\"}",
    )

    assertEquals(3, transport.requests.size)
    assertEquals("POST", transport.requests[0].method)
    assertEquals("/v1/register", transport.requests[0].path)
    assertEquals("GET", transport.requests[1].method)
    assertEquals("Bearer c1", transport.requests[1].headers["Authorization"])
    assertEquals("d1", transport.requests[1].headers["X-Device-Id"])
    assertEquals("/v1/events", transport.requests[2].path)
    assertEquals("Bearer c1", transport.requests[2].headers["Authorization"])
    assertTrue(transport.requests[2].body!!.contains("\"device_id\":\"d1\""))
  }

  @Test
  fun transientReconnectFailureCanRetryTheSameSessionRequest() {
    val transport = FakeTransport(
      RuntimeException("network temporarily unavailable"),
      BridgeResponse(200, "{\"status\":\"idle\",\"batch\":null}"),
    )
    val client = AndroidBridgeClient("https://workflow.example", transport)

    try {
      client.session("device-1", "credential-1")
      error("expected transient failure")
    } catch (error: RuntimeException) {
      assertEquals("network temporarily unavailable", error.message)
    }
    client.session("device-1", "credential-1")

    assertEquals(2, transport.requests.size)
    assertEquals(transport.requests[0], transport.requests[1])
  }

  @Test
  fun rejectedResponsesFailClosedWithServiceBody() {
    val client = AndroidBridgeClient(
      "https://workflow.example",
      FakeTransport(BridgeResponse(401, "{\"error\":\"revoked\"}")),
    )

    val failure = runCatching { client.session("device-1", "expired") }.exceptionOrNull()

    assertEquals("workflow service rejected session request: {\"error\":\"revoked\"}", failure?.message)
  }

  private data class Request(
    val method: String,
    val path: String,
    val headers: Map<String, String>,
    val body: String?,
  )

  private class FakeTransport(private vararg val outcomes: Any) : HttpTransport {
    val requests = mutableListOf<Request>()
    private var next = 0

    override fun execute(method: String, url: String, headers: Map<String, String>, body: String?): BridgeResponse {
      requests += Request(method, url.substringAfter("workflow.example"), headers, body)
      val outcome = outcomes[next++]
      if (outcome is RuntimeException) throw outcome
      return outcome as BridgeResponse
    }
  }
}
