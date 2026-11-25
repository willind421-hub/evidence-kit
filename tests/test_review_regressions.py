"""Synthetic regressions for the independent portfolio reviews."""
import json

import pytest

from evidence_kit import doc_claims
from evidence_kit.research_ledger import (
    COMPLETE, COMPLETE_WITH_UNKNOWNS, INSUFFICIENT, EvidenceSpan, ResearchLedger,
)


@pytest.mark.parametrize('tag', [
    '<!-- claim: {} -->',
    '<!-- claim: [] -->',
    '<!-- claim: null -->',
    '<!-- claim: {"type": "typo"} -->',
    '<!-- claim: {"type": "grep", "target": "x"} -->',
    '<!-- claim: {"type": "file_exists", "target": "x"}',
    '<!-- claim: -->',
])
def test_invalid_tags_fail_closed_with_line_numbers(tmp_path, tag):
    doc = tmp_path / 'invalid.md'
    doc.write_text('## Heading\n' + tag + '\n', encoding='utf-8')
    report = doc_claims.run(doc, root=tmp_path)
    assert report['ok'] is False
    assert report['checked'] == 0
    assert len(report['skipped']) == 1
    assert report['skipped'][0]['line'] == 2
    assert report['skipped'][0]['section'] == 'Heading'


def test_empty_document_in_batch_cannot_hide_behind_good_document(tmp_path, capsys):
    (tmp_path / 'x').write_text('synthetic', encoding='utf-8')
    good = tmp_path / 'good.md'
    good.write_text('<!-- claim: {"type": "file_exists", "target": "x"} -->', encoding='utf-8')
    empty = tmp_path / 'empty.md'
    empty.write_text('No tagged assertions.', encoding='utf-8')
    assert doc_claims.run_many([good, empty], root=tmp_path)['ok'] is False
    assert doc_claims.main(['--root', str(tmp_path), str(empty)]) == 1
    assert json.loads(capsys.readouterr().out)['ok'] is False


def test_file_exists_requires_file_not_directory(tmp_path):
    (tmp_path / 'module.py').mkdir()
    assert doc_claims.check_claim({'type': 'file_exists', 'target': 'module.py'}, root=tmp_path) == ('drift', 'file missing')


def test_non_utf8_document_returns_json_error_without_aborting_batch(tmp_path, capsys):
    bad = tmp_path / 'bad.md'
    bad.write_bytes(b'\xff\xfeinvalid')
    good = tmp_path / 'good.md'
    good.write_text('<!-- claim: {"type": "file_exists", "target": "good.md"} -->', encoding='utf-8')
    report = doc_claims.run_many([bad, good], root=tmp_path)
    assert report['ok'] is False and report['checked'] == 1
    assert len(report['errors']) == 1
    assert doc_claims.main(['--root', str(tmp_path), str(bad)]) == 1
    assert 'error' in json.loads(capsys.readouterr().out)


@pytest.mark.parametrize('expect', ['present', 'absent'])
def test_grep_default_cannot_probe_untrusted_document_targets(tmp_path, expect):
    (tmp_path / 'config.ini').write_text('api_key=SYNTHETIC', encoding='utf-8')
    claim = {'type': 'grep', 'target': 'config.ini', 'pattern': 'api_key=S', 'expect': expect}
    status, actual = doc_claims.check_claim(claim, root=tmp_path)
    assert status == 'skipped'
    assert actual == 'grep target not allowlisted'


def test_grep_allowlist_preserves_symbol_checks_and_bounds_other_targets(tmp_path, capsys):
    (tmp_path / 'module.py').write_text('def load():\n    pass\n', encoding='utf-8')
    (tmp_path / 'config.ini').write_text('api_key=SYNTHETIC', encoding='utf-8')
    claims = [
        {'type': 'grep', 'target': 'module.py', 'pattern': 'def load('},
        {'type': 'grep', 'target': 'config.ini', 'pattern': 'api_key=S'},
    ]
    doc = tmp_path / 'claims.md'
    doc.write_text('\n'.join('<!-- claim: ' + json.dumps(c) + ' -->' for c in claims), encoding='utf-8')
    report = doc_claims.run(doc, root=tmp_path, grep_allowlist=['module.py'])
    assert report['ok'] is False and report['checked'] == 1
    assert report['skipped'][0]['actual'] == 'grep target not allowlisted'
    assert doc_claims.check_claim(claims[0], root=tmp_path, grep_allowlist=['module.py']) == ('ok', 'pattern present')
    assert doc_claims.check_claim({**claims[0], 'pattern': 'def missing('}, root=tmp_path,
                                  grep_allowlist=['module.py']) == ('drift', 'pattern absent')
    doc.write_text('<!-- claim: ' + json.dumps(claims[0]) + ' -->', encoding='utf-8')
    assert doc_claims.main(['--root', str(tmp_path), '--allow-grep', 'module.py', str(doc)]) == 0
    assert json.loads(capsys.readouterr().out)['checked'] == 1
    assert doc_claims.run_many([doc], root=tmp_path, grep_allowlist=['module.py'])['ok'] is True


