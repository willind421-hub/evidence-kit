# Evidence Kit

[English](README.md) | [한국어](README.ko.md) | **日本語**

調査結果の主張とドキュメントの記述を正直に保つための、小さなツールキットです。実行時の依存関係はありません。
互いに独立した 4 つのモジュールが、それぞれ 1 つの役割を担います。

| モジュール | 役割 |
| --- | --- |
| `evidence_kit.research_ledger` | サブ質問・主張・根拠スパン・未解決点（gap）・矛盾を記録し、いつ止めるか、回答がどこまで完結したかを*コードで*判定します。 |
| `evidence_kit.evidence_dedup` | 検索で集めた根拠の重複を除きます（URL の完全一致 → 同一ドメインの似たタイトル）。除去前後の件数も返します。 |
| `evidence_kit.doc_claims` | Markdown 内の `<!-- claim: {...} -->` タグを実際のソースツリーと照合します（`doc-claims` CLI）。 |
| `evidence_kit.reference_ledger` | 「何が存在するか」をまとめた小さな YAML 索引を読み取り専用で読み込み、目標の一覧をブリーフィング形式で表示します。 |

## 解決したい問題

調査やドキュメントのツールは、2 つの場所で静かに劣化します。

- **調査の回答。** 「要確認」が文章として残るだけで忘れられます。根拠のない主張が事実のように回答に混ざります。
  公開情報のない質問ではループが終わらないか、モデルが「完了」と言った時点で止まってしまいます。
  同じ検索結果が何度も拾われ、根拠が実際より多く見えます。
- **ドキュメント。** 設計書は、コードが変わった後も「モジュール X がある」「Y は接続済み」と書き続けます。

Evidence Kit は、こうした曖昧な記述を、中身を確認できる小さなデータ構造と決定的なルールに置き換えます。

## 保証すること

- **根拠のない主張は未確認のまま残ります。** 主張は明示的に確認するまで `unconfirmed` で、根拠を付けても
  自動では確認済みになりません。同じ主張に `supports` と `refutes` の根拠が両方付くと `conflicted` になり、
  *未解決*の矛盾レコードが作られます。勝者を自動で選ぶことはありません。
- **分からないことを隠しません。** 完了状態は `complete`、`complete_with_unknowns`、
  `insufficient_evidence` のいずれかです。未解決・ブロック中の gap、未解決の矛盾、カバーされていない
  サブ質問が 1 つでもあれば、`complete` ではなく `complete_with_unknowns` になります。
- **停止はコードが判定します。** 3 つの明示的な条件（必須の質問がすべて片付いた、新しい根拠のないラウンドが
  続いた、gap ごとの試行上限に達した）で判断し、理由も返します。
- **重複除去は保守的です。** ドメインが異なれば統合せず、タイトルが空の項目は残し、順序を保ち、
  除去前後の件数を必ず報告します。
- **ドキュメント検査は読み取り専用で、内容を漏らしません。** 結果は真偽の記述だけを報告し、ファイルの内容は
  含めません。ルート外の対象は拒否し、壊れたタグはドリフトではなく *skipped* として報告し、何も自動修正しません。
  終了コード `0` = ドリフトなし、`1` = ドリフトあり、または文書を読めなかった。
- **参照台帳ローダーは不正な入力で落ちません。** ファイルがない・壊れている場合は `[]`、不正な行は捨て、
  未知の `status` は `proposed` に格下げします。

## 設計

- 素の dataclass と純粋関数だけで構成しています。ネットワークアクセス、モデル呼び出し、グローバル状態はありません。
  検索エンジンや LLM は呼び出し側が受け持ち、これらのモジュールは根拠の状態を保持して判定するだけです。
- ファイルシステムに触れるのは `doc_claims`（Markdown と対象ファイルの読み取り）と `reference_ledger`
  （YAML ファイル 1 つの読み取り）だけで、どちらも読み取り専用です。
- 実行時の依存関係はありません。PyYAML は `reference_ledger.load_instances` だけが必要とするオプションの
  extra（`yaml`）で、未インストールの場合はインストール方法を示す `ImportError` になります。
- Python 3.10 以上。

## クイックスタート

PyPI には公開していないため、リポジトリを取得してインストールします。

```bash
pip install -e ".[yaml]"        # または pip install -e .（YAML ローダー以外）
python examples/quickstart.py   # 合成データで 4 つのモジュールをすべて実行
doc-claims --root . examples/sample-doc.md
```

## モジュール

### research_ledger — 反復調査のための根拠の状態

```python
from evidence_kit.research_ledger import EvidenceSpan, ResearchLedger

led = ResearchLedger()
sq = led.add_subquestion("What does the service cost per month?", want_sources="official", importance=1)
claim = led.add_claim(sq.id, "The basic plan costs USD 10 per month")      # 既定は未確認
led.attach_span(claim, EvidenceSpan(url="https://example.com/pricing", quote="Basic: $10/month", stance="supports"))
led.attach_span(claim, EvidenceSpan(url="https://example.org/review", quote="Basic now costs $12", stance="refutes"))

claim.status                                   # 'conflicted'
led.completion()                               # 'complete_with_unknowns' — 矛盾を隠さない
led.should_stop([{"new_evidence": 0}, {"new_evidence": 0}])   # (True, 'stale_rounds')
led.to_dict()                                  # ジョブファイルやログ用の普通の dict
```

重要度 `1` は必須のサブ質問です。`ensure_gap` / `record_attempt` / `block_gap` を使うと、分からない部分が
文章ではなくデータ（試した検索語や停止理由を含む）として残ります。

### evidence_dedup — 保守的な重複除去

