"""Synthetic review regressions: do not discard distinct sources by title."""
from evidence_kit.evidence_dedup import dedup_evidence


def test_different_versions_on_same_domain_remain_distinct():
    items = [
        {'url': 'https://docs.example.test/3.12/whatsnew', 'title': 'What is new'},
        {'url': 'https://docs.example.test/3.13/whatsnew', 'title': 'WHAT IS NEW'},
    ]
    assert dedup_evidence(items)['kept'] == items


def test_missing_urls_do_not_merge_different_or_unidentified_sources():
    items = [
        {'title': 'Introduction', 'source': 'paper-A'},
        {'title': 'Introduction', 'source': 'paper-B'},
        {'title': 'Introduction'},
        {'title': 'Introduction'},
    ]
    assert dedup_evidence(items)['kept'] == items


def test_url_and_title_do_not_share_identity_namespace():
    items = [
        {'url': 'https://example.test/a', 'title': 'First'},
        {'title': 'https://example.test/a', 'source': 'paper-B'},
    ]
    assert dedup_evidence(items)['kept'] == items


def test_opt_in_title_merging_is_auditable_and_off_by_default():
    items = [
        {'url': 'https://example.test/a', 'title': 'Example title'},
        {'url': 'https://example.test/a', 'title': 'Other title'},
        {'url': 'https://www.example.test/b', 'title': 'Example Title'},
        {'url': 'https://elsewhere.test/a', 'title': 'Example title'},
    ]
    out = dedup_evidence(items, merge_similar=True)
    assert out['kept'] == [items[0], items[3]]
    assert out['merged'] == [
        {'kept_index': 0, 'dropped_index': 1, 'reason': 'exact_url'},
        {'kept_index': 0, 'dropped_index': 2, 'reason': 'similar_title'},
    ]
    assert out['before'] == 4 and out['after'] == 2
    assert dedup_evidence(items)['after'] == 3


def test_audit_indices_refer_to_original_input_including_ignored_entries():
    items = [None, {'url': 'https://example.test/a'}, 'ignored', {'url': 'https://example.test/a'}]
    out = dedup_evidence(items)
    assert out['before'] == 2 and out['after'] == 1
    assert out['merged'] == [{'kept_index': 1, 'dropped_index': 3, 'reason': 'exact_url'}]
