package com.example.agentworkflowui.data

import junit.framework.TestCase.assertEquals
import junit.framework.TestCase.assertFalse
import junit.framework.TestCase.assertTrue
import org.junit.Test

class EndpointCandidateProbeTest {
  @Test fun probesInPriorityOrderAndKeepsPerCandidateFailure() {
    val attempted = mutableListOf<String>()
    val probe = EndpointCandidateProbe(CandidateDialer { host, _, _ ->
      attempted += host
      if (host == "offline.example") error("offline")
    })
    val results = probe.probe(listOf(candidate("offline.example", 20), candidate("relay.example", 10)), 100)
    assertEquals(listOf("relay.example", "offline.example"), attempted)
    assertTrue(results[0].reachable)
    assertEquals("connection_failed", results[1].failureCode)
  }

  @Test fun rejectsExpiredOrUnpinnedCandidateWithoutDialing() {
    var calls = 0
    val probe = EndpointCandidateProbe(CandidateDialer { _, _, _ -> calls++ })
    val expired = candidate("expired", 1).copy(expiresAtEpochSeconds = 4)
    val unpinned = candidate("untrusted", 2).copy(hostKeyFingerprints = emptyList())
    val results = probe.probe(listOf(expired, unpinned), 5)
    assertFalse(results[0].reachable)
    assertEquals("candidate_expired", results[0].failureCode)
    assertEquals("host_key_fingerprint_missing", results[1].failureCode)
    assertEquals(0, calls)
  }

  private fun candidate(host: String, priority: Int) = SshEndpointCandidate(
    "id-$host", host, 22, priority, listOf("SHA256:knownHostKey"),
  )
}
