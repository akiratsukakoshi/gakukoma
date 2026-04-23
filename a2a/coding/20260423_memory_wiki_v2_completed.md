# 完了報告書: Memory Processor v2 ── Lint・Cross-reference・既存プロセス改善

**担当**: gakukoma-coder（Claudeサブエージェント）
**対象ファイル**: `/home/tukapontas/gakukoma/brain/memory_processor.py`
**完了日**: 2026-04-23

---

## 実装概要・変更行番号

### 改修1-A: ログトランケーション緩和（行 219）

`raw_logs[:3000]` → `raw_logs[:8000]` に変更。
- 変更箇所: `analyze_and_update_wiki()` の `analysis_prompt` f-string内
- 合わせて `max_tokens=500` → `max_tokens=600` に拡張（JSONフィールド追加分）

### 改修1-B: surprise_score / surprising_moment の追加（行 225-232、行 275-284）

- Step 1の `analysis_prompt` JSONスキーマに `surprise_score`（0-10整数）と `surprising_moment`（6以上の場合のみ記述）を追加
- Step 2bとして新設: `surprise_score >= 6` かつ `surprising_moment` が存在する場合、`wiki/surprises.md` に追記
- `surprises.md` フォーマット: `## YYYY-MM-DD（驚きスコア: N）` + surprising_momentの内容
- `print()` に `surprise_score` も表示するよう更新（行 261）

### 改修1-C: people/ プロンプト強化（行 303-320）

既存フォーマットに以下を追加:
- `初めて会った日:` フィールド
- `がくこまへの感情:` フィールド
- `がくこまの感情メモ:` フィールド
- プロンプト末尾に「既存ページの情報は削除せず保持すること」注記を追加
- `max_tokens=400` → `max_tokens=500` に拡張

### 改修1-D: places/ プロンプト強化（行 343-360）

既存フォーマットに以下を追加:
- `訪問回数:` フィールド
- `つながる場所:` フィールド
- `max_tokens=400` → `max_tokens=500` に拡張

### 改修1-E: _append_to_log() 関数の追加（行 96-107）

新規関数を `_rebuild_index()` の直後に定義:
- `wiki/log.md` が存在しない場合はヘッダーを付けて新規作成
- 既存内容に `## [YYYY-MM-DD] memory-update` エントリを追記
- `analyze_and_update_wiki()` の末尾（Step 5の後）で呼び出し
- `updates` リストには person・place・core_memory・surprises の更新情報を格納

### 改修2: _update_cross_references() 関数の追加（行 110-172）

新規関数:
- `people/`・`places/`・`core_memories.md` を収集（各ページ600文字でカット）
- ページ数が2未満の場合はスキップ
- Sonnetに全ページ俯瞰依頼 → JSON形式で `cross_references` リストを受け取る
- 各ページの `## 関連` セクションを置き換え or 末尾に追記
- `analyze_and_update_wiki()` のStep 4（index更新）の直後、Step 5として呼び出し

### 改修3: lint_wiki() 関数の追加（行 175-237）

新規関数:
- `people/`・`places/`・`core_memories.md`・`index.md` を収集（6000文字でカット）
- Sonnetに健全性チェック依頼（矛盾・不足ページ・孤立ページ・鮮度・REM連想・health_score・改善提案）
- 結果を `wiki/lint_report.md` に書き出し
- `rem_association` が存在する場合は `wiki/dreams.md` に追記
- `main()` で `datetime.now().weekday() == 0`（月曜日）のみ実行

---

## analyze_and_update_wiki() の最終フロー（Step 1〜5）

```
Step 1: 会話分析 + 感情スコア
  - raw_logs[:8000] をSonnetに渡す
  - JSON取得: summary / emotion_score / core_memory
             surprise_score / surprising_moment
             people_mentioned / new_facts_about_people / places_mentioned

Step 2: core_memories.md の更新
  - emotion_score >= 8 かつ core_memory が存在する場合に追記

Step 2b: surprises.md の更新（新規）
  - surprise_score >= 6 かつ surprising_moment が存在する場合に追記

Step 3: people/ ページの更新
  - people_mentioned の各人物についてSonnetでページ生成・更新
  - 強化フォーマット: 初めて会った日・がくこまへの感情・がくこまの感情メモ追加
  - 「既存情報保持」注記付き

Step 3b: places/ ページの更新
  - places_mentioned の各場所についてSonnetでページ生成・更新
  - 強化フォーマット: 訪問回数・つながる場所追加

Step 4: index.md の更新（_rebuild_index）

Step 5: cross-reference の更新（新規）
  - _update_cross_references() で全ページ間リンクを生成・更新

Step 後処理: log.md への記録（_append_to_log）
  - 更新した内容のリストを追記
```

---

## テスト実行結果

テストスクリプト `/tmp/test_memory_v2.py` を作成済み。

**テスト実行コマンド**:
```
python3 /tmp/test_memory_v2.py
```

テストは以下の順序で検証する:
1. 最新RAWログを対象に `analyze_and_update_wiki()` を実行
2. `lint_wiki()` を手動で実行（月曜日でなくても実行される）
3. index.md・log.md・lint_report.md・dreams.md・people/学長.md末尾を表示

**※ Bashツールの実行権限が付与されていなかったため、テスト実行はユーザーによる手動確認が必要。**

期待される出力例:
```
テスト対象: 2026-04-22_224717.md
分析完了: emotion_score=5, surprise_score=3
person-wiki更新: 学長
place-wiki更新: リビング
index.md再構築: 2026-04-22
cross-reference更新: people/学長
--- Lint テスト ---
lint完了: health_score=7
REM連想記録: がくこまは学長との会話を思い出した...
```

---

## 懸念事項

1. **surprise_score のJSON解析**: `analysis_prompt` に `0〜10の整数` という日本語コメントをJSONスキーマ例の中に記述しているため、まれにSonnetが数値ではなくコメント文字列を返す可能性がある。既存の `emotion_score` も同様の形式なので実績上問題ないとは思われるが、将来的には `int()` 変換でガードしておくと安全。

2. **cross-reference のページキー照合**: `page_key` が `"people/学長"` 形式で返ってきた場合、`wiki_dir / "people/学長.md"` として存在チェックしている。Sonnetがスペースや表記ゆれのあるキーを返すと `page_path.exists()` が `False` になってスキップされる。現状はエラーにはならないが、クロスリファレンスが一部スキップされる可能性がある。

3. **log.md の肥大化**: `_append_to_log()` は append-only のため、長期運用で log.md が肥大化する。現時点では削除・ローテーション機構がない。将来的に `cleanup_old_raw_logs()` と同様の仕組みを検討すること。

4. **lint_wiki() のトークン消費**: `pages_text[:6000]` でカットしているが、ページ数が増えた場合に情報が欠損する。現在のページ数（人物3名+場所数件）では問題ない。

5. **dreams.md の利用タイミング**: 指示書にある通り、現時点では生成するのみで `gakukoma_brain.py` の SYSTEM_PROMPT には注入していない。Phase 5.2以降での対応が必要。
