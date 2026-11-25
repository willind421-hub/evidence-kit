"""research_ledger — a thin evidence-state layer for iterative research.

Turns "needs more checking" from a sentence into *data that drives the next
action*. Five concepts: Subquestion, Claim, EvidenceSpan, Gap and Conflict.

Deliberately thin: dataclasses + dict serialization + pure decision functions.
No model calls, no files, no search — a research engine injects all of that.
Stop decisions are enforced by the code here, not by an LLM answering YES/NO.

Three completion states (prevents endless loops, so a question with no public
answer is still delivered honestly):
  complete / complete_with_unknowns / insufficient_evidence
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import List, Optional, Tuple

# Subquestion importance: 1 = required (no answer without it) / 2 = normal / 3 = reference.
IMPORTANCE_REQUIRED = 1

# The three completion states.
COMPLETE = "complete"
COMPLETE_WITH_UNKNOWNS = "complete_with_unknowns"
INSUFFICIENT = "insufficient_evidence"

# Source-kind hints — vocabulary for weighting sources per claim type
# (instead of a global "official source always wins" rule).
SOURCE_KINDS = ("official", "independent", "community", "any")


@dataclass
class Subquestion:
    id: str
    text: str
    why: str = ""
    want_sources: str = "any"          # one of SOURCE_KINDS
    success: str = ""                  # what must be confirmed for this to count as covered
    importance: int = 2                # 1=required / 2=normal / 3=reference
    status: str = "open"               # open / covered / blocked


@dataclass
class EvidenceSpan:
    url: str
    title: str = ""
    quote: str = ""                    # verbatim quote from the source (<=600 chars), not a summary
    stance: str = "context"            # supports / refutes / context
    origin: str = "snippet"            # snippet / fulltext

    def __post_init__(self):
        self.quote = str(self.quote or "")[:600]


@dataclass
class Claim:
    id: str
    subq_id: str
    text: str
    status: str = "unconfirmed"        # confirmed / unconfirmed / conflicted
    spans: List[EvidenceSpan] = field(default_factory=list)


@dataclass
class Gap:
    id: str
    subq_id: str
    question: str
    importance: int = 2
    attempts: int = 0
    queries_tried: List[str] = field(default_factory=list)
    required_source_type: str = "any"
    status: str = "open"               # open / resolved / blocked / deferred
    stop_reason: str = ""


@dataclass
class Conflict:
    id: str
    claim_id: str
    positions: List[dict] = field(default_factory=list)   # [{text, url}]
    status: str = "unresolved"         # resolved / unresolved
    winner: str = ""
    rationale: str = ""


class ResearchLedger:
    """Evidence state of one research job — the engine reads and updates it every round."""

    def __init__(self):
        self.subquestions: List[Subquestion] = []
        self.claims: List[Claim] = []
        self.gaps: List[Gap] = []
        self.conflicts: List[Conflict] = []
        self.urls_read: List[str] = []
        self._seq = 0

    def _next_id(self, prefix: str) -> str:
        self._seq += 1
        return f"{prefix}{self._seq}"

    # ---- subquestions ----
    def add_subquestion(self, text: str, *, why: str = "", want_sources: str = "any",
                        success: str = "", importance: int = 2) -> Subquestion:
        want = want_sources if want_sources in SOURCE_KINDS else "any"
        try:
            imp = max(1, min(int(importance), 3))
        except (TypeError, ValueError):
            imp = 2
        sq = Subquestion(self._next_id("sq"), " ".join(str(text or "").split()),
                         why=str(why or ""), want_sources=want,
                         success=str(success or ""), importance=imp)
        if sq.text:
            self.subquestions.append(sq)
        return sq

    def cover(self, subq_id: str) -> None:
        for sq in self.subquestions:
            if sq.id == subq_id:
                sq.status = "covered"
        for g in self.gaps:
            if g.subq_id == subq_id and g.status == "open":
                g.status = "resolved"

    # ---- claims and evidence ----
    def add_claim(self, subq_id: str, text: str, *, confirmed: bool = False) -> Claim:
        c = Claim(self._next_id("c"), subq_id, " ".join(str(text or "").split()),
                  status="confirmed" if confirmed else "unconfirmed")
        self.claims.append(c)
        return c

    def attach_span(self, claim: Claim, span: EvidenceSpan) -> None:
        claim.spans.append(span)
        # Deterministic conflict detection: a claim with a "supports" span that
        # also receives a "refutes" span becomes conflicted.
        stances = {s.stance for s in claim.spans}
        if "supports" in stances and "refutes" in stances and claim.status != "conflicted":
            claim.status = "conflicted"
            self.conflicts.append(Conflict(
                self._next_id("cf"), claim.id,
                positions=[{"text": s.quote[:200], "url": s.url, "stance": s.stance}
                           for s in claim.spans if s.stance in ("supports", "refutes")]))

    # ---- gaps ----
    def ensure_gap(self, subq_id: str, question: str, *, importance: int = 2,
                   required_source_type: str = "any") -> Gap:
        for g in self.gaps:
            if g.subq_id == subq_id and g.status == "open":
                return g
        g = Gap(self._next_id("g"), subq_id, " ".join(str(question or "").split()),
                importance=importance, required_source_type=required_source_type)
        self.gaps.append(g)
        return g

    def record_attempt(self, gap: Gap, queries: List[str]) -> None:
        gap.attempts += 1
        for q in queries or []:
            if q and q not in gap.queries_tried:
                gap.queries_tried.append(q)

    def block_gap(self, gap: Gap, reason: str) -> None:
        gap.status = "blocked"
        gap.stop_reason = str(reason or "")[:200]
        for sq in self.subquestions:
            if sq.id == gap.subq_id and sq.status == "open":
                sq.status = "blocked"

    def open_gaps(self) -> List[Gap]:
        return [g for g in self.gaps if g.status == "open"]

    # ---- decisions (enforced in code — an LLM may only propose) ----
    def should_stop(self, round_stats: List[dict], *, gap_attempt_cap: int = 2,
                    stale_rounds: int = 2) -> Tuple[bool, str]:
        """Stop decision. ``round_stats`` = [{new_evidence: int, new_confirmed: int}, ...] in round order.

        Stop conditions: (1) every required subquestion is covered/blocked and no
        gap is open; (2) the last ``stale_rounds`` rounds produced no new evidence;
        (3) every open gap has reached the attempt cap.
        Round limits and budgets are enforced separately by the engine loop.
        """
        required = [sq for sq in self.subquestions if sq.importance == IMPORTANCE_REQUIRED]
        req_done = all(sq.status != "open" for sq in required) if required else False
        if req_done and not self.open_gaps():
            return True, "required_covered" if self.completion() == COMPLETE else "required_settled"
        if len(round_stats) >= stale_rounds and all(
                (r.get("new_evidence") or 0) == 0 for r in round_stats[-stale_rounds:]):
            return True, "stale_rounds"
        opens = self.open_gaps()
        if opens and all(g.attempts >= gap_attempt_cap for g in opens):
            for g in opens:
                if not g.stop_reason:
                    g.stop_reason = "attempt_cap"
            return True, "gap_attempts_exhausted"
        return False, ""

    def completion(self) -> str:
        """One of the three completion states — deliver honestly even with unknowns (no endless loop)."""
        required = [sq for sq in self.subquestions if sq.importance == IMPORTANCE_REQUIRED]
        has_any_evidence = any(s.url for c in self.claims for s in c.spans)
        if not has_any_evidence:
            return INSUFFICIENT
        unknowns = (self.open_gaps()
                    or [g for g in self.gaps if g.status == "blocked"]
                    or [c for c in self.conflicts if c.status == "unresolved"]
                    or [sq for sq in self.subquestions if sq.status != "covered"]
                    or [c for c in self.claims if c.status != "confirmed"
                        or not any(s.stance == "supports" and s.url for s in c.spans)]
                    or [sq for sq in required
                        if not any(c.subq_id == sq.id for c in self.claims)])
        return COMPLETE_WITH_UNKNOWNS if unknowns else COMPLETE

    # ---- serialization (for job files — no black boxes) ----
    def to_dict(self) -> dict:
        return {
            "subquestions": [asdict(s) for s in self.subquestions],
            "claims": [asdict(c) for c in self.claims],
            "gaps": [asdict(g) for g in self.gaps],
            "conflicts": [asdict(c) for c in self.conflicts],
            "urls_read": list(self.urls_read),
            "completion": self.completion(),
        }
