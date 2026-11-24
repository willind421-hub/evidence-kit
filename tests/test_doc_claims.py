"""doc_claims contract — parser and guards.

Tags are matched only in the single-line HTML comment form (prose containing
"claim:" is not parsed), targets are confined to the root directory, results are
boolean descriptions only (no file contents), and parse failures are *skipped*,
not reported as drift (silence over false alarms).
"""
from __future__ import annotations

import io
import json

from evidence_kit import doc_claims as vdc


def _root_with_module(tmp_path):
    root = tmp_path / "root"
    (root / "pkg").mkdir(parents=True)
    (root / "pkg" / "ledger.py").write_text("def load_assets():\n    return []\n", encoding="utf-8")
    return root


# ---- ported (synthetic) -------------------------------------------------------

def test_parse_only_html_comment_form():
    text = "\n".join([
        "## 23. Scheduler layer",
        '<!-- claim: {"type": "file_exists", "target": "pkg/scheduler.py"} -->',
        "Extracted claim: research panel blah — prose is not a tag",
        'claim: {"type": "grep"} — not a comment, must not match',
    ])
    claims = [c for c in vdc.parse_claims(text) if not c.get("error")]
    assert len(claims) == 1
    assert claims[0]["section"].startswith("23. Scheduler layer")
    assert claims[0]["line"] == 2


def test_broken_tag_is_skipped_not_drift(tmp_path):
    doc = tmp_path / "d.md"
    doc.write_text("## X\n<!-- claim: {broken json} -->\n", encoding="utf-8")
    report = vdc.run(doc, root=tmp_path)
    assert report["ok"] is True and report["checked"] == 0
    assert len(report["skipped"]) == 1


def test_target_outside_root_refused(tmp_path):
    root = _root_with_module(tmp_path)
    doc = tmp_path / "d.md"
    doc.write_text(
        '## X\n<!-- claim: {"type": "file_exists", "target": "../../.env"} -->\n',
        encoding="utf-8")
    report = vdc.run(doc, root=root)
    assert report["checked"] == 0 and len(report["skipped"]) == 1
    assert "outside root" in report["skipped"][0]["actual"]


def test_grep_drift_reports_boolean_only(tmp_path):
    root = _root_with_module(tmp_path)
    doc = tmp_path / "d.md"
    doc.write_text(
        '## Y\n<!-- claim: {"type": "grep", "target": "pkg/ledger.py",'
        ' "pattern": "def no_such_function", "expect": "present"} -->\n',
        encoding="utf-8")
    report = vdc.run(doc, root=root)
    assert report["ok"] is False and len(report["drifts"]) == 1
    d = report["drifts"][0]
    assert d["actual"] == "pattern absent"     # no source text or context leaked
    assert d["section"] == "Y"


# ---- added for standalone use (root parameter, CLI, report shapes) ------------

def test_ok_claims_against_root(tmp_path):
    root = _root_with_module(tmp_path)
    doc = tmp_path / "d.md"
    doc.write_text("\n".join([
        "## Z",
        '<!-- claim: {"type": "file_exists", "target": "pkg/ledger.py"} -->',
        '<!-- claim: {"type": "grep", "target": "pkg/ledger.py", "pattern": "def load_assets"} -->',
        '<!-- claim: {"type": "grep", "target": "pkg/ledger.py", "pattern": "TODO", "expect": "absent"} -->',
    ]), encoding="utf-8")
    report = vdc.run(doc, root=root)
    assert report == {"ok": True, "checked": 3, "drifts": [], "skipped": []}


def test_no_claims_and_parse_failure_are_distinct(tmp_path):
    empty = tmp_path / "empty.md"
    empty.write_text("## Nothing tagged here\n", encoding="utf-8")
    broken = tmp_path / "broken.md"
    broken.write_text("## B\n<!-- claim: [1, 2] -->\n<!-- claim: {not json} -->\n", encoding="utf-8")
    r_empty = vdc.run(empty, root=tmp_path)
    r_broken = vdc.run(broken, root=tmp_path)
    assert r_empty == {"ok": True, "checked": 0, "drifts": [], "skipped": []}
    assert r_broken["checked"] == 0 and r_broken["drifts"] == []
    assert [s["actual"] for s in r_broken["skipped"]] == ["tag parse failed or unsupported type"]


def test_unreadable_document_is_not_ok(tmp_path):
    report = vdc.run(tmp_path / "missing.md", root=tmp_path)
    assert report["ok"] is False and "error" in report


def test_cli_single_and_multiple_files(tmp_path, capsys):
    root = _root_with_module(tmp_path)
    good = tmp_path / "good.md"
    good.write_text('<!-- claim: {"type": "file_exists", "target": "pkg/ledger.py"} -->\n', encoding="utf-8")
    bad = tmp_path / "bad.md"
    bad.write_text('## S\n<!-- claim: {"type": "file_exists", "target": "pkg/gone.py"} -->\n', encoding="utf-8")

    assert vdc.main(["--root", str(root), str(good)]) == 0
    single = json.loads(capsys.readouterr().out)
    assert single == {"ok": True, "checked": 1, "drifts": [], "skipped": []}

    assert vdc.main(["--root", str(root), str(good), str(bad), str(tmp_path / "nope.md")]) == 1
    merged = json.loads(capsys.readouterr().out)
    assert merged["checked"] == 2
    assert [(d["doc"], d["actual"]) for d in merged["drifts"]] == [(str(bad), "file missing")]
    assert len(merged["errors"]) == 1


def test_cli_output_survives_non_utf8_stdout(tmp_path, monkeypatch):
    doc = tmp_path / "d.md"
    doc.write_text("## Caf\u00e9 \u2014 notes\n<!-- claim: {broken} -->\n", encoding="utf-8")
    buf = io.BytesIO()
    out = io.TextIOWrapper(buf, encoding="ascii")
    monkeypatch.setattr("sys.stdout", out)
    assert vdc.main(["--root", str(tmp_path), str(doc)]) == 0
    out.flush()
    report = json.loads(buf.getvalue().decode("ascii"))
    assert report["skipped"][0]["section"] == "Caf\u00e9 \u2014 notes"
