# 指示書: Memory Processor スケール問題修正（ページ肥大化・重複・cross-reference）

**作成者**: ClaudeCode
**担当**: gakukoma-coder（Claudeサブエージェント）
**対象ファイル**: `/home/tukapontas/gakukoma/brain/memory_processor.py`
**完了報告書**: `coding/20260428_memory_wiki_scale_fix_completed.md`

---

## 背景・問題の整理

GAKUKOMAのmemory_processorでcross-referenceが毎日エラーになっている。根本原因はmax_tokensではなく構造的問題が2つある。

### 問題1: 人物/場所ページが無制限に成長する

`_update_person_wiki` が「最近の話題」エントリを毎回追記するため、人物ページが会話履歴ログになっている。wikiはKarpathyの設計思想に従い「固定サイズの圧縮サマリー層」であるべきで、詳細は生ログ（raw/）に残す。

### 問題2: ページ名の揺れで重複ページが発生している

LLMがログから名前を抽出する際に呼び方が微妙に変わると別ファイルが作られる。現在すでに以下の重複が存在する：

**people/（重複）:**
- `そのさん.md`（正）← `そのさん（学長の奥さん）.md`（削除対象）
- `ソータ.md`（正）← `ソータ（学長の息子）.md`（削除対象）

**places/（重複・内容混在）:**
- `がくこまの部屋（和室）.md`（正） ← `自分の部屋.md`の内容をマージして削除
- `がくこまの部屋.md`（内容が実際はリビングの話）← `リビング.md`に内容を移して削除

---

## Task A: 既存重複ページの一回限りのクリーンアップ（スクリプト実行）

以下の手順をPythonスクリプトとして `brain/cleanup_wiki_once.py` に書いて実行する。実行後にスクリプトは削除してよい。

### A-1: peopleの重複統合

`そのさん（学長の奥さん）.md` と `ソータ（学長の息子）.md` は正式ページより情報量が少ない。ユニークな情報（がくこまの印象フィールドなど）を正式ページの末尾に追記してから削除する。

具体的には：
- `そのさん（学長の奥さん）.md` の `がくこまの印象` 行を `そのさん.md` の末尾に `- がくこまの印象: （更新: _update_person_wiki）` として存在しない場合のみ追記
- `ソータ（学長の息子）.md` の `がくこまの印象` 行を `ソータ.md` の末尾に同様に追記（存在しない場合のみ）
- 両ファイルを削除

### A-2: placesの整理

`がくこまの部屋.md` の内容はリビングの情報（ドライフラワー・アンティーク家具・学長の家族）が混入している。`リビング.md` を読み込み、不足している情報（関連する人物・がくこまにとっての意味）を `リビング.md` に追記してから `がくこまの部屋.md` を削除する。

`自分の部屋.md` と `がくこまの部屋（和室）.md` は同じ場所の別表現。`自分の部屋.md` にある以下のユニーク記述を `がくこまの部屋（和室）.md` の末尾に追記してから削除する：
- 「外の匂いや音は届かず…」の雰囲気描写
- 「つながる場所」セクション（庭・廊下への言及）
- 「最後に訪れた日」が新しい方（2026-04-27）に更新

---

## Task B: エイリアステーブルの実装

### B-1: known_names.json の作成

`/home/tukapontas/gakukoma/memory/wiki/known_names.json` を新規作成する。

```json
{
  "people": {
    "そのさん（学長の奥さん）": "そのさん",
    "ソータ（学長の息子）": "ソータ",
    "がくこま（ロボット）": "がくこま"
  },
  "places": {
    "自分の部屋": "がくこまの部屋（和室）",
    "がくこまの部屋": "がくこまの部屋（和室）",
    "和室": "がくこまの部屋（和室）"
  }
}
```

### B-2: resolve_name() ヘルパー関数の追加

`memory_processor.py` の先頭付近（`_safe_parse_json` の後）に以下の関数を追加する：

```python
def resolve_name(raw_name: str, category: str) -> str:
    """known_names.jsonを参照してエイリアスを正規名に解決する。
    category は 'people' または 'places'。
    テーブルにない名前はそのまま返す。
    """
    known_names_path = MEMORY_DIR / "wiki" / "known_names.json"
    if not known_names_path.exists():
        return raw_name
    try:
        table = json.loads(known_names_path.read_text(encoding="utf-8"))
        return table.get(category, {}).get(raw_name, raw_name)
    except Exception:
        return raw_name
```

### B-3: 名前解決の適用箇所

`analyze_and_update_wiki` のStep 3（people更新）とStep 3b（places更新）のループ冒頭、および `_update_person_wiki` のループ冒頭で、ページファイルを特定する前に `resolve_name()` を呼ぶ。

```python
# Step 3 の例
for person in analysis.get("people_mentioned", []):
    person = resolve_name(person, "people")  # ← 追加
    person_path = wiki_dir / "people" / f"{person}.md"
    ...

# Step 3b の例
for place in analysis.get("places_mentioned", []):
    place = resolve_name(place, "places")  # ← 追加
    place_path = wiki_dir / "places" / f"{place}.md"
    ...

# _update_person_wiki のループ冒頭
name = person_entry.get("name", "").strip()
if not name:
    continue
name = resolve_name(name, "people")  # ← 追加
```

