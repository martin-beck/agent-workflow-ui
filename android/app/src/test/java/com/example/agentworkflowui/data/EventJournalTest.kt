package com.example.agentworkflowui.data

import junit.framework.TestCase.assertEquals
import junit.framework.TestCase.assertNotNull
import junit.framework.TestCase.assertNull
import org.json.JSONObject
import org.junit.Test

class EventJournalTest {
  private class Memory : EventJournal.Storage {
    var value: String? = null
    override fun read() = value
    override fun write(value: String) { this.value = value }
  }

  @Test
  fun sparseAnswersStartAtOneAndAdvanceIndependentlyOfDecisionIndex() {
    val storage = Memory()
    val journal = EventJournal(storage)
    val first = journal.reserve("session", "D-2", "B") { sequence -> event(sequence, "D-2", "B") }
    val second = journal.reserve("session", "D-3", "C") { sequence -> event(sequence, "D-3", "C") }
    assertEquals(1, first!!.sequence)
    assertEquals(2, second!!.sequence)
    assertEquals(listOf(1, 2), journal.pending("session").map { it.sequence })
  }

  @Test
  fun repeatedSaveOfSameDecisionProducesNoNewEvent() {
    val journal = EventJournal(Memory())
    assertNotNull(journal.reserve("session", "D-1", "A") { event(it, "D-1", "A") })
    assertNull(journal.reserve("session", "D-1", "A") { event(it, "D-1", "A") })
    assertEquals(listOf(1), journal.pending("session").map { it.sequence })
  }

  @Test
  fun aFailedSendCanBeRetriedWithSameSequenceAndAcked() {
    val storage = Memory()
    val journal = EventJournal(storage)
    val pending = journal.reserve("session", "D-1", "A") { event(it, "D-1", "A") }!!
    // Recreate the journal to model an app process death between send and ack.
    val retry = EventJournal(storage).pending("session").single()
    assertEquals(pending.sequence, retry.sequence)
    assertEquals(pending.event.toString(), retry.event.toString())
    EventJournal(storage).acknowledge("session", retry.sequence)
    assertEquals(emptyList<EventJournal.Pending>(), EventJournal(storage).pending("session"))
  }

  @Test
  fun editingAfterSaveGetsAnewSequence() {
    val journal = EventJournal(Memory())
    journal.reserve("session", "D-1", "A") { event(it, "D-1", "A") }
    journal.acknowledge("session", 1)
    val edited = journal.reserve("session", "D-1", "B") { event(it, "D-1", "B") }!!
    assertEquals(2, edited.sequence)
  }

  private fun event(sequence: Int, decisionId: String, answer: String) =
    JSONObject().put("sequence", sequence).put("payload",
      JSONObject().put("decision_id", decisionId).put("answer", answer))
}
