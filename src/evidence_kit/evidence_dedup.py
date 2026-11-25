"""evidence_dedup — lightweight de-duplication of search evidence.

By default only non-empty string URLs that match exactly are de-duplicated.
Missing URLs and distinct paths (including different document versions) are kept.
Optional ``merge_similar=True`` enables lossy same-domain title-token matching;
it can discard distinct sources, so every removal has an audit entry.
No embeddings, no network. Other metadata is not merged field by field.
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


def dedup_evidence(items: List[dict] | None, *, threshold: float = 0.85,
                   merge_similar: bool = False) -> dict:
    """De-duplicate evidence items (dicts with ``url`` and/or ``title``).

    Exact URL matching is the default. URL-less items are always kept.
    ``merge_similar=True`` additionally drops same-domain items with title-token
    Jaccard >= ``threshold``; this is lossy even for versioned documents.
    Non-dict entries are ignored; order is preserved (first occurrence wins).
    ``merged`` entries contain zero-based original-input ``kept_index`` and
    ``dropped_index`` plus ``reason`` (``exact_url`` or ``similar_title``).
    Counts include dict entries only. Input objects are not modified.
    """
    valid = [(idx, it) for idx, it in enumerate(items or []) if isinstance(it, dict)]
    seen, kept, sigs, merged = {}, [], [], []
    for idx, it in valid:
        url = it.get("url")
        url = url if isinstance(url, str) and url.strip() else None
        kept_idx, reason = seen.get(url), "exact_url"
        dom, toks = _domain(url), _title_tokens(it.get("title"))
        if kept_idx is None and merge_similar and dom and toks:
            for prior_idx, prior_dom, prior_toks in sigs:
                if prior_dom == dom and _jaccard(toks, prior_toks) >= threshold:
                    kept_idx, reason = prior_idx, "similar_title"
                    break
        if kept_idx is None:
            kept_idx = idx
            sigs.append((idx, dom, toks))
            kept.append(it)
        else:
            merged.append({"kept_index": kept_idx, "dropped_index": idx, "reason": reason})
        if url is not None:
            seen[url] = kept_idx
    return {"kept": kept, "before": len(valid), "after": len(kept), "merged": merged}
