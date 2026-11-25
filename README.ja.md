# Evidence Kit

[English](README.md) | [한국어](README.ko.md) | **日本語**

調査結果の主張とドキュメントの記述を正直に保つための、小さなツールキットです。実行時の依存関係はありません。
互いに独立した 4 つのモジュールが、それぞれ 1 つの役割を担います。

| モジュール | 役割 |
| --- | --- |
| `evidence_kit.research_ledger` | サブ質問・主張・根拠スパン・未解決点（gap）・矛盾を記録し、いつ止めるか、回答がどこまで完結したかを*コードで*判定します。 |
| `evidence_kit.evidence_dedup` | 既定では完全一致する URL だけを除去します。類似タイトルの統合は任意で、件数と除去理由も返します。 |
| `evidence_kit.doc_claims` | Markdown 内の `<!-- claim: {...} -->` タグを実際のソースツリーと照合します（`doc-claims` CLI）。 |
| `evidence_kit.reference_ledger` | 「何が存在するか」をまとめた小さな YAML 索引を読み取り専用で読み込み、目標の一覧をブリーフィング形式で表示します。 |

## 解決したい問題

調査やドキュメントのツールは、2 つの場所で静かに劣化します。

- **調査の回答。** 「要確認」が文章として残るだけで忘れられます。根拠のない主張が事実のように回答に混ざります。
  公開情報のない質問ではループが終わらないか、モデルが「完了」と言った時点で止まってしまいます。
  同じ検索結果が何度も拾われ、根拠が実際より多く見えます。
- **ドキュメント。** 設計書は、コードが変わった後も「モジュール X がある」「Y は接続済み」と書き続けます。

Evidence Kit は、こうした曖昧な記述を、中身を確認できる小さなデータ構造と決定的なルールに置き換えます。

## 動作と信頼境界

- **根拠のない主張は未確認のまま残ります。** 主張は明示的に確認するまで `unconfirmed` で、根拠を付けても
  自動では確認済みになりません。同じ主張に `supports` と `refutes` の根拠が両方付くと `conflicted` になり、
  *未解決*の矛盾レコードが作られます。勝者を自動で選ぶことはありません。
- **完了判定は呼び出し側が渡した根拠状態に基づきます。** 空でない根拠 URL がなければ
  `insufficient_evidence` です。それ以外でも、未解決・ブロック中の gap、未解決の矛盾、未カバーの質問、
  未確認の主張や支持する URL のない主張があれば `complete_with_unknowns` です。必須質問に主張が
  ない場合も `complete` にはなりません。出典の真偽や品質は検証しません。
- **停止はコードが判定します。** 3 つの明示的な条件（必須の質問がすべて片付いた、新しい根拠のないラウンドが
  続いた、gap ごとの試行上限に達した）で判断し、理由も返します。
- **既定の重複除去は URL の完全一致だけです。** 異なるパスや URL のない項目は残します。先の項目を
  残し、件数と元入力の除去インデックス・理由を報告します。類似タイトルの統合は明示的な選択で、
  別の出典を失う可能性があります。出典の同一性を証明するものではありません。
- **文書検査は読み取り専用ですが機密性を保証しません。** 一致した本文は出力しませんが、真偽結果も
  内容を明かすオラクル（boolean oracle）になります。既定では grep は無効で、信頼した呼び出し側の
  設定だけが機密でない正確な対象ファイルを許可できます。ルート制限は機密性の境界ではありません。
  壊れたタグや閉じていないタグは `skipped` として検証を失敗させ、検査 0 件の文書も失敗します。
  全文書に検査があり、ドリフト・スキップ・読み取りエラーがなければ終了 `0`、それ以外は `1` です。
- **YAML ローダーは一般的な不正入力を処理します。** ファイルなし・読み取り失敗、不正な UTF-8、
  YAML 構文エラー、マッピング以外の最上位値は `[]` です。不正な行は捨て、未知の `status` は
  `proposed` にします。無制限入力の隔離やリソース枯渇の防止までは保証しません。

## 設計

- 素の dataclass と純粋関数だけで構成しています。ネットワークアクセス、モデル呼び出し、グローバル状態はありません。
  検索エンジンや LLM は呼び出し側が受け持ち、これらのモジュールは根拠の状態を保持して判定するだけです。
- ファイルシステムに触れるのは `doc_claims`（Markdown と対象ファイルの読み取り）と `reference_ledger`
  （YAML ファイル 1 つの読み取り）だけで、どちらも読み取り専用です。
- 実行時の依存関係はありません。PyYAML は `reference_ledger.load_instances` だけが必要とするオプションの
  extra（`yaml`）で、未インストールの場合はインストール方法を示す `ImportError` になります。
- Python 3.10 以上。

## クイックスタート

このチェックアウトからインストールしてください。パッケージ索引の同名項目の所有者は推測しないでください。

```bash
pip install -e ".[yaml]"        # または pip install -e .（YAML ローダー以外）
python examples/quickstart.py   # 合成データで 4 つのモジュールをすべて実行
doc-claims --root . --allow-grep src/evidence_kit/doc_claims.py --allow-grep src/evidence_kit/evidence_dedup.py examples/sample-doc.md
doc-claims --root . examples/invalid-doc.md  # 想定される終了 1: 壊れたタグ
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

停止と完了は別です。必須質問が片付いても根拠が不足・未確認なら `required_settled` で停止できます。
`required_covered` は完了状態が `complete` のときだけ返します。新しい根拠のないラウンドや試行上限でも
未完了の調査を止めます。確認・出典の適合性と品質・有効な状態値・主張と質問の対応は呼び出し側の責任です。

### evidence_dedup — 保守的な重複除去

```python
from evidence_kit.evidence_dedup import dedup_evidence

