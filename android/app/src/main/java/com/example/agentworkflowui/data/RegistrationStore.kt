package com.example.agentworkflowui.data

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import java.nio.charset.StandardCharsets
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

/**
 * Stores the short-lived service credential encrypted with a device-bound
 * Android Keystore AES key.  The credential is never put in QR data, logs, or
 * ordinary plaintext preferences.
 */
class RegistrationStore(context: Context) {
  private val preferences = context.getSharedPreferences(PREFERENCES, Context.MODE_PRIVATE)

  fun load(): Registration? {
    val encoded = preferences.getString(PAYLOAD, null) ?: return null
    return runCatching {
      val bytes = decrypt(Base64.decode(encoded, Base64.NO_WRAP))
      val values = String(bytes, StandardCharsets.UTF_8).split("\u0000", limit = 4)
      require(values.size == 4)
      Registration(values[0], values[1], values[2], values[3])
    }.getOrNull()
  }

  fun save(value: Registration) {
    val plain = listOf(value.projectId, value.endpoint, value.deviceId, value.credential)
      .joinToString("\u0000").toByteArray(StandardCharsets.UTF_8)
    preferences.edit().putString(PAYLOAD, Base64.encodeToString(encrypt(plain), Base64.NO_WRAP)).apply()
  }

  fun clear() = preferences.edit().clear().apply()

  private fun encrypt(plain: ByteArray): ByteArray {
    val cipher = Cipher.getInstance("AES/GCM/NoPadding")
    cipher.init(Cipher.ENCRYPT_MODE, key())
    return cipher.iv + cipher.doFinal(plain)
  }

  private fun decrypt(value: ByteArray): ByteArray {
    require(value.size > GCM_IV_BYTES)
    val cipher = Cipher.getInstance("AES/GCM/NoPadding")
    cipher.init(Cipher.DECRYPT_MODE, key(), GCMParameterSpec(128, value.copyOfRange(0, GCM_IV_BYTES)))
    return cipher.doFinal(value.copyOfRange(GCM_IV_BYTES, value.size))
  }

  private fun key(): SecretKey {
    val store = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
    if (!store.containsAlias(KEY_ALIAS)) {
      KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore").apply {
        init(KeyGenParameterSpec.Builder(KEY_ALIAS, KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
          .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
          .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
          .setRandomizedEncryptionRequired(true)
          .build())
        generateKey()
      }
    }
    return (store.getEntry(KEY_ALIAS, null) as KeyStore.SecretKeyEntry).secretKey
  }

  data class Registration(val projectId: String, val endpoint: String,
                          val deviceId: String, val credential: String)

  companion object {
    private const val PREFERENCES = "workflow-ui-registration"
    private const val PAYLOAD = "encrypted-registration"
    private const val KEY_ALIAS = "agent-workflow-ui-registration"
    private const val GCM_IV_BYTES = 12
  }
}
