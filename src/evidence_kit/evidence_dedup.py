"""evidence_dedup — lightweight de-duplication of search evidence.

Pass 1 removes exact duplicates (key = ``url``, or ``title`` when ``url`` is
missing). Pass 2 merges items on the *same domain* whose title-token Jaccard
similarity is at or above ``threshold``. No embeddings, no network.

Guards against over-merging: items on different domains are never merged by
title, and items with an empty title (or no domain) are never merged by pass 2.
Other fields (ids, source names, snippets) are not compared.
"""
from __future__ import annotations

import re
from typing import Any, List
from urllib.parse import urlparse


def _domain(url: Any) -> str:
    try:
        host = (urlparse(str(url or "")).netloc or "").lower()
    except Exception:
        return ""
    return host[4:] if host.startswith("www.") else host


def _title_tokens(title: Any) -> set:
    return set(re.findall(r"\w+", str(title or "").lower()))


def _jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b) if (a | b) else 0.0


def dedup_evidence(items: List[dict], *, threshold: float = 0.85) -> dict:
    """De-duplicate evidence items (dicts with ``url`` and/or ``title``).

    Pass 1: exact match on ``url`` (falls back to ``title`` when ``url`` is empty).
    Pass 2: same domain + title-token Jaccard >= ``threshold``.

    Never merges across domains; items with an empty title are kept by pass 2.
    Non-dict entries are ignored. Order is preserved (the first occurrence wins).

    Returns ``{"kept": [...], "before": int, "after": int}`` — before/after counts
    are returned together so the reduction can be audited (no black box).
    """
    valid = [it for it in (items or []) if isinstance(it, dict)]
    seen, exact = set(), []
    for it in valid:
        k = str(it.get("url") or it.get("title") or "")
        if k and k in seen:
            continue
        if k:
            seen.add(k)
        exact.append(it)
    kept, sigs = [], []
    for it in exact:
        dom, toks = _domain(it.get("url")), _title_tokens(it.get("title"))
        dup = False
        if dom and toks:
            for sd, st in sigs:
                if sd == dom and _jaccard(toks, st) >= threshold:
                    dup = True
                    break
        if not dup:
            sigs.append((dom, toks))
            kept.append(it)
    return {"kept": kept, "before": len(valid), "after": len(kept)}