def test_grep_allowlist_cannot_authorize_root_escape(tmp_path):
    root = tmp_path / 'root'
    root.mkdir()
    (tmp_path / 'outside.txt').write_text('synthetic', encoding='utf-8')
    claim = {'type': 'grep', 'target': '../outside.txt', 'pattern': 'synthetic'}
    assert doc_claims.check_claim(claim, root=root, grep_allowlist=['../outside.txt'])[0] == 'skipped'


@pytest.mark.parametrize('confirmed,stance,expected', [
    (False, None, INSUFFICIENT),
    (True, None, INSUFFICIENT),
    (False, 'supports', COMPLETE_WITH_UNKNOWNS),
    (True, 'context', COMPLETE_WITH_UNKNOWNS),
    (True, 'refutes', COMPLETE_WITH_UNKNOWNS),
    (True, 'supports', COMPLETE),
])
def test_cover_does_not_turn_unsupported_required_claim_into_complete(confirmed, stance, expected):
    led = ResearchLedger()
    sq = led.add_subquestion('Required?', importance=1)
    claim = led.add_claim(sq.id, 'Synthetic claim', confirmed=confirmed)
    if stance:
        led.attach_span(claim, EvidenceSpan(url='https://example.test/source', stance=stance))
    led.cover(sq.id)
    assert led.completion() == expected
    assert led.to_dict()['completion'] == expected


def test_other_evidence_cannot_hide_unsupported_covered_required_question():
    led = ResearchLedger()
    first = led.add_subquestion('Supported?', importance=1)
    supported = led.add_claim(first.id, 'Supported', confirmed=True)
    led.attach_span(supported, EvidenceSpan(url='https://example.test', stance='supports'))
    led.cover(first.id)
    second = led.add_subquestion('Unsupported?', importance=1)
    led.add_claim(second.id, 'Unknown')
    led.cover(second.id)
    assert led.completion() == COMPLETE_WITH_UNKNOWNS


def test_covered_required_question_without_claims_is_insufficient():
    led = ResearchLedger()
    sq = led.add_subquestion('Required?', importance=1)
    led.cover(sq.id)
    assert led.completion() == INSUFFICIENT


@pytest.mark.parametrize('blocked', [True, False])
def test_stopping_with_required_unknowns_reports_settled_not_covered(blocked):
    led = ResearchLedger()
    sq = led.add_subquestion('Required?', importance=1)
    if blocked:
        led.block_gap(led.ensure_gap(sq.id, 'No public evidence'), 'Unavailable')
    else:
        led.cover(sq.id)
    assert led.should_stop([]) == (True, 'required_settled')


@pytest.mark.parametrize('content', [
    '- nonempty\n- list\n', 'scalar text\n', 'true\n', '42\n', 'null\n', '',
    'instances: [wrong, shape]\n', 'instances: null\n',
    'instances: [broken: {',
    'instances:\n  bad: {type: goal, label: Bad, due: 2026-13-99}\n',
])
def test_reference_bad_shapes_return_empty_list(tmp_path, content):
    from evidence_kit.reference_ledger import load_instances
    path = tmp_path / 'ledger.yaml'
    path.write_text(content, encoding='utf-8')
    assert load_instances(path) == []


def test_reference_bad_encoding_returns_empty_list(tmp_path):
    from evidence_kit.reference_ledger import load_instances
    path = tmp_path / 'ledger.yaml'
    path.write_bytes(b'instances: \xff\xfe')
    assert load_instances(path) == []


def test_reference_unquoted_date_preserves_due_and_briefing_order(tmp_path):
    from evidence_kit.reference_ledger import brief_lines, load_instances
    path = tmp_path / 'ledger.yaml'
    path.write_text('instances:\n'
                    '  later: {type: goal, label: Later, due: "2026-12-31"}\n'
                    '  sooner: {type: goal, label: Sooner, due: 2026-12-01}\n', encoding='utf-8')
    rows = load_instances(path)
    assert rows[1]['due'] == '2026-12-01'
    lines = brief_lines(rows, today='2026-11-25')
    assert lines[1] == '  1. Sooner — D-6'
    assert 'Later' in lines[2]


@pytest.mark.parametrize('fields', [
    'type: [goal], label: Bad', 'type: goal, label: [Bad]',
    'type: {name: goal}, label: Bad', 'type: goal, label: null',
])
def test_reference_invalid_nested_rows_do_not_drop_valid_siblings(tmp_path, fields):
    from evidence_kit.reference_ledger import load_instances
    path = tmp_path / 'ledger.yaml'
    path.write_text('instances:\n  bad: {' + fields + '}\n'
                    '  good: {type: goal, label: Good}\n', encoding='utf-8')
    assert [r['id'] for r in load_instances(path)] == ['good']


def test_reference_nested_optional_bad_shapes_are_dropped(tmp_path):
    from evidence_kit.reference_ledger import load_instances
    path = tmp_path / 'ledger.yaml'
    path.write_text('instances:\n  g:\n    type: goal\n    label: Good\n'
                    '    status: [confirmed]\n    refs: {serves: [ok, {bad: id}, [nested], null]}\n'
                    '    notes: {bad: shape}\n    source_ledger: [bad]\n    due: [bad]\n', encoding='utf-8')
    assert load_instances(path) == [{'id': 'g', 'type': 'goal', 'label': 'Good',
                                    'status': 'proposed', 'refs': {'serves': ['ok']},
                                    'notes': None, 'source_ledger': None, 'due': None}]
