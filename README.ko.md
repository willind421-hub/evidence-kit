# Evidence Kit

[English](README.md) | **한국어** | [日本語](README.ja.md)

조사 결과의 주장과 문서 내용을 정직하게 유지하기 위한 작은 도구 모음입니다. 런타임 의존성이 없습니다.
서로 독립된 네 모듈이 각각 한 가지 일을 맡습니다.

| 모듈 | 하는 일 |
| --- | --- |
| `evidence_kit.research_ledger` | 하위 질문·주장·근거 구간·공백(gap)·충돌을 기록하고, 언제 멈출지와 답이 얼마나 완결됐는지를 *코드로* 판정합니다. |
| `evidence_kit.evidence_dedup` | 검색 근거의 중복을 지웁니다(URL 정확 일치 → 같은 도메인의 비슷한 제목). 제거 전후 개수를 함께 돌려줍니다. |
| `evidence_kit.doc_claims` | Markdown 안의 `<!-- claim: {...} -->` 태그를 실제 소스 트리와 대조합니다(`doc-claims` CLI). |
| `evidence_kit.reference_ledger` | "무엇이 있는가"를 모은 작은 YAML 색인을 읽기 전용으로 불러오고, 목표 목록을 브리핑 형태로 보여 줍니다. |

## 해결하려는 문제

조사·문서 도구는 두 군데에서 조용히 썩습니다.

- **조사 답변.** "추가 확인 필요"가 문장으로만 남고 잊힙니다. 근거 없는 주장이 사실처럼 답에 섞입니다.
  공개된 답이 없는 질문에서는 루프가 끝없이 돌거나, 모델이 "됐다"고 말하는 순간 멈춥니다.
  같은 검색 결과가 여러 번 잡혀 근거가 실제보다 많아 보입니다.
- **문서.** 설계 문서는 코드가 바뀐 뒤에도 "X 모듈이 있다", "Y가 연결돼 있다"고 계속 주장합니다.

Evidence Kit은 이런 모호한 문장을 들여다볼 수 있는 작은 데이터 구조와 결정론적 규칙으로 바꿉니다.

## 보장하는 것

- **근거 없는 주장은 미확인으로 남습니다.** 주장은 명시적으로 확인하기 전까지 `unconfirmed`이고,
  근거를 붙여도 저절로 확인되지 않습니다. 같은 주장에 `supports`와 `refutes` 근거가 모두 붙으면
  `conflicted`가 되고 *미해소* 충돌 기록이 생깁니다. 승자를 자동으로 고르지 않습니다.
- **모르는 것을 숨기지 않습니다.** 완료 상태는 `complete`, `complete_with_unknowns`,
  `insufficient_evidence` 셋 중 하나입니다. 열려 있거나 막힌 공백, 미해소 충돌, 덮이지 않은 하위 질문이
  하나라도 있으면 `complete`가 아니라 `complete_with_unknowns`입니다.
- **중단은 코드가 판정합니다.** 세 가지 명시적 조건(필수 질문 정리 완료, 새 근거 없는 라운드 반복,
  공백별 시도 상한)으로 판단하고 그 이유를 함께 돌려줍니다.
- **중복 제거는 보수적입니다.** 도메인이 다르면 합치지 않고, 제목이 빈 항목은 남기며, 순서를 보존하고,
  제거 전후 개수를 항상 알려 줍니다.
- **문서 검사는 읽기 전용이고 내용을 흘리지 않습니다.** 결과는 참/거짓 서술만 보고하고 파일 내용은 싣지
  않습니다. 루트 밖 대상은 거부하고, 깨진 태그는 드리프트가 아니라 *skipped*로 보고하며, 아무것도 자동으로
  고치지 않습니다. 종료 코드 `0` = 드리프트 없음, `1` = 드리프트 또는 문서 읽기 실패.
- **참조 장부 로더는 잘못된 입력에 죽지 않습니다.** 파일이 없거나 깨지면 `[]`, 잘못된 행은 버리고,
  모르는 `status`는 `proposed`로 낮춥니다.

## 설계

- 평범한 dataclass와 순수 함수뿐입니다. 네트워크 접근, 모델 호출, 전역 상태가 없습니다.
  검색 엔진이나 LLM은 호출하는 쪽이 맡고, 이 모듈들은 근거 상태를 담고 판정만 합니다.
