package com.example.agentworkflowui.data

import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import java.security.KeyPairGenerator
import java.security.KeyStore

/** Device key is generated locally and never leaves Android Keystore. */
object DeviceIdentity {
  private const val alias = "agent-workflow-ui-device"

  fun publicKey(): String {
    val store = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
    if (!store.containsAlias(alias)) {
      KeyPairGenerator.getInstance(KeyProperties.KEY_ALGORITHM_EC, "AndroidKeyStore").apply {
        initialize(KeyGenParameterSpec.Builder(alias, KeyProperties.PURPOSE_SIGN or KeyProperties.PURPOSE_VERIFY)
          .setDigests(KeyProperties.DIGEST_SHA256).build())
        generateKeyPair()
      }
    }
    return Base64.encodeToString(store.getCertificate(alias).publicKey.encoded, Base64.NO_WRAP)
  }
}
