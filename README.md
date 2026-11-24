# Evidence Kit

**English** | [한국어](README.ko.md) | [日本語](README.ja.md)

A small, dependency-free toolkit for keeping research claims and documentation honest.
Four independent modules, one per job:

| Module | Job |
| --- | --- |
| `evidence_kit.research_ledger` | Track subquestions, claims, evidence spans, gaps and conflicts; decide *in code* when to stop and how complete an answer is. |
| `evidence_kit.evidence_dedup` | Remove duplicate search evidence (exact URL, then same-domain similar titles) and report before/after counts. |
| `evidence_kit.doc_claims` | Check `<!-- claim: {...} -->` tags in Markdown against a source tree (`doc-claims` CLI). |
| `evidence_kit.reference_ledger` | Read-only loader for a small YAML index of "what exists", plus a briefing view of goals. |

## The problem

Research and documentation tooling rots quietly in two places:

- **Research answers.** "Needs more checking" is written as a sentence and then forgotten. Claims without
  support slip into the answer as facts. Loops either run forever on questions that have no public answer,
  or stop whenever a model says "looks done". Duplicate search hits inflate how much evidence there seems to be.
- **Documentation.** A design document says "module X exists" or "Y is wired up" long after the code moved on.

Evidence Kit turns those soft statements into small, inspectable data structures with deterministic rules.

## What it guarantees

- **Unsupported claims stay unverified.** A claim is `unconfirmed` unless you confirm it explicitly; attaching
  evidence never confirms it. A claim that receives both a `supports` and a `refutes` span becomes `conflicted`
  and gets an *unresolved* conflict record — no winner is picked automatically.
- **Unknowns are never hidden.** Completion is one of `complete`, `complete_with_unknowns`,
  `insufficient_evidence`. Any open or blocked gap, unresolved conflict or uncovered subquestion yields
  `complete_with_unknowns`, never `complete`.
- **Stopping is decided by code**, from three explicit conditions (required questions settled, stale rounds,
  gap attempt cap), and the reason is returned.
- **De-duplication is conservative:** never across domains, empty titles are kept, order is preserved, and the
  before/after counts are always reported.
- **Document checks are read-only and leak nothing:** only boolean results are reported (never file contents),
  targets outside the root are refused, broken tags are reported as *skipped* (not drift), nothing is auto-fixed.
  Exit code `0` = no drift, `1` = drift or unreadable document.
- **The reference-ledger loader never crashes on bad input:** a missing or broken file gives `[]`, invalid rows
  are dropped, and an unknown `status` is demoted to `proposed`.

## Design

- Plain dataclasses and pure functions. No network access, no model calls, no global state.
  Search engines or LLMs belong to the caller; these modules only hold and judge the evidence state.
- Only `doc_claims` (reads Markdown and target files) and `reference_ledger` (reads one YAML file) touch the
  file system, and both are read-only.
- No runtime dependencies. PyYAML is an optional extra (`yaml`) needed only by
  `reference_ledger.load_instances`; without it you get an `ImportError` with an install hint.
- Python 3.10+.

## Quick start

The package is not published on PyPI; install it from a checkout:

```bash
pip install -e ".[yaml]"        # or: pip install -e .   (everything except the YAML loader)
python examples/quickstart.py   # runs all four modules on synthetic data
doc-claims --root . examples/sample-doc.md
```

## Modules

### research_ledger — evidence state for iterative research

```python
from evidence_kit.research_ledger import EvidenceSpan, ResearchLedger

led = ResearchLedger()
sq = led.add_subquestion("What does the service cost per month?", want_sources="official", importance=1)
claim = led.add_claim(sq.id, "The basic plan costs USD 10 per month")      # unconfirmed by default
led.attach_span(claim, EvidenceSpan(url="https://example.com/pricing", quote="Basic: $10/month", stance="supports"))
led.attach_span(claim, EvidenceSpan(url="https://example.org/review", quote="Basic now costs $12", stance="refutes"))

claim.status                                   # 'conflicted'
led.completion()                               # 'complete_with_unknowns' — the conflict is not hidden
led.should_stop([{"new_evidence": 0}, {"new_evidence": 0}])   # (True, 'stale_rounds')
led.to_dict()                                  # plain dict for job files / logs
```

Importance `1` marks a required subquestion. `ensure_gap` / `record_attempt` / `block_gap` keep unknowns as
data (with the queries tried and a stop reason) instead of prose.

### evidence_dedup — conservative de-duplication

```python
from evidence_kit.evidence_dedup import dedup_evidence

out = dedup_evidence([
    {"url": "https://example.com/pricing", "title": "Pricing plans"},
    {"url": "https://example.com/pricing", "title": "Pricing plans"},    # same URL
    {"url": "https://www.example.com/plans", "title": "Pricing Plans"},  # same domain, same title tokens
    {"url": "https://example.org/review", "title": "Pricing plans"},     # other domain: kept
])
out["before"], out["after"]                    # (4, 2)
```

