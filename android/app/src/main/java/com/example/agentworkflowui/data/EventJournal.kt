package com.example.agentworkflowui.data

import java.nio.charset.StandardCharsets
import java.util.Base64

/**
 * Durable per-session event sequence and outbox.
 *
 * An event is reserved before it is sent.  A dropped response therefore
 * retries the exact same sequence and payload, while a changed decision gets
 * a new sequence. This uses a small dependency-free line format so JVM tests
 * do not accidentally call Android's org.json stubs.
 */
class EventJournal(private val storage: Storage) {
  interface Storage {
    fun read(): String?
    fun write(value: String)
  }

  /** The event is kept as canonical JSON text so the journal is JVM-testable
   * without depending on Android's org.json stubs. */
  data class Pending(val sessionId: String, val sequence: Int, val key: String,
                     val event: String)

  private data class Session(
    var nextSequence: Int = 1,
    val committed: MutableMap<String, String> = linkedMapOf(),
    val outbox: MutableList<Pending> = mutableListOf(),
  )

  private fun encode(value: String) = Base64.getEncoder().encodeToString(value.toByteArray(StandardCharsets.UTF_8))
  private fun decode(value: String) = String(Base64.getDecoder().decode(value), StandardCharsets.UTF_8)

  private fun load(): MutableMap<String, Session> = runCatching {
    val sessions = linkedMapOf<String, Session>()
    storage.read().orEmpty().lineSequence().filter(String::isNotBlank).forEach { line ->
      val fields = line.split('|')
      require(fields.isNotEmpty())
      val sessionId = decode(fields[1])
      val session = sessions.getOrPut(sessionId) { Session() }
      when (fields[0]) {
        "S" -> session.nextSequence = fields[2].toInt()
        "C" -> session.committed[decode(fields[2])] = decode(fields[3])
        "O" -> session.outbox += Pending(sessionId, fields[2].toInt(), decode(fields[3]), decode(fields[4]))
        else -> error("invalid event journal record")
      }
    }
    sessions
  }.getOrElse { linkedMapOf() }

  private fun persist(sessions: Map<String, Session>) {
    val lines = buildList {
      sessions.toSortedMap().forEach { (sessionId, session) ->
        add("S|${encode(sessionId)}|${session.nextSequence}")
        session.committed.toSortedMap().forEach { (key, answer) ->
          add("C|${encode(sessionId)}|${encode(key)}|${encode(answer)}")
        }
        session.outbox.sortedBy { it.sequence }.forEach { pending ->
          add("O|${encode(sessionId)}|${pending.sequence}|${encode(pending.key)}|${encode(pending.event)}")
        }
      }
    }
    storage.write(lines.joinToString("\n"))
  }

  /** Reserve an event for a changed decision, or return null if already saved. */
  @Synchronized
  fun reserve(sessionId: String, decisionId: String, answer: String,
              binding: String = "",
              event: (Int) -> String): Pending? {
    require(sessionId.isNotBlank() && decisionId.isNotBlank())
    val sessions = load()
    val session = sessions.getOrPut(sessionId) { Session() }
    val committedKey = "$decisionId\u0000$binding"
    if (session.committed[committedKey] == answer) return null
    val sequence = session.nextSequence
    val pending = Pending(sessionId, sequence, "$sessionId:$sequence", event(sequence))
    session.outbox += pending
    session.committed[committedKey] = answer
    session.nextSequence = sequence + 1
    persist(sessions)
    return pending
  }

  @Synchronized
  fun pending(sessionId: String): List<Pending> = load()[sessionId]?.outbox?.sortedBy { it.sequence }.orEmpty()

  @Synchronized
  fun acknowledge(sessionId: String, sequence: Int) {
    val sessions = load()
    sessions[sessionId]?.outbox?.removeIf { it.sequence == sequence }
    persist(sessions)
  }
}
