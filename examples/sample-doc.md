# Sample design note

This document carries machine-checkable claims. Run, from the repository root:

    doc-claims --root . examples/sample-doc.md

## Modules

The document checker lives in its own module.
<!-- claim: {"type": "file_exists", "target": "src/evidence_kit/doc_claims.py"} -->

It exposes a console entry point.
<!-- claim: {"type": "grep", "target": "src/evidence_kit/doc_claims.py", "pattern": "def main(", "expect": "present"} -->

The de-duplication module makes no network calls.
<!-- claim: {"type": "grep", "target": "src/evidence_kit/evidence_dedup.py", "pattern": "import urllib.request", "expect": "absent"} -->

## Malformed tags

A broken tag is reported under "skipped", never as drift.
<!-- claim: {"type": "file_exists", target: missing quotes} -->
