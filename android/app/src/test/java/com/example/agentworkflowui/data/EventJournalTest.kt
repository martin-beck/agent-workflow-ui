package com.example.agentworkflowui.data

import junit.framework.TestCase.assertEquals
import junit.framework.TestCase.assertNotNull
import junit.framework.TestCase.assertNull
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
    assertEquals(pending.event, retry.event)
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

  @Test
  fun sameDecisionAndAnswerOnNewRevisionGetsAnEvent() {
    val journal = EventJournal(Memory())
    journal.reserve("session", "D-1", "A", binding = "1:sha256:a") { event(it, "D-1", "A") }
    journal.acknowledge("session", 1)
    val next = journal.reserve("session", "D-1", "A", binding = "2:sha256:b") { event(it, "D-1", "A") }
    assertNotNull(next)
    assertEquals(2, next!!.sequence)
  }

  private fun event(sequence: Int, decisionId: String, answer: String) =
    "{\"sequence\":$sequence,\"payload\":{\"decision_id\":\"$decisionId\",\"answer\":\"$answer\"}}"
}