- 파일 시스템에 닿는 것은 `doc_claims`(Markdown과 대상 파일 읽기)와 `reference_ledger`(YAML 한 개 읽기)뿐이며
  둘 다 읽기 전용입니다.
- 런타임 의존성이 없습니다. PyYAML은 `reference_ledger.load_instances`에만 필요한 선택 extra(`yaml`)이고,
  설치되지 않았으면 설치 방법을 알려 주는 `ImportError`가 납니다.
- Python 3.10 이상.

## 빠른 시작

PyPI에는 올리지 않았으므로 저장소를 받아 설치합니다.

```bash
pip install -e ".[yaml]"        # 또는 pip install -e .  (YAML 로더만 빠짐)
python examples/quickstart.py   # 합성 데이터로 네 모듈을 모두 실행
doc-claims --root . examples/sample-doc.md
```

## 모듈

### research_ledger — 반복 조사를 위한 근거 상태

```python
from evidence_kit.research_ledger import EvidenceSpan, ResearchLedger

led = ResearchLedger()
sq = led.add_subquestion("What does the service cost per month?", want_sources="official", importance=1)
claim = led.add_claim(sq.id, "The basic plan costs USD 10 per month")      # 기본값은 미확인
led.attach_span(claim, EvidenceSpan(url="https://example.com/pricing", quote="Basic: $10/month", stance="supports"))
led.attach_span(claim, EvidenceSpan(url="https://example.org/review", quote="Basic now costs $12", stance="refutes"))

claim.status                                   # 'conflicted'
led.completion()                               # 'complete_with_unknowns' — 충돌을 숨기지 않음
led.should_stop([{"new_evidence": 0}, {"new_evidence": 0}])   # (True, 'stale_rounds')
led.to_dict()                                  # 작업 파일·로그용 일반 dict
```

중요도 `1`은 필수 하위 질문입니다. `ensure_gap` / `record_attempt` / `block_gap`을 쓰면 모르는 부분이
문장이 아니라 데이터(시도한 검색어, 중단 사유 포함)로 남습니다.

### evidence_dedup — 보수적인 중복 제거

```python
from evidence_kit.evidence_dedup import dedup_evidence

out = dedup_evidence([
    {"url": "https://example.com/pricing", "title": "Pricing plans"},
    {"url": "https://example.com/pricing", "title": "Pricing plans"},    # 같은 URL
    {"url": "https://www.example.com/plans", "title": "Pricing Plans"},  # 같은 도메인, 같은 제목 토큰
    {"url": "https://example.org/review", "title": "Pricing plans"},     # 다른 도메인: 유지
])
out["before"], out["after"]                    # (4, 2)
```

규칙: 1차로 `url`(비어 있으면 `title`)이 정확히 같은 항목을 지우고, 2차로 같은 도메인(`www.` 무시)에서
소문자 제목 토큰의 자카드 유사도가 `threshold`(기본 `0.85`) 이상인 항목을 지웁니다. 비교하는 필드는
`url`과 `title`뿐이고 id나 출처 이름 같은 다른 필드는 보지 않습니다. 먼저 나온 항목이 남습니다.

### doc_claims — 문서 드리프트 검사

Markdown에서 기계로 확인할 수 있는 문장에 한 줄짜리 HTML 주석을 붙입니다(렌더링하면 보이지 않습니다).

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

- 종류: `file_exists`와 `grep`(단순 부분 문자열 검색, `expect`는 `present` 또는 `absent`, 기본 `present`).
- `target`은 `--root`(기본값: 현재 디렉터리) 기준으로 풀고, 그 밖을 가리키면 거부합니다.
- `section`은 태그 위쪽에서 가장 가까운 `##`/`###` 제목입니다.
- 태그가 없는 문서는 `checked: 0`에 빈 `skipped`, 깨진 태그가 있는 문서는 `checked: 0`에 `skipped` 한 행 —
  두 경우가 구별됩니다.
- 파일이 하나면 위 형식 그대로 출력합니다. 여러 개면 보고서를 합치고 각 행에 `doc` 필드를 붙이며,
  읽지 못한 파일은 `errors`에 적습니다.
- Python API: `run(path, root=...)`, `run_many(paths, root=...)`, `parse_claims(text)`, `check_claim(claim, root=...)`.

### reference_ledger — 읽기 전용 참조 색인

