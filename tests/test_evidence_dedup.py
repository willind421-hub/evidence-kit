"""evidence_dedup tests.

The first two tests are ported from the original test suite; the rest pin down
existing behaviour (characterization tests) — they document the rules, they do
not add new ones.
"""
from __future__ import annotations

from evidence_kit.evidence_dedup import dedup_evidence


# ---- ported -------------------------------------------------------------------

def test_dedup_exact_and_semantic():
    items = [
        {"title": "Partner program sign up", "url": "http://a.com/1"},
        {"title": "Partner program sign up", "url": "http://a.com/1"},        # exact duplicate
        {"title": "Partner program sign up guide", "url": "http://a.com/2"},  # same domain + similar title
        {"title": "A completely different topic", "url": "http://b.com/1"},
    ]
    out = dedup_evidence(items, threshold=0.5)
    assert out["before"] == 4
    urls = [e["url"] for e in out["kept"]]
    assert "http://a.com/1" in urls and "http://b.com/1" in urls
    assert len(out["kept"]) < 4               # at least one was merged


def test_dedup_different_domain_never_merged():
    items = [{"title": "Same title", "url": "http://a.com"},
             {"title": "Same title", "url": "http://b.com"}]
    out = dedup_evidence(items, threshold=0.1)
    assert len(out["kept"]) == 2              # different domains are never merged


# ---- characterization of the original rules -----------------------------------

def test_same_url_twice_keeps_first_occurrence():
    items = [{"url": "https://example.com/a", "title": "First", "snippet": "one"},
             {"url": "https://example.com/a", "title": "Second", "snippet": "two"}]
    out = dedup_evidence(items)
    assert out == {"kept": [items[0]], "before": 2, "after": 1}


def test_identical_title_same_domain_merges_at_default_threshold():
    items = [{"url": "https://www.example.com/a", "title": "Pricing plans"},
             {"url": "https://example.com/b", "title": "pricing PLANS"}]   # www. and case ignored
    assert dedup_evidence(items)["after"] == 1


def test_similar_title_below_default_threshold_is_kept():
    # Jaccard({pricing, plans}, {pricing, plans, 2026}) = 2/3 < 0.85
    items = [{"url": "https://example.com/a", "title": "Pricing plans"},
             {"url": "https://example.com/b", "title": "Pricing plans 2026"}]
    assert dedup_evidence(items)["after"] == 2


def test_other_fields_such_as_ids_are_not_compared():
    # Only url/title are looked at: distinct ids do not prevent a merge.
    items = [{"id": "e1", "url": "https://example.com/a", "title": "Report"},
             {"id": "e2", "url": "https://example.com/a", "title": "Report"},
             {"id": "e3", "url": "https://example.com/b", "title": "Report"}]
    out = dedup_evidence(items)
    assert [e["id"] for e in out["kept"]] == ["e1"]


def test_missing_url_falls_back_to_title_as_exact_key():
    # Without a url the title becomes the exact-match key, whatever the source.
    items = [{"title": "Shared headline", "source": "feed-a"},
             {"title": "Shared headline", "source": "feed-b"}]
    out = dedup_evidence(items)
    assert [e["source"] for e in out["kept"]] == ["feed-a"]


def test_empty_titles_are_kept_and_non_dicts_ignored():
    items = [{"url": "https://example.com/a", "title": ""},
             {"url": "https://example.com/b", "title": ""},
             "not-a-dict", None]
    out = dedup_evidence(items, threshold=0.0)
    assert out["before"] == 2 and out["after"] == 2


def test_order_is_preserved():
    items = [{"url": f"https://site{i}.example/", "title": f"Item {i}"} for i in range(5)]
    out = dedup_evidence(items)
    assert out["kept"] == items
    assert dedup_evidence([]) == {"kept": [], "before": 0, "after": 0}
    assert dedup_evidence(None) == {"kept": [], "before": 0, "after": 0}
