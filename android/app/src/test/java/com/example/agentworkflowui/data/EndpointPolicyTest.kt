package com.example.agentworkflowui.data

import junit.framework.TestCase.assertEquals
import org.junit.Test

class EndpointPolicyTest {
  @Test
  fun normalizesHttpsEndpoint() {
    assertEquals("https://workflow.example:8443", EndpointPolicy.requireHttps(" https://workflow.example:8443/"))
  }

  @Test
  fun rejectsPlaintextAndCredentialBearingEndpoints() {
    expectFailure { EndpointPolicy.requireHttps("http://workflow.example") }
    expectFailure { EndpointPolicy.requireHttps("https://user:secret@workflow.example") }
    expectFailure { EndpointPolicy.requireHttps("https://workflow.example/v1") }
  }

  @Test
  fun permitsOnlyLoopbackHttpForEstablishedTunnel() {
    assertEquals("http://127.0.0.1:43111", EndpointPolicy.requireTunnelEndpoint("http://127.0.0.1:43111"))
    expectFailure { EndpointPolicy.requireTunnelEndpoint("http://relay.example:43111") }
    expectFailure { EndpointPolicy.requireHttps("http://127.0.0.1:43111") }
  }

  private fun expectFailure(action: () -> Unit) {
    try {
      action()
      error("expected endpoint validation failure")
    } catch (_: IllegalArgumentException) {
      // expected
    }
  }
}
