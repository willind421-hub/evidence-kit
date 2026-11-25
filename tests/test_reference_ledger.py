"""reference_ledger contract — a thin reference index with a read-only loader.

Hybrid registration: meaning fields (type, standing) need approval, so an unknown
status is demoted to "proposed". Guard: broken YAML or incomplete rows never
take the whole loader down (lenient parsing).
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from evidence_kit import reference_ledger

needs_yaml = pytest.mark.skipif(importlib.util.find_spec("yaml") is None,
                                reason="PyYAML not installed (extra: yaml)")

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "reference-ledger.example.yaml"


def _write_yaml(path, text):
    path.write_text(text, encoding="utf-8")


_HAPPY = """
instances:
  proj-a:
    type: project
    label: "Project A"
    source_ledger: assets
    refs: {publishes_to: [chan-b]}
    status: confirmed
  chan-b: {type: channel, label: "Channel B"}
"""


@needs_yaml
def test_load_instances_happy(tmp_path):
    y = tmp_path / "ledger.yaml"
    _write_yaml(y, _HAPPY)
    rows = reference_ledger.load_instances(y)
    assert {r["id"] for r in rows} == {"proj-a", "chan-b"}
    a = next(r for r in rows if r["id"] == "proj-a")
    assert a["type"] == "project"
    assert a["source_ledger"] == "assets"
    assert a["refs"] == {"publishes_to": ["chan-b"]}
    assert a["status"] == "confirmed"
    b = next(r for r in rows if r["id"] == "chan-b")
    assert b["status"] == "proposed"          # omitted status = proposed (hybrid approval)
    assert b["refs"] == {} and b["source_ledger"] is None


@needs_yaml
def test_load_instances_missing_or_broken(tmp_path):
    assert reference_ledger.load_instances(tmp_path / "missing.yaml") == []
    y = tmp_path / "broken.yaml"
    _write_yaml(y, "instances: [broken: {")
    assert reference_ledger.load_instances(y) == []
    _write_yaml(y, "instances: just-a-string")   # not a mapping
    assert reference_ledger.load_instances(y) == []


@needs_yaml
def test_unknown_type_or_missing_label_skipped(tmp_path):
    y = tmp_path / "w.yaml"
    _write_yaml(y, """
instances:
  ok: {type: device, label: "Device"}
  bad-type: {type: universe, label: "Unknown type"}
  no-label: {type: project}
  blank-label: {type: project, label: "  "}
""")
    rows = reference_ledger.load_instances(y)
    assert [r["id"] for r in rows] == ["ok"]


@needs_yaml
def test_unknown_status_demoted_to_proposed(tmp_path):
    y = tmp_path / "w.yaml"
    _write_yaml(y, 'instances:\n  a: {type: goal, label: "Goal", status: approved}\n')
    rows = reference_ledger.load_instances(y)
    assert rows[0]["status"] == "proposed"    # outside the whitelist = not approved


@needs_yaml
def test_refs_lenient_parsing(tmp_path):
    y = tmp_path / "w.yaml"
    _write_yaml(y, """
instances:
  a:
    type: project
    label: "Lenient parsing"
    refs:
      good: [x, y]
      not-list: "a string"
      mixed: [ok, 3, "", null]
      "": [z]
""")
    rows = reference_ledger.load_instances(y)
    assert rows[0]["refs"] == {"good": ["x", "y"], "mixed": ["ok"]}


@needs_yaml
def test_example_ledger_contract():
    """Example ledger: loads, ids are unique and refs only point at ids in the ledger (no orphans)."""
    rows = reference_ledger.load_instances(EXAMPLE)
    assert len(rows) == 5
    ids = [r["id"] for r in rows]
    assert len(ids) == len(set(ids)), "duplicate id"
    known = set(ids)
    for r in rows:
        for rel, targets in r["refs"].items():
            for t in targets:
                assert t in known, f"orphan reference: {r['id']} --{rel}--> {t}"


# ---- briefing lines — the first consumer of the ledger -------------------------

@needs_yaml
def test_due_field_lenient(tmp_path):
    y = tmp_path / "w.yaml"
    _write_yaml(y, 'instances:\n  g: {type: goal, label: "Goal", due: "2030-03-23"}\n'
                   '  g2: {type: goal, label: "Goal 2", due: 3}\n')
    rows = reference_ledger.load_instances(y)
    assert rows[0]["due"] == "2030-03-23"
    assert rows[1]["due"] is None            # not a string = dropped (lenient)


def _inst(id, type, label, due=None, refs=None):
    return {"id": id, "type": type, "label": label, "status": "confirmed",
            "source_ledger": None, "refs": refs or {}, "notes": None, "due": due}


def test_brief_lines_orders_by_due_and_links_projects():
    rows = [
        _inst("goal-a", "goal", "Goal A, no rush"),
        _inst("goal-b", "goal", "Goal B, due soon", due="2030-03-23"),
        _inst("proj-x", "project", "Project X — details", refs={"serves": ["goal-b"]}),
        _inst("chan-1", "channel", "Channel"),
    ]
    lines = reference_ledger.brief_lines(rows, today="2030-03-10")
    assert "Goals (reference ledger): 2" in lines[0]
    assert lines[1].startswith("  1. Goal B")          # the goal with a due date comes first
    assert "D-13" in lines[1]                          # days until due
    assert "[related: Project X]" in lines[1]          # the serves relation is used
    assert lines[2].startswith("  2. Goal A")
    assert "Pick one" in lines[-1]


def test_brief_lines_overdue_and_empty():
    rows = [_inst("g", "goal", "Past goal", due="2030-03-08")]
    lines = reference_ledger.brief_lines(rows, today="2030-03-10")
    assert "overdue by 2 days" in lines[1]
    assert reference_ledger.brief_lines([], today="2030-03-10") == []
    assert reference_ledger.brief_lines([_inst("c", "channel", "Channel only")], today="x") == []


def test_missing_pyyaml_gives_clear_error(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "yaml", None)   # makes "import yaml" raise ImportError
    with pytest.raises(ImportError, match=r"pip install pyyaml") as exc:
        reference_ledger.load_instances(tmp_path / "any.yaml")
    assert 'pip install "evidence-kit[yaml]"' not in str(exc.value)
