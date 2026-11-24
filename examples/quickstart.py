"""Evidence Kit quick start — runs every module on synthetic data.

    pip install -e ".[yaml]"
    python examples/quickstart.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent

try:
    import evidence_kit  # noqa: F401
except ImportError:  # allow running from a source checkout without installing
    sys.path.insert(0, str(REPO / "src"))

from evidence_kit.doc_claims import run as check_doc
from evidence_kit.evidence_dedup import dedup_evidence
from evidence_kit.research_ledger import EvidenceSpan, ResearchLedger


def research_ledger_demo() -> None:
    print("== research_ledger")
    led = ResearchLedger()
    price = led.add_subquestion("What does the example service cost per month?",
                                want_sources="official", importance=1)
    region = led.add_subquestion("Is the service available in region X?", importance=2)

    claim = led.add_claim(price.id, "The basic plan costs USD 10 per month", confirmed=True)
    led.attach_span(claim, EvidenceSpan(url="https://example.com/pricing",
                                        quote="Basic: $10/month", stance="supports",
                                        origin="fulltext"))
    led.cover(price.id)

    gap = led.ensure_gap(region.id, "Regional availability of the example service")
    led.record_attempt(gap, ["example service region X"])
    led.record_attempt(gap, ["example service availability map"])

    stop, reason = led.should_stop([{"new_evidence": 1}, {"new_evidence": 0}])
    print(f"stop={stop} reason={reason}")
    print(f"completion={led.completion()}")          # unknowns are reported, not hidden
    print(f"gap stop_reason={gap.stop_reason} tried={gap.queries_tried}")


def dedup_demo() -> None:
    print("== evidence_dedup")
    items = [
        {"url": "https://example.com/pricing", "title": "Pricing plans"},
        {"url": "https://example.com/pricing", "title": "Pricing plans"},       # exact duplicate
        {"url": "https://www.example.com/plans", "title": "Pricing Plans"},     # same domain, same title
        {"url": "https://example.org/review", "title": "Pricing plans"},        # other domain: kept
    ]
    out = dedup_evidence(items)
    print(f"before={out['before']} after={out['after']}")
    for item in out["kept"]:
        print("  kept", item["url"])


def doc_claims_demo() -> None:
    print("== doc_claims")
    report = check_doc(HERE / "sample-doc.md", root=REPO)
    print(json.dumps(report, indent=2))


def reference_ledger_demo() -> None:
    print("== reference_ledger")
    from evidence_kit.reference_ledger import brief_lines, load_instances
    try:
        rows = load_instances(HERE / "reference-ledger.example.yaml")
    except ImportError as exc:
        print(f"skipped: {exc}")
        return
    print(f"{len(rows)} instances: " + ", ".join(f"{r['id']}({r['status']})" for r in rows))
    for line in brief_lines(rows, today="2026-01-20"):
        print(line)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):   # the briefing uses non-ASCII punctuation
        sys.stdout.reconfigure(encoding="utf-8")
    research_ledger_demo()
    dedup_demo()
    doc_claims_demo()
    reference_ledger_demo()
