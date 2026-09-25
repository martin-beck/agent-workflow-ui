package com.example.agentworkflowui.data

import org.json.JSONArray
import org.json.JSONObject

/**
 * Durable per-session event sequence and outbox.
 *
 * An event is reserved before it is sent.  A dropped response therefore
 * retries the exact same sequence and payload, while a changed decision gets
 * a new sequence.  This deliberately does not use the decision's list index:
 * sparse batches and reordered decisions must not create sequence collisions.
 */
class EventJournal(private val storage: Storage) {
  interface Storage {
    fun read(): String?
    fun write(value: String)
  }

  data class Pending(val sessionId: String, val sequence: Int, val key: String,
                     val event: JSONObject)

  private fun root(): JSONObject = runCatching {
    storage.read()?.let { JSONObject(it) }
  }.getOrNull() ?: JSONObject()

  private fun persist(root: JSONObject) = storage.write(root.toString())

  /** Reserve an event for a changed decision, or return null if already saved. */
  @Synchronized
  fun reserve(sessionId: String, decisionId: String, answer: String,
              event: (Int) -> JSONObject): Pending? {
    require(sessionId.isNotBlank() && decisionId.isNotBlank())
    val root = root()
    val session = root.optJSONObject(sessionId) ?: JSONObject().also { root.put(sessionId, it) }
    val committed = session.optJSONObject("committed") ?: JSONObject().also { session.put("committed", it) }
    if (committed.optString(decisionId, "") == answer) return null
    val sequence = session.optInt("next_sequence", 1)
    val payload = event(sequence)
    val key = "$sessionId:$sequence"
    val outbox = session.optJSONArray("outbox") ?: JSONArray().also { session.put("outbox", it) }
    outbox.put(JSONObject().put("sequence", sequence).put("key", key).put("event", payload))
    committed.put(decisionId, answer)
    session.put("next_sequence", sequence + 1)
    persist(root)
    return Pending(sessionId, sequence, key, payload)
  }

  @Synchronized
  fun pending(sessionId: String): List<Pending> {
    val session = root().optJSONObject(sessionId) ?: return emptyList()
    val outbox = session.optJSONArray("outbox") ?: return emptyList()
    return buildList {
      for (index in 0 until outbox.length()) {
        val item = outbox.getJSONObject(index)
        add(Pending(sessionId, item.getInt("sequence"), item.getString("key"), item.getJSONObject("event")))
      }
    }.sortedBy { it.sequence }
  }

  @Synchronized
  fun acknowledge(sessionId: String, sequence: Int) {
    val root = root()
    val session = root.optJSONObject(sessionId) ?: return
    val old = session.optJSONArray("outbox") ?: return
    val next = JSONArray()
    for (index in 0 until old.length()) {
      val item = old.getJSONObject(index)
      if (item.optInt("sequence") != sequence) next.put(item)
    }
    session.put("outbox", next)
    persist(root)
  }
}
