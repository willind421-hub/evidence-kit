# Sample design note

This document carries machine-checkable claims. Run, from the repository root:

    doc-claims --root . --allow-grep src/evidence_kit/doc_claims.py --allow-grep src/evidence_kit/evidence_dedup.py examples/sample-doc.md

## Modules

The document checker lives in its own module.
<!-- claim: {"type": "file_exists", "target": "src/evidence_kit/doc_claims.py"} -->

It exposes a console entry point.
<!-- claim: {"type": "grep", "target": "src/evidence_kit/doc_claims.py", "pattern": "def main(", "expect": "present"} -->

The de-duplication module has no literal `import urllib.request` statement.
This substring check does not prove absence of network activity or test behavior.
<!-- claim: {"type": "grep", "target": "src/evidence_kit/evidence_dedup.py", "pattern": "import urllib.request", "expect": "absent"} -->

Grep authorization above comes from trusted caller configuration, not these tags.
Boolean matches can disclose allowed file contents; do not allowlist secrets.
For an expected failure, run `doc-claims --root . examples/invalid-doc.md` (exit 1).
