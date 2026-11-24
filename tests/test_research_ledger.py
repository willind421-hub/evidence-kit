"""research_ledger tests — state transitions and decisions are enforced in code.

Stopping and completion are decided by these functions, not by an LLM answering
YES/NO. If these break, "unknown" goes back to being a sentence instead of data.
"""
from __future__ import annotations

from evidence_kit.research_ledger import (
    COMPLETE, COMPLETE_WITH_UNKNOWNS, INSUFFICIENT,
    EvidenceSpan, ResearchLedger,
)


def _ledger_one_subq(importance=1):
    led = ResearchLedger()
    sq = led.add_subquestion("Annual fee of the example developer program", want_sources="official",
                             success="fee confirmed in USD", importance=importance)
    return led, sq


def test_confirmed_claim_and_cover_gives_complete():
    led, sq = _ledger_one_subq()
    c = led.add_claim(sq.id, "The annual fee is USD 99", confirmed=True)
    led.attach_span(c, EvidenceSpan(url="https://example.com/programs/",
                                    quote="US$99 per membership year", stance="supports",
                                    origin="fulltext"))
    led.cover(sq.id)
    assert led.completion() == COMPLETE


def test_open_gap_gives_complete_with_unknowns():
    led, sq = _ledger_one_subq()
    c = led.add_claim(sq.id, "The annual fee is USD 99", confirmed=True)
    led.attach_span(c, EvidenceSpan(url="https://x", stance="supports"))
    led.cover(sq.id)
    led2sq = led.add_subquestion("Can payouts be received in region X?", importance=2)
    led.ensure_gap(led2sq.id, "Payout availability for region X accounts")
    assert led.completion() == COMPLETE_WITH_UNKNOWNS


def test_no_evidence_gives_insufficient():
    led, _ = _ledger_one_subq(importance=1)
    assert led.completion() == INSUFFICIENT


def test_conflict_detected_when_supports_meets_refutes():
    led, sq = _ledger_one_subq()
    c = led.add_claim(sq.id, "The example API is free")
    led.attach_span(c, EvidenceSpan(url="https://a", quote="A free tier exists", stance="supports"))
    led.attach_span(c, EvidenceSpan(url="https://b", quote="$12,000 per month", stance="refutes"))
    assert c.status == "conflicted"
    assert len(led.conflicts) == 1 and led.conflicts[0].status == "unresolved"
    assert led.completion() == COMPLETE_WITH_UNKNOWNS   # delivered honestly, no forced winner


def test_should_stop_required_covered():
    led, sq = _ledger_one_subq()
    c = led.add_claim(sq.id, "confirmed", confirmed=True)
    led.attach_span(c, EvidenceSpan(url="https://x", stance="supports"))
    led.cover(sq.id)
    stop, reason = led.should_stop([{"new_evidence": 3}])
    assert stop and reason == "required_covered"


def test_should_stop_stale_rounds():
    led, _ = _ledger_one_subq()
    stop, reason = led.should_stop([{"new_evidence": 0}, {"new_evidence": 0}])
    assert stop and reason == "stale_rounds"   # no endless loop on questions without public info


def test_should_stop_gap_attempt_cap():
    led, sq = _ledger_one_subq()
    g = led.ensure_gap(sq.id, "something not found")
    led.record_attempt(g, ["q1"])
    led.record_attempt(g, ["q2"])
    stop, reason = led.should_stop([{"new_evidence": 5}])
    assert stop and reason == "gap_attempts_exhausted"
    assert g.stop_reason == "attempt_cap"
    assert g.queries_tried == ["q1", "q2"]     # what was tried is kept as data


def test_blocked_gap_records_reason_and_blocks_subq():
    led, sq = _ledger_one_subq()
    g = led.ensure_gap(sq.id, "check the official page")
    led.block_gap(g, "[blocked:policy] login wall")
    assert g.status == "blocked" and "blocked" in g.stop_reason
    assert sq.status == "blocked"
    # A required question is blocked and there is no evidence: "insufficient" is the
    # honest state (not complete_with_unknowns).
    assert led.completion() == INSUFFICIENT


def test_blocked_gap_with_partial_evidence_is_unknowns():
    led, sq = _ledger_one_subq()
    c = led.add_claim(sq.id, "partially confirmed", confirmed=True)
    led.attach_span(c, EvidenceSpan(url="https://x", stance="supports"))
    sq2 = led.add_subquestion("another, blocked question", importance=2)
    g = led.ensure_gap(sq2.id, "check the official page")
    led.block_gap(g, "[blocked:policy] login wall")
    assert led.completion() == COMPLETE_WITH_UNKNOWNS


def test_ensure_gap_is_idempotent_per_open_subq():
    led, sq = _ledger_one_subq()
    g1 = led.ensure_gap(sq.id, "question")
    g2 = led.ensure_gap(sq.id, "question, rephrased")
    assert g1 is g2 and len(led.gaps) == 1


def test_to_dict_roundtrip_fields():
    led, sq = _ledger_one_subq()
    led.ensure_gap(sq.id, "needs checking")
    d = led.to_dict()
    assert d["completion"] == INSUFFICIENT
    assert d["subquestions"][0]["want_sources"] == "official"
    assert d["gaps"][0]["status"] == "open"