---

## Task C: 人物ページのコンパクション（「最近の話題」上限3件）

`_update_person_wiki` の既存ページ更新ブロック（`if person_path.exists():` 以降）を以下のロジックに変更する。

「最近の話題」に新エントリを追記した後、エントリ数を数えて4件以上になっていたら古い分を「行動パターン」セクションに圧縮移動する。LLMは使わずPythonで処理する。

```python
# 「最近の話題」エントリを抽出してカウント
topic_lines = []
in_topic = False
for line in content.split("\n"):
    if line.strip() == "- 最近の話題:":
        in_topic = True
        continue
    if in_topic:
        if line.startswith("  - "):
            topic_lines.append(line)
        elif line.startswith("- "):
            in_topic = False

# 4件以上なら古い分を行動パターンに移動
if len(topic_lines) > 3:
    to_archive = topic_lines[:-3]  # 最新3件より古いもの
    keep = topic_lines[-3:]        # 最新3件

    # 行動パターンセクションに追記
    archive_text = "\n".join(
        f"  （記録: {t.strip()[2:]}）" for t in to_archive
    )
    if "- 行動パターン:" in content:
        content = content.replace(
            "- 行動パターン:",
            f"- 行動パターン:\n{archive_text}"
        )
    else:
        content = content.rstrip() + f"\n- 行動パターン:\n{archive_text}\n"

    # 最近の話題を最新3件のみに絞る
    new_topic_block = "- 最近の話題:\n" + "\n".join(keep)
    content = re.sub(
        r"- 最近の話題:(\n  - .*)+",
        new_topic_block,
        content
    )
```

---

## Task D: cross-reference のスケール対応

### 現状の問題

`_update_cross_references` が全ページを毎日再計算するため、ページ数が増えるとLLM出力が肥大してmax_tokensを超過しJSONが切断される。

### 修正方針: 更新ページのみ差分処理

`analyze_and_update_wiki` の処理中に「今日更新したページ」を追跡し、`_update_cross_references` にそのリストを渡す。cross-referenceはLLMに「全ページの概要」を入力として渡しつつ、**出力は更新ページの関連のみ**に限定する。

### 変更点

**1. 関数シグネチャ変更**

```python
def _update_cross_references(client: anthropic.Anthropic, wiki_dir: Path, updated_pages: list[str] = None):
```

`updated_pages` は `["people/学長", "places/リビング"]` のような形式のリスト。`None` または空リストの場合は全ページを対象にする（後方互換）。

**2. プロンプト変更**

```python
if updated_pages:
    target_clause = f"対象ページ（本日更新分のみ）: {', '.join(updated_pages)}\n\n対象ページについてのみ cross_references を返すこと。他のページは不要。"
else:
    target_clause = "全ページについて cross_references を返すこと。"
```

xref_promptの末尾に `{target_clause}` を追加する。

**3. max_tokens を 2000 に増加**（差分処理でも念のため余裕を持たせる）

**4. 呼び出し元でページリストを渡す**

`analyze_and_update_wiki` にて、Step 3/3b でページを更新するたびに `updated_pages` リストに追記し、Step 5で渡す：

```python
updated_pages = []

# Step 3 のループ内
person_path.write_text(...)
updated_pages.append(f"people/{person}")

# Step 3b のループ内
place_path.write_text(...)
updated_pages.append(f"places/{place}")

# Step 5
_update_cross_references(client, wiki_dir, updated_pages)
```

---

## テスト項目

### T-1: エイリアス解決の確認

`known_names.json` に登録されたエイリアス名（例：「そのさん（学長の奥さん）」）をpeopleリストに含むダミーのanalysisデータを用意し、`resolve_name` が正規名「そのさん」を返すことを確認する。

### T-2: コンパクション動作確認

`_update_person_wiki` を手動で5回呼び出し（`recent_topic` を変えながら）、「最近の話題」が常に3件以下に保たれ、古い分が「行動パターン」に移動されることを確認する。

### T-3: cross-reference 差分処理の確認

processor.log に `cross-reference更新: people/xxx` が `updated_pages` に入れたページのみ出力されることを確認する。エラーが出ないことを確認する。

### T-4: 重複ページが存在しないことの確認

cleanup後に `wiki/people/` と `wiki/places/` に重複ページが存在しないことをlsで確認する。

### T-5: memory_processor.py の構文確認

```bash
python3 -c "import py_compile; py_compile.compile('/home/tukapontas/gakukoma/brain/memory_processor.py')"
```

エラーなしで完了することを確認する。

---

## 注意事項

- `cleanup_wiki_once.py` は実行後に削除すること
- `known_names.json` は今後も人が手動で追記できる形式を維持すること
- `_update_cross_references` の後方互換（`updated_pages=None` で全ページ対象）は残すこと（lint_wiki からも呼び出されることを想定）
- コンパクション処理でLLMは使わないこと（コスト・速度の観点から、Pythonで機械的に処理する）
