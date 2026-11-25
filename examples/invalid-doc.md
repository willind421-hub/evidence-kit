# Expected failure

A malformed claim is visible under `skipped` and makes verification fail (exit 1).
It must not silently turn an unchecked document into a passing report.

<!-- claim: {"type": "file_exists", target: missing quotes} -->
