"""doc_claims — check machine-readable claims embedded in Markdown against a source tree.

Documentation tends to claim "X exists" or "Y is wired up". The checkable subset
of those claims is tagged in the document, and this module compares the tags with
the actual files. A mismatch is *drift* — over-reporting and documentation rot are
caught without a human audit.

Tag convention (a single-line HTML comment in Markdown — invisible when rendered,
does not break the document)::

  <!-- claim: {"type": "file_exists", "target": "src/pkg/module.py"} -->
  <!-- claim: {"type": "grep", "target": "src/pkg/module.py", "pattern": "def load", "expect": "present"} -->

Contract:
- Only two types: ``file_exists`` / ``grep`` (``expect``: ``present`` | ``absent``,
  default ``present``). Running tests or commands is deliberately not part of
  the convention — no dead fields, no side effects.
- Read-only: matched text is not included in reports. Boolean results can still
  disclose content when a caller controls patterns (a boolean oracle). Grep is
  disabled unless trusted caller configuration allowlists exact target files.
- ``target`` is confined to the root directory; a target outside the root is
  refused.
- Parse failures, unterminated tags and missing fields go to ``skipped``, not
  ``drifts``, but fail the report. A document with zero checks also fails.
- No auto-fix: nothing in the documents or code is modified. Report only.

Output follows a verify-style contract: JSON ``{ok, checked, drifts, skipped}``
and exit code 0 (checks passed) / 1 (drift, skipped, no checks, unreadable document).
This checks tagged file/substring assertions, not program behavior or security.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Iterable, List, Optional

_TAG_START_RE = re.compile(r"<!--\s*claim:\s*")
_HEADING_RE = re.compile(r"^(#{2,3})\s+(.*)")
_VALID_TYPES = ("file_exists", "grep")


def _root_path(root) -> Path:
    return Path(root) if root is not None else Path.cwd()


def parse_claims(text: str):
    """Document text -> list of claims.

    Only the single-line HTML comment form is matched (prose that merely contains
    "claim:" is not parsed). Each claim gets its line number and the nearest
    ``##``/``###`` heading above it as ``section``.
    """
    claims, heading = [], ""
    for lineno, line in enumerate(text.splitlines(), start=1):
        h = _HEADING_RE.match(line.strip())
        if h:
            heading = h.group(2).strip()[:60]
        starts = list(_TAG_START_RE.finditer(line))
        for idx, match in enumerate(starts):
            end = starts[idx + 1].start() if idx + 1 < len(starts) else len(line)
            payload, closed, _ = line[match.end():end].partition("-->")
            try:
                obj = json.loads(payload) if closed else None
            except (ValueError, TypeError):
                obj = None
            if not isinstance(obj, dict):
                claims.append({"line": lineno, "section": heading, "error": "parse"})
                continue
            obj["line"] = lineno
            obj["section"] = heading
            claims.append(obj)
    return claims


def _safe_target(target, root=None) -> Path | None:
    """Relative ``target`` -> absolute path inside ``root``. ``None`` if outside (check refused)."""
    if not isinstance(target, str) or not target.strip():
        return None
    base = _root_path(root).resolve()
    p = (base / target.strip()).resolve()
    try:
        p.relative_to(base)
    except ValueError:
        return None
    return p


def check_claim(claim: dict, root=None, *, grep_allowlist=()):
    """Check one claim -> ``(status, actual)``; status is ``ok`` | ``drift`` | ``skipped``.

    ``actual`` is a boolean-style description, not matched file text; this is not
    a confidentiality guarantee. Grep targets require a trusted allowlist.
    ``root`` defaults to the current working directory.
    """
    ctype = claim.get("type")
    if claim.get("error") or ctype not in _VALID_TYPES:
        return "skipped", "tag parse failed or unsupported type"
    p = _safe_target(claim.get("target"), root)
    if p is None:
        return "skipped", "target missing or outside root"
    if ctype == "file_exists":
        return ("ok", "exists") if p.is_file() else ("drift", "file missing")
    # grep
    pattern = claim.get("pattern")
    if not isinstance(pattern, str) or not pattern:
        return "skipped", "pattern missing"
    expect = claim.get("expect", "present")
    if expect not in ("present", "absent"):
        return "skipped", "unsupported expect value"
    # Policy comes from the trusted caller, never from document tags.
    # Boolean matches disclose content too; root confinement alone is insufficient.
    allowed = {_safe_target(target, root) for target in grep_allowlist}
    if p not in allowed:
        return "skipped", "grep target not allowlisted"
    try:
        found = pattern in p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ("drift", "file read failed (missing?)")
    if (expect == "present") == found:
        return "ok", ("pattern present" if found else "pattern absent (as expected)")
    return "drift", ("pattern absent" if expect == "present" else "pattern present (expected absent)")


def run(doc_path, root=None, *, grep_allowlist=()) -> dict:
    """Check every claim in one Markdown document.

    Returns ``{"ok", "checked", "drifts", "skipped"}`` (plus ``"error"`` when the
    document cannot be read, in which case ``ok`` is ``False``). A document with
    no tags yields ``checked == 0`` and an empty ``skipped`` list; a broken tag
    yields ``checked == 0`` with one ``skipped`` row — the two cases stay distinct.
    """
    doc = Path(doc_path)
    try:
        text = doc.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return {"ok": False, "checked": 0, "drifts": [], "skipped": [],
                "error": f"failed to read document: {doc}"}
    checked, drifts, skipped = 0, [], []
    grep_allowlist = tuple(grep_allowlist)
    for claim in parse_claims(text):
        status, actual = check_claim(claim, root, grep_allowlist=grep_allowlist)
        row = {"section": claim.get("section", ""), "line": claim.get("line"),
               "type": claim.get("type"), "target": claim.get("target"),
               "actual": actual}
        if status == "ok":
            checked += 1
        elif status == "drift":
            checked += 1
            drifts.append(row)
        else:
            skipped.append(row)
    return {"ok": checked > 0 and not drifts and not skipped, "checked": checked, "drifts": drifts,
            "skipped": skipped}


def run_many(doc_paths: Iterable, root=None, *, grep_allowlist=()) -> dict:
    """Run :func:`run` over several documents and merge the reports.

    Same keys as :func:`run`; every drift/skipped row gains a ``"doc"`` field, and
    unreadable documents are listed under ``"errors"`` (which makes ``ok`` False).
    """
    checked, drifts, skipped, errors, all_ok = 0, [], [], [], True
    grep_allowlist = tuple(grep_allowlist)
    for doc in doc_paths:
        report = run(doc, root, grep_allowlist=grep_allowlist)
        all_ok = all_ok and report["ok"]
        if "error" in report:
            errors.append(report["error"])
        checked += report["checked"]
        drifts.extend({"doc": str(doc), **row} for row in report["drifts"])
        skipped.extend({"doc": str(doc), **row} for row in report["skipped"])
    out = {"ok": all_ok and checked > 0, "checked": checked,
           "drifts": drifts, "skipped": skipped}
    if errors:
        out["errors"] = errors
    return out


def main(argv: Optional[List[str]] = None) -> int:
    """Console entry point: ``doc-claims [--root DIR] FILE [FILE ...]``."""
    parser = argparse.ArgumentParser(
        prog="doc-claims",
        description="Check <!-- claim: {...} --> tags in Markdown files against a source tree.")
    parser.add_argument("files", nargs="+", help="Markdown documents to check")
    parser.add_argument("--root", default=".",
                        help="directory that claim targets are resolved against "
                             "(targets outside it are refused; default: current directory)")
    parser.add_argument("--allow-grep", action="append", default=[], metavar="TARGET",
                        help="allow content checks of this exact root-relative file (repeatable; "
                             "default: none). Set only from trusted configuration, not documents; "
                             "boolean results can disclose allowed file contents")
    args = parser.parse_args(argv)
    if len(args.files) == 1:
        report = run(args.files[0], args.root, grep_allowlist=args.allow_grep)
    else:
        report = run_many(args.files, args.root, grep_allowlist=args.allow_grep)
    try:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    except UnicodeEncodeError:   # e.g. a legacy Windows code page on a pipe
        print(json.dumps(report, ensure_ascii=True, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
