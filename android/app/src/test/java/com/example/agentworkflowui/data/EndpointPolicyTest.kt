package com.example.agentworkflowui.data

import junit.framework.TestCase.assertEquals
import org.json.JSONObject
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
  fun validatesRendezvousMetadataBeforeRegistration() {
    val qr = JSONObject("""
      {"endpoint":"https://workflow.example:8443",
       "ssh_rendezvous":{"host":"relay.example","port":22,
        "forward_port":43111,"host_key_fingerprint":"SHA256:abc"}}
    """.trimIndent())
    assertEquals("https://workflow.example:8443", EndpointPolicy.validateQr(qr))
    qr.getJSONObject("ssh_rendezvous").put("forward_port", 0)
    expectFailure { EndpointPolicy.validateQr(qr) }
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