out = dedup_evidence([
    {"url": "https://example.com/pricing", "title": "Pricing plans"},
    {"url": "https://example.com/pricing", "title": "Pricing plans"},    # 同じ URL
    {"url": "https://www.example.com/plans", "title": "Pricing Plans"},  # 同じドメイン、同じタイトルトークン
    {"url": "https://example.org/review", "title": "Pricing plans"},     # 別ドメイン: 残す
])
out["before"], out["after"]                    # (4, 3)
out["merged"]  # [{"kept_index": 0, "dropped_index": 1, "reason": "exact_url"}]
```

既定では空でない文字列 URL の完全一致だけを除去します（URL 正規化やタイトルへの代替なし）。
`merge_similar=True` のときだけ、同一ドメイン（`www.` は無視）の小文字化したタイトルトークンの
ジャカード係数が `threshold`（既定 `0.85`）以上の項目も除きます。異なる版でも同じタイトルになり得るため、
損失を許容するときだけ有効にしてください。監査インデックスは元入力の 0 始まりの位置で、理由は
`exact_url` または `similar_title` です。dict 以外は無視して件数にも含めません。フィールド単位の併合は
しないため、除去されるメタデータが必要なら元入力を保存してください。

### doc_claims — ドキュメントのドリフト検査

Markdown の中で機械的に確認できる記述に、1 行の HTML コメントを付けます（レンダリング時には表示されません）。

```markdown
## Storage
The loader lives in its own module.
<!-- claim: {"type": "file_exists", "target": "src/pkg/loader.py"} -->
<!-- claim: {"type": "grep", "target": "src/pkg/loader.py", "pattern": "def load(", "expect": "present"} -->
```

```bash
doc-claims --root path/to/project --allow-grep src/pkg/loader.py docs/design.md docs/other.md
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
- `file_exists` はディレクトリではなくファイルを要求します。タグのファイル・部分文字列の主張だけを
  検査し、実行時の動作、接続状態、セキュリティや文書全体の正しさは証明しません。
- 各 `grep` 対象に `--allow-grep TARGET`（繰り返し可）または API `grep_allowlist=[...]` が必要です。
  既定では内容の読み取り許可は 0 件です。信頼できない文書から許可リストを作ったり機密ファイルを
  許可したりしないでください。選んだパターンと真偽結果だけでも許可された内容を推測できます。
- `target` は `--root`（既定: カレントディレクトリ）を基準に解決し、その外を指すものは拒否します。
- `section` はタグより上にある最も近い `##`/`###` 見出しです。
- タグのない文書は `checked: 0` で `skipped` が空、壊れたタグのある文書は `checked: 0` で `skipped` に 1 行 —
  2 つのケースは区別できます。
- ファイルが 1 つなら上の形式そのままで出力します。複数なら報告をまとめ、各行に `doc` フィールドを付け、
  読めなかったファイルは `errors` に列挙します。
- Python API: `run(path, root=..., grep_allowlist=())`、`run_many(paths, root=..., grep_allowlist=())`、
  `parse_claims(text)`、`check_claim(claim, root=..., grep_allowlist=())`。

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

引用符付き ISO 日付と PyYAML の引用符なし `date` 値は、どちらも文字列で返します。不正な入れ子フィールドは
除去または既定値にし、不正な行があっても有効な隣接行は残します。ただし不正な引用符なし日付を含む YAML
構文エラーはファイル全体を拒否します。空・拒否・存在しないファイルはいずれも `[]` で区別する診断はありません。
PyYAML 未導入時は `[]` ではなく `ImportError` です。`pyyaml` またはローカルの `.[yaml]` extra を導入してください。

## API 概要

| モジュール | 公開名 |
| --- | --- |
| `research_ledger` | `ResearchLedger`（`add_subquestion`、`cover`、`add_claim`、`attach_span`、`ensure_gap`、`record_attempt`、`block_gap`、`open_gaps`、`should_stop`、`completion`、`to_dict`）、dataclass `Subquestion`、`Claim`、`EvidenceSpan`、`Gap`、`Conflict`、定数 `COMPLETE`、`COMPLETE_WITH_UNKNOWNS`、`INSUFFICIENT`、`IMPORTANCE_REQUIRED`、`SOURCE_KINDS` |
| `evidence_dedup` | `dedup_evidence(items, *, threshold=0.85, merge_similar=False) -> {"kept", "before", "after", "merged"}` |
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
- `evidence_dedup` は意味ではなく文字列に基づきます。同じ URL でも内容が不変である証明にはなりません。
  任意のタイトル統合は別のページを失う可能性があり、別ドメインの転載は残します。
- `doc_claims` が扱う主張は 2 種類だけです。タグは 1 行に収める必要があり、`grep` は正規表現ではなく部分文字列
  検索で、コードブロック内のタグも通常の行と同じく読み取ります。コマンドやテストは実行せず、ファイルも変更しません。
- `reference_ledger` はローダーとブリーフィング表示だけです。書き込み機能や関係タイプのスキーマはなく、ローダーは
  `refs` が実在する id を指しているかを検査しません（確認方法はテストにあります）。ブリーフィングの文言は英語固定です。

## 由来

これらのモジュールは、開発を終了した個人用 AI アシスタントプロジェクト **willind** から切り出したものです。
もともとはディープリサーチ機能の根拠状態レイヤーと根拠の重複除去、「生きた設計書」のドリフト検査、
毎朝のブリーフィングが読む小さな参照索引として使われていました。公開にあたり、内部 import と固定パスを
パラメータに置き換え、コメントを英語に訳しました。核となる設計は保ちつつ、上記のレビュー修正で検証条件と
安全な既定値を意図的に強化しています。

## ライセンス

Apache License 2.0 — [LICENSE](LICENSE) と [NOTICE](NOTICE) を参照してください。
