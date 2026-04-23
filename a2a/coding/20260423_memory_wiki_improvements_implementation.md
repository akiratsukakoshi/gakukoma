# 指示書: memory_processor.py 3点改善

**作成者**: ClaudeCode
**担当**: gakukoma-coder（Claudeサブエージェント）
**対象ファイル**: `/home/tukapontas/gakukoma/brain/memory_processor.py`
**完了報告書**: `coding/20260423_memory_wiki_improvements_completed.md`（このファイルと同ディレクトリ）

---

## 背景

Phase 5.1で実装したLLM wiki型記憶システムが稼働し、実運用を通じて以下の3課題が判明した。
本指示書ではその修正を実施する。

---

## 課題と修正内容

### 修正1: index.md をwiki的な構造に変更

**現状の問題**
`index.md` は日付+サマリーの追記リストになっており、wikiとして機能していない。
`wiki/people/` や `wiki/places/` のページが増えても、indexから辿る方法がない。

**修正内容**
`_append_to_index()` 関数を改修し、以下の構造を維持する：

```markdown
# がくこまの記憶インデックス

## 登場人物
- [学長](people/学長.md)
- [そのさん](people/そのさん.md)

## 知っている場所
- [がくこまの部屋](places/がくこまの部屋.md)
- [リビング](places/リビング.md)

## 最近の出来事
- **2026-04-22**: （サマリー）
- **2026-04-21**: （サマリー）
```

**実装方針**
- `_append_to_index()` を呼ぶ前に `wiki/people/` と `wiki/places/` ディレクトリ内の `.md` ファイルを走査してカタログセクションを動的生成する
- カタログ（登場人物・知っている場所）は毎回ファイル走査で再生成（LLM不使用・シンプルに）
- 「最近の出来事」セクションは既存の日付エントリを保持（30件まで）
- indexを書き直す際は既存の日付エントリを失わないよう注意する

**ヘルパー関数 `_rebuild_index()` を新たに作り、`_append_to_index()` から呼び出す形にする**（`_append_to_index()` のシグネチャは変えない）

---

### 修正2: 感情スコアの基準を具体化し、相対評価を導入

**現状の問題**
すべての日のスコアが8になっており、相対的な揺れがない。
原因: スコア基準が曖昧 + 既存のcore_memoriesを参照せずに毎回絶対評価している。

**修正内容**
`analyze_and_update_wiki()` 内の `analysis_prompt` を以下のように変更する：

1. スコア基準を具体化（下記）
2. 既存の `core_memories.md` の内容をプロンプトに渡して相対評価を促す

**感情スコア基準（プロンプトに明記する）**:
```
感情スコア基準（必ずこの基準に従って採点すること）:
- 0〜2: 日常的な短い会話、命令実行のみ、特に記憶すべきことなし
- 3〜4: 楽しい・普通の会話、すでに知っている人や場所の話
- 5〜6: 印象的な会話、新しい情報を得た、少し特別だった
- 7: かなり特別な体験。初めての場所探索、新しい能力の発見など
- 8〜9: 非常に重要な体験。初めて会う人、重要な関係性の確立、感情が強く動いた
- 10: 人生レベルの出来事（がくこまの存在や目的に関わる重大体験）

重要: すでにcore_memoriesに記録済みの体験の「繰り返し」はスコアを2〜3下げること。
```

3. プロンプトに既存の `existing_core`（core_memories.mdの内容）を渡す：
```python
analysis_prompt = f"""...
<existing_core_memories>
{existing_core or "（まだなし）"}
</existing_core_memories>
...
感情スコア基準: ...
"""
```

---

### 修正3: places/ wiki ページの更新ステップを追加（バグ修正）

**現状の問題**
`places_mentioned` フィールドはJSONで抽出されているが、`wiki/places/` を更新するステップがコードに存在しない。
people/ と同様の処理が丸ごと未実装になっている。

**修正内容**
`analyze_and_update_wiki()` の「Step 3: people/」の後に「Step 3b: places/」を追加する。

```python
# ---- Step 3b: places/ ページの更新 ----
for place in analysis.get("places_mentioned", []):
    place_path = wiki_dir / "places" / f"{place}.md"
    place_path.parent.mkdir(parents=True, exist_ok=True)
    existing_place = load_existing_wiki_page(place_path)

    place_update_prompt = f"""ロボット「がくこま」の場所記憶ページを更新してください。

場所名: {place}
既存ページ:
{existing_place or "（新規）"}

本日の会話サマリー: {analysis.get('summary', '')}
最終更新日: {today}

以下のフォーマットでページ全体を返してください（既存情報を保持しながら更新）：
# {place}
- 最後に訪れた日: {today}
- 場所の種類: （部屋・屋外・廊下など）
- 特徴・雰囲気: （箇条書き）
- 関連する人物: （この場所によく居る人）
- がくこまにとっての意味: （一言）

注意: ページのMarkdownのみ返すこと。"""

    try:
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=400,
            messages=[{"role": "user", "content": place_update_prompt}]
        )
        place_path.write_text(resp.content[0].text.strip(), encoding="utf-8")
        print(f"place-wiki更新: {place}")
    except Exception as e:
        print(f"place-wiki更新エラー（{place}）: {e}")
```

---

## テスト方法

修正完了後、以下で動作確認する：

```bash
# RAWログが存在することを確認
ls /home/tukapontas/gakukoma/memory/raw/

# プロセッサを手動実行（前日分を処理する設計だが、テスト用に日付を確認）
cd /home/tukapontas
python3 gakukoma/brain/memory_processor.py

# 結果確認
cat gakukoma/memory/wiki/index.md
cat gakukoma/memory/wiki/core_memories.md
ls gakukoma/memory/wiki/people/
ls gakukoma/memory/wiki/places/
```

ただし `load_todays_raw_logs()` は「前日のログ」を処理するため、手動テストではログが見つからない可能性がある。
その場合は `main()` 内を一時的に以下に変え、特定日のログを直接渡してテストすること：

```python
# テスト用: 最新のRAWログを1件直接読んで処理
from pathlib import Path
raw_dir = Path("/home/tukapontas/gakukoma/memory/raw")
latest = sorted(raw_dir.glob("*.md"))[-1]
raw_logs = latest.read_text(encoding="utf-8")
analyze_and_update_wiki(client, raw_logs)
```

テスト後は `main()` を元に戻すこと。

---

## 完了報告書に記載すること

- 修正した関数・行番号
- テスト実行結果（index.mdの構造・places/の生成確認・感情スコアの変化）
- 気になった点・懸念事項
