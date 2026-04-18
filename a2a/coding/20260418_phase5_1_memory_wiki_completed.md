# 完了報告書: Phase 5.1 — LLM Wiki型記憶システム + 退屈行動（Intrinsic Motivation）

> **作成日**: 2026-04-18
> **担当**: ClaudeCode（claude-sonnet-4-6）
> **対応指示書**: `20260418_phase5_1_memory_wiki_implementation.md`

---

## 1. 実装したファイルの一覧

| ファイル | 操作 |
|---|---|
| `/home/tukapontas/gakukoma/memory/raw/` | ディレクトリ新規作成 |
| `/home/tukapontas/gakukoma/memory/episodes/` | ディレクトリ新規作成 |
| `/home/tukapontas/gakukoma/memory/wiki/people/` | ディレクトリ新規作成 |
| `/home/tukapontas/gakukoma/memory/wiki/places/` | ディレクトリ新規作成 |
| `/home/tukapontas/gakukoma/brain/gakukoma_brain.py` | 修正（定数追加・`end_session()`置換・`_load_daily_notes()`置換） |
| `/home/tukapontas/gakukoma/brain/memory_processor.py` | 新規作成 |
| `/home/tukapontas/gakukoma/voice_loop/voice_loop.py` | 修正（`import random`追加・`from datetime import datetime`追加・`_idle_start`追加・`_maybe_do_idle_action()`追加・呼び出し追加） |
| `/home/tukapontas/gakukoma/voice_loop/config.yaml` | 修正（`idle_behavior`セクション追加） |
| crontab | `0 3 * * *` エントリ追加 |

---

## 2. 各Stepの実施結果

### Step 1: ディレクトリ作成
- `raw/`, `episodes/`, `wiki/people/`, `wiki/places/` を作成。**OK**

### Step 2: `gakukoma_brain.py` の修正
- `MEMORY_DIR` / `LEGACY_MEMORY_DIR` 定数を `PRIMING_EXAMPLES` 直後に追加。
- `end_session()` を完全ログ保存版（raw/へ全会話ログ保存、旧ディレクトリへの後方互換確認）に置き換え。
- `_load_daily_notes()` をwiki参照版（フォールバック付き）に置き換え。**OK**

### Step 3: `memory_processor.py` 新規作成
- 指示書セクション3の内容を完全に実装。**OK**

### Step 4: `config.yaml` 修正
- `idle_behavior` セクションを末尾に追加。**OK**

### Step 5: `voice_loop.py` 修正
- `import random` と `from datetime import datetime` をインポートブロックに追加（既存になかったため追加）。
- `__init__` に `self._idle_start = None` を `self.audio_file` 設定の直後に追加。
- `_maybe_do_idle_action()` メソッドを `is_wakeword()` メソッドの直前に追加。
- IDLEループ内: `is_wakeword()` が False のとき（物音を拾ったがウェイクワードでなかった場合）に `_maybe_do_idle_action()` を呼び出し。
- ウェイクワード検出時（`brain.new_session()` の直前）に `self._idle_start = None` を追加。**OK**

### Step 6: cron設定
- `0 3 * * * python3 /home/tukapontas/gakukoma/brain/memory_processor.py >> /home/tukapontas/gakukoma/memory/processor.log 2>&1` を設定。**OK**

---

## 3. 構文確認結果（Step 7）

```
gakukoma_brain.py OK
memory_processor.py OK
voice_loop.py OK
```

3ファイルとも構文エラーなし。

---

## 4. memory_processor.py 単体実行結果（Step 8）

```
=== Memory Processor 開始 2026-04-18 11:05:37 ===
本日のRAWログなし。スキップ。
=== Memory Processor 完了 ===
```

本日のRAWログが存在しないため「スキップ」で正常終了。期待通り。

---

## 5. voice_loop.py の `_maybe_do_idle_action()` 呼び出し箇所

| 行番号 | 内容 |
|---|---|
| 103 | メソッド定義: `def _maybe_do_idle_action(self):` |
| 316 | IDLEループ内の呼び出し: `self._maybe_do_idle_action()` |

呼び出しタイミング: `record_wakeword_candidate()` → `is_wakeword()` チェック → **Falseの場合に呼び出し**。ウェイクワード検出時は呼び出されない。

---

## 6. 気づいた点・懸念事項

### 実装上の判断
- **`_maybe_do_idle_action()` の呼び出し位置について**: 指示書では「`record_wakeword_candidate()` 呼び出しの直後・`is_wakeword()` チェックの後」と記述されているが、`is_wakeword()` が False のブロック（`else:` 節）に配置した。これにより「物音を拾ってウェイクワードでなかった場合はリセットしない」という重要注意事項を満たしつつ、環境音のたびに時間が正しく積み上がる。

- **音が全くない間のアイドル動作タイミング**: `record_wakeword_candidate()` は音量閾値を超えるまでブロッキング待機するため、完全無音の環境では `_maybe_do_idle_action()` が呼ばれない。指示書の退屈行動設計（5分間隔）を考えると実用上は問題ないが、無音環境での確認は実機テストで確認が必要。

### 懸念事項
- **memory_processor.py の `time` import**: `_maybe_do_idle_action()` 内の移動処理に `import time` をローカルインポートしている（指示書通りの実装）。関数内での重複インポートは無害だが、将来的にはモジュールレベルに移動推奨。
- **wiki/index.md の同日重複チェック**: `_append_to_index()` の同日チェックは日付文字列（例: `2026-04-18`）が既存テキストに含まれているかで判断。index.md のエントリ行以外（例: コメント）に同じ日付が書かれていると誤判定する可能性があるが、現状の実装では問題になるシナリオはない。
- **旧メモリディレクトリ**: `/home/tukapontas/.openclaw/workspace/memory/` は削除していない。フォールバックで引き続き参照される。

---

*作成: ClaudeCode (claude-sonnet-4-6), 2026-04-18*
