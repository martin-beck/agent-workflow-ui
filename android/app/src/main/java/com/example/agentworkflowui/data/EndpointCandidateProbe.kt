package com.example.agentworkflowui.data

import java.net.InetSocketAddress
import java.net.Socket

/** The Android device is the authority on reachability; host-side discovery is advisory. */
data class SshEndpointCandidate(
  val candidateId: String,
  val host: String,
  val port: Int,
  val priority: Int,
  val hostKeyFingerprints: List<String>,
  val expiresAtEpochSeconds: Long? = null,
)

data class CandidateProbeResult(
  val candidate: SshEndpointCandidate,
  val reachable: Boolean,
  val failureCode: String? = null,
)

fun interface CandidateDialer {
  fun connect(host: String, port: Int, timeoutMillis: Int)
}

object SocketCandidateDialer : CandidateDialer {
  override fun connect(host: String, port: Int, timeoutMillis: Int) {
    Socket().use { socket -> socket.connect(InetSocketAddress(host, port), timeoutMillis) }
  }
}

/** Performs bounded TCP reachability probes and retains per-candidate reasons.
 * SSH host-key verification belongs to the tunnel handshake (AR-0121); this
 * probe never treats TCP reachability as authentication or consent.
 */
class EndpointCandidateProbe(private val dialer: CandidateDialer = SocketCandidateDialer) {
  fun probe(candidates: List<SshEndpointCandidate>, nowEpochSeconds: Long,
            timeoutMillis: Int = 2_500): List<CandidateProbeResult> {
    require(timeoutMillis in 100..10_000)
    return candidates.sortedWith(compareBy<SshEndpointCandidate> { it.priority }.thenBy { it.candidateId })
      .map { candidate ->
        if (candidate.port !in 1..65535 || candidate.host.isBlank() || candidate.host.any { it.isWhitespace() }) {
          CandidateProbeResult(candidate, false, "invalid_candidate")
        } else if (candidate.expiresAtEpochSeconds?.let { it <= nowEpochSeconds } == true) {
          CandidateProbeResult(candidate, false, "candidate_expired")
        } else if (candidate.hostKeyFingerprints.isEmpty()) {
          CandidateProbeResult(candidate, false, "host_key_fingerprint_missing")
        } else {
          try {
            dialer.connect(candidate.host, candidate.port, timeoutMillis)
            CandidateProbeResult(candidate, true)
          } catch (_: Exception) {
            CandidateProbeResult(candidate, false, "connection_failed")
          }
        }
      }
  }
}
