package com.example.agentworkflowui.data

import junit.framework.TestCase.assertEquals
import junit.framework.TestCase.assertFailsWith
import org.json.JSONObject
import org.junit.Test

class EndpointPolicyTest {
  @Test
  fun normalizesHttpsEndpoint() {
    assertEquals("https://workflow.example:8443", EndpointPolicy.requireHttps(" https://workflow.example:8443/"))
  }

  @Test
  fun rejectsPlaintextAndCredentialBearingEndpoints() {
    assertFailsWith<IllegalArgumentException> { EndpointPolicy.requireHttps("http://workflow.example") }
    assertFailsWith<IllegalArgumentException> { EndpointPolicy.requireHttps("https://user:secret@workflow.example") }
    assertFailsWith<IllegalArgumentException> { EndpointPolicy.requireHttps("https://workflow.example/v1") }
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
    assertFailsWith<IllegalArgumentException> { EndpointPolicy.validateQr(qr) }
  }
}