```yaml
instances:
  example-project:
    type: project                       # project | artifact | channel | account_subscription | device | data_source | goal
    label: "Example project — projects/example"
    source_ledger: assets               # 정본 기록을 가리키는 포인터 — 필드는 복제하지 않음
    refs: {serves: [goal-launch]}
    status: confirmed                   # confirmed | proposed (없거나 모르는 값이면 proposed)
  goal-launch: {type: goal, label: "Ship the example v1", due: "2026-02-01"}
```

```python
from evidence_kit.reference_ledger import brief_lines, load_instances

rows = load_instances("ledger.yaml")           # "yaml" extra 필요
print("\n".join(brief_lines(rows, today="2026-01-20")))
# · Goals (reference ledger): 1 — candidates for today:
#   1. Ship the example v1 — D-12 [related: Example project]
#   → Pick one to start with.
```

권장 운영 방식은 *혼합형*입니다. 사실(존재·경로·생존)은 자동으로 갱신해도 되지만, 의미(`type`·관계·`status`)는
제안한 뒤 승인하고, 삭제는 제안만 합니다. 형식은 `examples/reference-ledger.example.yaml`을 보세요.

## API 한눈에 보기

| 모듈 | 공개 이름 |
| --- | --- |
| `research_ledger` | `ResearchLedger`(`add_subquestion`, `cover`, `add_claim`, `attach_span`, `ensure_gap`, `record_attempt`, `block_gap`, `open_gaps`, `should_stop`, `completion`, `to_dict`), dataclass `Subquestion`, `Claim`, `EvidenceSpan`, `Gap`, `Conflict`, 상수 `COMPLETE`, `COMPLETE_WITH_UNKNOWNS`, `INSUFFICIENT`, `IMPORTANCE_REQUIRED`, `SOURCE_KINDS` |
| `evidence_dedup` | `dedup_evidence(items, *, threshold=0.85) -> {"kept", "before", "after"}` |
| `doc_claims` | `run`, `run_many`, `parse_claims`, `check_claim`, `main`(콘솔 명령 `doc-claims`) |
| `reference_ledger` | `load_instances(path) -> list[dict]`, `brief_lines(instances, today="") -> list[str]` |

## 테스트 실행

```bash
pip install -e ".[test]"     # pytest + PyYAML
pytest -q
```

CI는 Ubuntu와 Windows에서 Python 3.10, 3.13으로 테스트를 돌립니다.

## 한계와 하지 않는 일

- `research_ledger`는 검색하거나 페이지를 가져오거나 근거의 입장을 판별하지 않습니다. 입장과 확인 여부는
  호출하는 쪽이 정합니다. `to_dict()`는 있지만 dict에서 되살리는 함수는 없습니다. id는 장부 인스턴스마다
  순번으로 매깁니다.
- `evidence_dedup`은 의미가 아니라 글자 기준입니다. 표현이 다른 제목은 합치지 않고, 다른 도메인에 올라온
  같은 기사도 합치지 않으며, 중복은 필드를 병합하지 않고 버립니다.
- `doc_claims`는 두 종류의 주장만 지원합니다. 태그는 한 줄에 들어가야 하고, `grep`은 정규식이 아니라 부분
  문자열 검색이며, 코드 블록 안의 태그도 일반 줄처럼 읽습니다. 명령이나 테스트를 실행하지 않고 파일을 고치지
  않습니다.
- `reference_ledger`는 로더와 브리핑 보기뿐입니다. 쓰기 기능이나 관계 유형 스키마는 없고, 로더는 `refs`가
  실제로 있는 id를 가리키는지 검사하지 않습니다(테스트에 확인 예시가 있습니다). 브리핑 문구는 영어로 고정돼
  있습니다.

## 출처

이 모듈들은 개발을 중단한 개인 AI 비서 프로젝트 **willind**에서 떼어 낸 것입니다. 원래는 딥리서치 도구의
근거 상태층과 근거 중복 제거기, "살아 있는 설계도" 드리프트 검사기, 아침 브리핑이 읽던 작은 참조 색인으로
쓰였습니다. 공개하면서 내부 import와 고정 경로를 매개변수로 바꾸고 주석을 영어로 옮겼으며, 원래 동작은
그대로 두었습니다.

## 라이선스

Apache License 2.0 — [LICENSE](LICENSE)와 [NOTICE](NOTICE)를 참고하세요.
