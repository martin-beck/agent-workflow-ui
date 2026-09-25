package com.example.agentworkflowui.data

import android.util.Base64
import com.jcraft.jsch.HostKey
import com.jcraft.jsch.HostKeyRepository
import com.jcraft.jsch.JSch
import com.jcraft.jsch.Session
import java.security.MessageDigest
import org.json.JSONObject

/** A local-only HTTP endpoint carried inside a pinned SSH connection. */
data class SshTunnelHandle(val endpoint: String, private val session: Session, private val localPort: Int) : AutoCloseable {
  val connected: Boolean get() = session.isConnected
  override fun close() {
    runCatching { session.delPortForwardingL(localPort) }
    if (session.isConnected) session.disconnect()
  }
}

/** SSH client for the loopback-only service port allocated by the workflow host. */
class SshTunnelManager(private val connectTimeoutMs: Int = 10_000) {
  fun connect(qr: JSONObject): SshTunnelHandle {
    val candidate = qr.optJSONObject("ssh_rendezvous")
      ?: error("registration has no SSH rendezvous candidate")
    val host = candidate.getString("host")
    val port = candidate.getInt("port")
    val user = candidate.getString("username")
    val forwardPort = candidate.getInt("forward_port")
    val fingerprint = candidate.getString("host_key_fingerprint")
    require(host.isNotBlank() && !host.startsWith("-") && port in 1..65535 && forwardPort in 1..65535)
    require(Regex("SHA256:[A-Za-z0-9+/]{43}").matches(fingerprint))

    val jsch = JSch()
    jsch.addIdentity(DeviceIdentity.jschIdentity(), null)
    val session = jsch.getSession(user, host, port)
    session.setConfig("PreferredAuthentications", "publickey")
    session.setConfig("StrictHostKeyChecking", "yes")
    session.hostKeyRepository = PinnedHostKeyRepository(fingerprint)
    try {
      session.connect(connectTimeoutMs)
      val localPort = session.setPortForwardingL("127.0.0.1", 0, "127.0.0.1", forwardPort)
      return SshTunnelHandle("http://127.0.0.1:$localPort", session, localPort)
    } catch (failure: Throwable) {
      if (session.isConnected) session.disconnect()
      throw failure
    }
  }
}

/** Fails closed on every host key except the SHA256 fingerprint confirmed in the QR. */
class PinnedHostKeyRepository(private val expectedFingerprint: String) : HostKeyRepository {
  override fun check(host: String, key: ByteArray): Int {
    val actual = "SHA256:" + Base64.encodeToString(MessageDigest.getInstance("SHA-256").digest(key), Base64.NO_WRAP)
      .trimEnd('=')
    return if (MessageDigest.isEqual(actual.toByteArray(), expectedFingerprint.toByteArray())) HostKeyRepository.OK else HostKeyRepository.CHANGED
  }
  override fun add(hostkey: HostKey, ui: com.jcraft.jsch.UserInfo?) = Unit
  override fun remove(host: String?, type: String?) = Unit
  override fun remove(host: String?, type: String?, key: ByteArray?) = Unit
  override fun getKnownHostsRepositoryID(): String = "AWUI-QR-host-key-pin"
  override fun getHostKey(): Array<HostKey> = emptyArray()
  override fun getHostKey(host: String?, type: String?): Array<HostKey> = emptyArray()
}
