"""Evidence Kit — a small toolkit for keeping research claims and documentation honest.

Modules:

- :mod:`evidence_kit.research_ledger` — questions, claims, evidence spans, gaps and
  conflicts with code-enforced stop/completion decisions.
- :mod:`evidence_kit.evidence_dedup` — exact + same-domain title de-duplication of evidence.
- :mod:`evidence_kit.doc_claims` — check ``<!-- claim: {...} -->`` tags in Markdown
  against a source tree (also the ``doc-claims`` console script).
- :mod:`evidence_kit.reference_ledger` — read-only loader for a YAML reference index
  (needs the ``yaml`` extra).
"""

__version__ = "0.1.0"

__all__ = ["__version__"]
