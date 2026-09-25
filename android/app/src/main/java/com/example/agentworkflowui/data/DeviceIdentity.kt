package com.example.agentworkflowui.data

import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import com.jcraft.jsch.Identity
import com.jcraft.jsch.JSchException
import java.io.ByteArrayOutputStream
import java.io.DataOutputStream
import java.math.BigInteger
import java.security.Signature
import java.security.KeyPairGenerator
import java.security.KeyStore
import java.security.interfaces.ECPublicKey
import org.json.JSONObject

/** Device key is generated locally and never leaves Android Keystore. */
object DeviceIdentity {
  private const val alias = "agent-workflow-ui-device"

  private fun keyPair(): java.security.KeyPair {
    val store = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
    if (!store.containsAlias(alias)) {
      KeyPairGenerator.getInstance(KeyProperties.KEY_ALGORITHM_EC, "AndroidKeyStore").apply {
        initialize(KeyGenParameterSpec.Builder(alias, KeyProperties.PURPOSE_SIGN or KeyProperties.PURPOSE_VERIFY)
          .setDigests(KeyProperties.DIGEST_SHA256).build())
        generateKeyPair()
      }
    }
    val certificate = store.getCertificate(alias)
    return java.security.KeyPair(certificate.publicKey, store.getKey(alias, null) as java.security.PrivateKey)
  }

  /** OpenSSH public key; the corresponding private key never leaves Android Keystore. */
  fun publicKey(): String {
    val public = keyPair().public as ECPublicKey
    val blob = ByteArrayOutputStream()
    DataOutputStream(blob).use { out ->
      out.writeSshString("ecdsa-sha2-nistp256".toByteArray())
      out.writeSshString("nistp256".toByteArray())
      val point = byteArrayOf(4) + public.w.affineX.toFixed(32) + public.w.affineY.toFixed(32)
      out.writeSshString(point)
    }
    return "ecdsa-sha2-nistp256 ${Base64.encodeToString(blob.toByteArray(), Base64.NO_WRAP)} awui-android"
  }

  /** Proof binds registration consent to this project, one-time token, and pinned SSH host key. */
  fun enrollmentProof(qr: JSONObject): String {
    val fields = listOf("project_id", "bootstrap_id", "nonce", "expires_at")
    val rendezvous = qr.optJSONObject("ssh_rendezvous")
    val values = fields.map { qr.optString(it, "") } + rendezvous?.optString("host_key_fingerprint", "").orEmpty()
    val message = "awui-android-enrollment-v1\n" + values.joinToString("\n")
    return signMessage(message.toByteArray(Charsets.UTF_8))
  }

  fun sshSessionProof(challenge: JSONObject): String {
    val values = listOf("project_id", "device_id", "challenge_id", "nonce", "expires_at")
      .map { challenge.getString(it) }
    val message = "awui-android-session-v1\n" + values.joinToString("\n")
    return signMessage(message.toByteArray(Charsets.UTF_8))
  }

  private fun signMessage(message: ByteArray): String {
    val signer = Signature.getInstance("SHA256withECDSA")
    signer.initSign(keyPair().private)
    signer.update(message)
    return Base64.encodeToString(signer.sign(), Base64.NO_WRAP)
  }

  /** JSch adapter signs SSH authentication challenges inside Android Keystore. */
  fun jschIdentity(): Identity = object : Identity {
    override fun setPassphrase(passphrase: ByteArray?): Boolean = passphrase == null || passphrase.isEmpty()
    override fun getPublicKeyBlob(): ByteArray = Base64.decode(publicKey().split(" ")[1], Base64.NO_WRAP)
    override fun getSignature(data: ByteArray): ByteArray = getSignature(data, "ecdsa-sha2-nistp256")
    override fun getSignature(data: ByteArray, alg: String): ByteArray {
      require(alg == "ecdsa-sha2-nistp256") { "unsupported SSH signature algorithm" }
      val signer = Signature.getInstance("SHA256withECDSA")
      signer.initSign(keyPair().private)
      signer.update(data)
      val der = signer.sign()
      val (r, s) = decodeDerSignature(der)
      val inner = ByteArrayOutputStream()
      DataOutputStream(inner).use { out ->
        out.writeSshString(alg.toByteArray())
        out.writeSshString(r.toSshMpInt())
        out.writeSshString(s.toSshMpInt())
      }
      return inner.toByteArray()
    }
    override fun getAlgName(): String = "ecdsa-sha2-nistp256"
    override fun getName(): String = alias
    override fun isEncrypted(): Boolean = false
    override fun clear() = Unit
  }

  private fun decodeDerSignature(bytes: ByteArray): Pair<BigInteger, BigInteger> {
    require(bytes.size >= 8 && bytes[0] == 0x30.toByte())
    var offset = 2
    fun integer(): BigInteger {
      require(bytes[offset++] == 0x02.toByte())
      val size = bytes[offset++].toInt() and 0xff
      require(size in 1..33 && offset + size <= bytes.size)
      val result = BigInteger(1, bytes.copyOfRange(offset, offset + size))
      offset += size
      return result
    }
    val r = integer()
    val s = integer()
    require(offset == bytes.size)
    return r to s
  }

  private fun BigInteger.toFixed(size: Int): ByteArray {
    val source = toByteArray().let { if (it.size > size) it.copyOfRange(it.size - size, it.size) else it }
    return ByteArray(size - source.size) + source
  }

  private fun BigInteger.toSshMpInt(): ByteArray = toByteArray()

  private fun DataOutputStream.writeSshString(value: ByteArray) {
    writeInt(value.size)
    write(value)
  }
}
