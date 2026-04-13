# 指示書: トークン削減 - セッション管理修正 + ツールプロファイル最小化

作成日: 2026-03-22
担当: Antigravity
優先度: 高

---

## 背景・問題

voice_loop の実際のトークン使用量を計測したところ、**Turn 1: ~88K tokens / Turn 2: ~90K tokens** という非常に高い値を観測した。

分析の結果、主な原因は以下の2点：

### 問題1: セッションが実質リセットされていない（最大原因）

`voice_loop.py` のウェイクワード検出時に `self.session_id = None` にしているが、
`openclaw agent` に `--session-id` を渡さない場合、**デフォルトセッション（昨日からの会話履歴込み）が流用される**。

これにより、毎回の起動時に前のセッション全履歴（~15,000〜20,000トークン）が context に乗ってくる。

### 問題2: ツールスキーマが重い（~15,000〜20,000トークン）

現在 `tools.profile: "coding"` で16ツール全部が有効になっており、そのJSONスキーマがすべて毎回送られる。
GAKUKOMAが実際に必要なツールは `exec`（シェルスクリプト実行）と `write`（メモリノート書き込み）の**2つのみ**。

---

## タスク

### Task A: voice_loop.py - セッション管理修正

**ファイル**: `/home/tukapontas/gakukoma/voice_loop/voice_loop.py`

ウェイクワード検出時に **新しいセッションIDを生成**する。これにより各会話が独立したセッションとなり、前セッションの履歴が引き継がれない。

**変更箇所**: `run()` メソッド内のウェイクワード検出後の処理

```python
# 変更前
self.session_id = None
self.state = "listening"

# 変更後（importにuuidを追加して）
import uuid
# ...
self.session_id = str(uuid.uuid4())
self.state = "listening"
```

**注意**: UUIDを使う理由は、デフォルトセッション（履歴積み上がり）との縁を切るため。
メモリの永続化はセッション履歴ではなく `memory/YYYY-MM-DD.md` ファイル経由で行う（既存AGENTS.md設計通り）。

### Task B: openclaw.json - ツールプロファイル最小化

**ファイル**: `/home/tukapontas/.openclaw/openclaw.json`

`tools` セクションを以下に変更して、不要なツールのJSONスキーマをモデルに送らないようにする。

```json
"tools": {
  "profile": "coding",
  "deny": [
    "read", "edit", "apply_patch", "process",
    "memory_search",
    "sessions_list", "sessions_history", "sessions_send", "sessions_spawn",
    "subagents", "session_status", "cron", "image"
  ]
}
```

これにより GAKUKOMAが使えるのは `exec`（シェルスクリプト）・`write`（メモリ書き込み）・`memory_get`（メモリ読み込み）の3つになる。

- `exec`: 首振り・カメラ・TTSなど全てのシェルスクリプトツール
- `write`: `memory/YYYY-MM-DD.md` に日次ノートを書くため
- `memory_get`: 起動時に今日/昨日のメモリファイルをパス指定で読むため

`memory_search`（セマンティック検索）は現在 embedding provider 未設定のため実質無効。スキーマだけ送られて無駄なので deny。将来 Gemini の embedding API キーを設定する際に deny リストから外せばよい。

### Task C: IDENTITY.md の最小化

**ファイル**: `/home/tukapontas/.openclaw/workspace/IDENTITY.md`

現在、以下のようなブランクのテンプレートが入っており、**毎ターン ~150トークン消費している**。
このファイルはブートストラップ注入されるため、空にしても残し続けることで「MISSINGマーカー」表示を避けられる。
最小化する:

```markdown
# IDENTITY.md
```

（1行のみ。ブランクテンプレートの説明文を全削除）

---

## テスト手順

変更後、voice_loop.pyを起動して以下を確認：

**T-1**: ウェイクワード「ガクコマ」で起動後、Turn 1のログに表示される
`Token Usage -> cache_read_input_tokens: XXX, cache_creation_input_tokens: XXX` を確認。
目標: cache_creation_input_tokens が 10,000以下（現在44,513）

**T-2**: 2回のターンにわたって会話し、Turn 2の `cache_read_input_tokens` を確認。
目標: 30,000以下（現在89,093）

**T-3**: セッションを終了（「おやすみ」）→ 再度ウェイクワード起動 → 新しいセッションIDが振られることをログで確認。
（前のセッションIDと異なるUUIDが出ること）

**T-4**: exec ツールが使える（シェルスクリプト呼び出しが動作する）
→ 「周りを見て」「右を向いて」などの既存機能が動作すること

**T-5**: `openclaw config validate` でJSON設定にエラーがないこと

---

## 完了報告

完了後、`/home/tukapontas/a2a/coding/20260322_token_reduction_session_fix_completed.md` を作成。
計測値（Before/After のトークン数）を記載すること。