```python
from evidence_kit.evidence_dedup import dedup_evidence

out = dedup_evidence([
    {"url": "https://example.com/pricing", "title": "Pricing plans"},
    {"url": "https://example.com/pricing", "title": "Pricing plans"},    # 同じ URL
    {"url": "https://www.example.com/plans", "title": "Pricing Plans"},  # 同じドメイン、同じタイトルトークン
    {"url": "https://example.org/review", "title": "Pricing plans"},     # 別ドメイン: 残す
])
out["before"], out["after"]                    # (4, 2)
```

ルール: 1 段目で `url`（空なら `title`）が完全に一致する項目を除き、2 段目で同じドメイン（`www.` は無視）の
中から、小文字化したタイトルトークンのジャカード係数が `threshold`（既定 `0.85`）以上の項目を除きます。
比較するのは `url` と `title` だけで、id や出典名などほかのフィールドは見ません。先に現れた項目が残ります。

### doc_claims — ドキュメントのドリフト検査

Markdown の中で機械的に確認できる記述に、1 行の HTML コメントを付けます（レンダリング時には表示されません）。

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

- 種類: `file_exists` と `grep`（単純な部分文字列検索。`expect` は `present` か `absent`、既定は `present`）。
- `target` は `--root`（既定: カレントディレクトリ）を基準に解決し、その外を指すものは拒否します。
- `section` はタグより上にある最も近い `##`/`###` 見出しです。
- タグのない文書は `checked: 0` で `skipped` が空、壊れたタグのある文書は `checked: 0` で `skipped` に 1 行 —
  2 つのケースは区別できます。
- ファイルが 1 つなら上の形式そのままで出力します。複数なら報告をまとめ、各行に `doc` フィールドを付け、
  読めなかったファイルは `errors` に列挙します。
- Python API: `run(path, root=...)`、`run_many(paths, root=...)`、`parse_claims(text)`、`check_claim(claim, root=...)`。

### reference_ledger — 読み取り専用の参照索引

```yaml
instances:
  example-project:
    type: project                       # project | artifact | channel | account_subscription | device | data_source | goal
    label: "Example project — projects/example"
    source_ledger: assets               # 正本レコードへのポインタ — フィールドは複製しない
    refs: {serves: [goal-launch]}
    status: confirmed                   # confirmed | proposed（未指定・未知の値は proposed）
  goal-launch: {type: goal, label: "Ship the example v1", due: "2026-02-01"}
```

```python
from evidence_kit.reference_ledger import brief_lines, load_instances

rows = load_instances("ledger.yaml")           # "yaml" extra が必要
print("\n".join(brief_lines(rows, today="2026-01-20")))
# · Goals (reference ledger): 1 — candidates for today:
#   1. Ship the example v1 — D-12 [related: Example project]
#   → Pick one to start with.
```

想定している運用は*ハイブリッド*です。事実（存在・パス・稼働状況）は自動更新してよく、意味（`type`・関係・
`status`）は提案してから承認し、削除は提案にとどめます。形式は `examples/reference-ledger.example.yaml` を参照してください。

## API 概要

| モジュール | 公開名 |
| --- | --- |
| `research_ledger` | `ResearchLedger`（`add_subquestion`、`cover`、`add_claim`、`attach_span`、`ensure_gap`、`record_attempt`、`block_gap`、`open_gaps`、`should_stop`、`completion`、`to_dict`）、dataclass `Subquestion`、`Claim`、`EvidenceSpan`、`Gap`、`Conflict`、定数 `COMPLETE`、`COMPLETE_WITH_UNKNOWNS`、`INSUFFICIENT`、`IMPORTANCE_REQUIRED`、`SOURCE_KINDS` |
| `evidence_dedup` | `dedup_evidence(items, *, threshold=0.85) -> {"kept", "before", "after"}` |
| `doc_claims` | `run`、`run_many`、`parse_claims`、`check_claim`、`main`（コンソールコマンド `doc-claims`） |
| `reference_ledger` | `load_instances(path) -> list[dict]`、`brief_lines(instances, today="") -> list[str]` |

## テストの実行

```bash
pip install -e ".[test]"     # pytest + PyYAML
pytest -q
```

CI では Ubuntu と Windows 上で、Python 3.10 と 3.13 を使ってテストします。

## 制限事項と対象外

- `research_ledger` は検索もページ取得も根拠の立場の判定も行いません。立場と確認の有無は呼び出し側が決めます。
  `to_dict()` はありますが、dict から復元する関数はありません。id は台帳インスタンスごとの連番です。
- `evidence_dedup` は意味ではなく文字列に基づきます。言い回しの違うタイトルは統合せず、別ドメインに転載された
  同じ記事も統合せず、重複はフィールドを併合せずに捨てます。
- `doc_claims` が扱う主張は 2 種類だけです。タグは 1 行に収める必要があり、`grep` は正規表現ではなく部分文字列
  検索で、コードブロック内のタグも通常の行と同じく読み取ります。コマンドやテストは実行せず、ファイルも変更しません。
- `reference_ledger` はローダーとブリーフィング表示だけです。書き込み機能や関係タイプのスキーマはなく、ローダーは
  `refs` が実在する id を指しているかを検査しません（確認方法はテストにあります）。ブリーフィングの文言は英語固定です。

## 由来

これらのモジュールは、開発を終了した個人用 AI アシスタントプロジェクト **willind** から切り出したものです。
もともとはディープリサーチ機能の根拠状態レイヤーと根拠の重複除去、「生きた設計書」のドリフト検査、
毎朝のブリーフィングが読む小さな参照索引として使われていました。公開にあたり、内部 import と固定パスを
パラメータに置き換え、コメントを英語に訳し、元の動作はそのまま残しています。

## ライセンス

Apache License 2.0 — [LICENSE](LICENSE) と [NOTICE](NOTICE) を参照してください。
