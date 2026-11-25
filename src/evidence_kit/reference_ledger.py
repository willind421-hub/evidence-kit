"""reference_ledger — a thin reference index of "what exists" (v0 loader).

Collects the *instances* of a small world — projects, artifacts, channels,
subscriptions, devices, data sources, goals — in one YAML file without copying
the fields of their authoritative ledgers: a ``source_ledger`` pointer names the
canonical record instead. Type schemas, relation types and action mappings are
meant to be added only together with a real consumer (no layer without a consumer).

Registration policy (hybrid):
- facts (existence, path, liveness) may be updated automatically;
- meaning (type, relations, standing) is proposed and then approved
  (``status: proposed`` -> ``confirmed``);
- removal is only ever proposed — never deleted automatically (avoids ghost and
  orphan data).

The YAML file is owned by the user; this code is only a read-only loader and
checker with no side effects.

Requires PyYAML for :func:`load_instances` (``pip install pyyaml``).
:func:`brief_lines` works on already-loaded rows and needs no extra dependency.
"""
from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import List

_VALID_TYPES = ("project", "artifact", "channel", "account_subscription",
                "device", "data_source", "goal")
_VALID_STATUS = ("confirmed", "proposed")


def _require_yaml():
    try:
        import yaml
    except ImportError as exc:
        raise ImportError(
            "evidence_kit.reference_ledger.load_instances needs PyYAML. "
            'Install it with: pip install pyyaml (or, from this checkout: pip install -e ".[yaml]")'
        ) from exc
    return yaml


def load_instances(path) -> List[dict]:
    """Reference-ledger YAML -> list of validated instance rows. Missing or broken file -> ``[]``.

    A row needs ``type`` (whitelisted) and a non-empty string ``label``. An unknown
    ``status`` is demoted to ``"proposed"`` — treating unapproved meaning as
    unapproved is the safe side of the hybrid policy. ``refs`` only passes in the
    form ``{relation: [id, ...]}``; anything else is silently dropped (lenient parsing).

    Raises :class:`ImportError` with an install hint if PyYAML is not installed.
    """
    yaml = _require_yaml()
    try:
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    except (OSError, UnicodeError, ValueError, yaml.YAMLError):
        return []
    if not isinstance(data, dict):
        return []
    rows = data.get("instances")
    if not isinstance(rows, dict):
        return []
    instances: List[dict] = []
    for inst_id, row in rows.items():
        if not isinstance(row, dict):
            continue
        itype = row.get("type")
        if itype not in _VALID_TYPES:
            continue
        label = row.get("label")
        if not isinstance(label, str) or not label.strip():
            continue
        status = row.get("status")
        if status not in _VALID_STATUS:
            status = "proposed"
        source = row.get("source_ledger")
        source = source.strip() if isinstance(source, str) and source.strip() else None
        raw_refs = row.get("refs")
        refs: dict = {}
        if isinstance(raw_refs, dict):
            for rel, targets in raw_refs.items():
                if not isinstance(rel, str) or not rel.strip():
                    continue
                if isinstance(targets, list):
                    ids = [t for t in targets if isinstance(t, str) and t.strip()]
                    if ids:
                        refs[rel.strip()] = ids
        notes = row.get("notes")
        notes = notes.strip() if isinstance(notes, str) and notes.strip() else None
        due = row.get("due")
        if isinstance(due, date) and not isinstance(due, datetime):
            due = due.isoformat()
        due = due.strip() if isinstance(due, str) and due.strip() else None
        instances.append({
            "id": str(inst_id), "type": itype, "label": label.strip(),
            "status": status, "source_ledger": source, "refs": refs,
            "notes": notes, "due": due,
        })
    return instances


def brief_lines(instances, today: str = "") -> List[str]:
    """Ledger rows -> a short briefing section (no model involved).

    Lists up to three ``goal`` rows as candidates for today, nearest ``due`` first
    (goals without a due date follow in registration order). Each candidate is
    annotated with the projects that point at it through a ``serves`` relation —
    the first place where the ledger's ``refs`` do real work. Returns ``[]`` when
    there are no goals. ``today`` is an ISO date (``YYYY-MM-DD``); if it is empty
    or invalid, no day counts are shown.
    """
    goals = [r for r in instances if r["type"] == "goal"]
    if not goals:
        return []
    # Reverse index of projects that serve a goal (goal_id -> [project label head]).
    serving: dict = {}
    for r in instances:
        if r["type"] != "project":
            continue
        for gid in (r["refs"].get("serves") or []):
            serving.setdefault(gid, []).append(r["label"].split(" — ")[0])

    def _dday(due):
        try:
            import datetime as _dt
            return (_dt.date.fromisoformat(due) - _dt.date.fromisoformat(today)).days
        except (ValueError, TypeError):
            return None

    keyed = []
    for idx, g in enumerate(goals):
        days = _dday(g["due"]) if g["due"] else None
        keyed.append(((0, days) if days is not None else (1, idx), days, g))
    keyed.sort(key=lambda k: k[0])
    lines = [f"· Goals (reference ledger): {len(goals)} — candidates for today:"]
    for i, (_, days, g) in enumerate(keyed[:3], start=1):
        tail = ""
        if days is not None:
            tail = f" — D-{days}" if days >= 0 else f" — overdue by {-days} days"
        rel = serving.get(g["id"])
        if rel:
            tail += f" [related: {', '.join(rel)}]"
        lines.append(f"  {i}. {g['label']}{tail}")
    lines.append("  → Pick one to start with.")
    return lines