Rules: pass 1 drops exact duplicates keyed by `url` (or `title` when `url` is empty); pass 2 drops items on the
same domain (`www.` ignored) whose lower-cased title tokens have Jaccard similarity `>= threshold`
(default `0.85`). Only `url` and `title` are compared — other fields such as ids or source names are not.
The first occurrence wins.

### doc_claims — documentation drift checker

Tag checkable statements in Markdown with a single-line HTML comment (invisible when rendered):

```markdown
## Storage
The loader lives in its own module.
<!-- claim: {"type": "file_exists", "target": "src/pkg/loader.py"} -->
<!-- claim: {"type": "grep", "target": "src/pkg/loader.py", "pattern": "def load(", "expect": "present"} -->
```

```bash
doc-claims --root path/to/project docs/design.md docs/other.md
```

```json
{
  "ok": false,
  "checked": 2,
  "drifts": [
    {"section": "Storage", "line": 4, "type": "grep", "target": "src/pkg/loader.py", "actual": "pattern absent"}
  ],
  "skipped": []
}
```

- Types: `file_exists`, and `grep` (plain substring; `expect` is `present` or `absent`, default `present`).
- `target` is resolved against `--root` (default: current directory); anything outside is refused.
- `section` is the nearest `##`/`###` heading above the tag.
- A document without tags gives `checked: 0` and an empty `skipped` list; a broken tag gives `checked: 0` with a
  `skipped` row — the two cases stay distinguishable.
- With one file the output is exactly the report above; with several files the reports are merged, each row
  gets a `doc` field, and unreadable files are listed under `errors`.
- Python API: `run(path, root=...)`, `run_many(paths, root=...)`, `parse_claims(text)`, `check_claim(claim, root=...)`.

### reference_ledger — read-only reference index

```yaml
instances:
  example-project:
    type: project                       # project | artifact | channel | account_subscription | device | data_source | goal
    label: "Example project — projects/example"
    source_ledger: assets               # pointer to the canonical record; fields are not copied
    refs: {serves: [goal-launch]}
    status: confirmed                   # confirmed | proposed (missing/unknown -> proposed)
  goal-launch: {type: goal, label: "Ship the example v1", due: "2026-02-01"}
```

```python
from evidence_kit.reference_ledger import brief_lines, load_instances

rows = load_instances("ledger.yaml")           # needs the "yaml" extra
print("\n".join(brief_lines(rows, today="2026-01-20")))
# · Goals (reference ledger): 1 — candidates for today:
#   1. Ship the example v1 — D-12 [related: Example project]
#   → Pick one to start with.
```

The intended policy is *hybrid*: facts may be updated automatically, meaning (`type`, relations, `status`) is
proposed and then approved, and removal is only ever proposed. See `examples/reference-ledger.example.yaml`.

## API overview

| Module | Public names |
| --- | --- |
| `research_ledger` | `ResearchLedger` (`add_subquestion`, `cover`, `add_claim`, `attach_span`, `ensure_gap`, `record_attempt`, `block_gap`, `open_gaps`, `should_stop`, `completion`, `to_dict`), dataclasses `Subquestion`, `Claim`, `EvidenceSpan`, `Gap`, `Conflict`, constants `COMPLETE`, `COMPLETE_WITH_UNKNOWNS`, `INSUFFICIENT`, `IMPORTANCE_REQUIRED`, `SOURCE_KINDS` |
| `evidence_dedup` | `dedup_evidence(items, *, threshold=0.85) -> {"kept", "before", "after"}` |
| `doc_claims` | `run`, `run_many`, `parse_claims`, `check_claim`, `main` (console script `doc-claims`) |
| `reference_ledger` | `load_instances(path) -> list[dict]`, `brief_lines(instances, today="") -> list[str]` |

## Running tests

```bash
pip install -e ".[test]"     # pytest + PyYAML
pytest -q
```

CI runs the suite on Ubuntu and Windows with Python 3.10 and 3.13.

## Limitations and non-goals

- `research_ledger` does not search, fetch pages or classify stance — the caller decides stance and
  confirmation. It has `to_dict()` but no loader back from a dict. IDs are sequential per ledger instance.
- `evidence_dedup` is lexical, not semantic: differently worded titles are not merged, syndicated copies on other
  domains are never merged, and duplicates are dropped rather than merged field by field.
- `doc_claims` supports only two claim types; a tag must fit on one line; `grep` is a substring match, not a
  regular expression; tags inside fenced code blocks are parsed like any other line; it never runs commands
  or tests and never edits files.
- `reference_ledger` is a loader and a briefing view only: there is no writer, no relation-type schema, and the
  loader does not check that `refs` point at existing ids (the test suite shows how to check that). Briefing
  text is fixed English.

## Origin

These modules were extracted from **willind**, a discontinued personal AI-assistant project, where they served
as the evidence-state layer and evidence de-duplicator of a deep-research tool, a "living design document"
drift checker, and a small reference index read by a morning briefing. For this release internal imports and
hard-coded paths were replaced with parameters, comments were translated into English, and the original
behaviour was kept.

## License

Apache License 2.0 — see [LICENSE](LICENSE) and [NOTICE](NOTICE).
