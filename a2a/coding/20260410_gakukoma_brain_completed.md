# 完了報告書: gakukoma_brain 実装

**日時**: 2026-04-14
**担当**: Claudeサブエージェント（コーディング担当）+ ClaudeCode（実機テスト解析）
**対応する指示書**: 20260410_gakukoma_brain_implementation.md

---

## 実装内容サマリー

`voice_loop.py → openclaw CLI（subprocess）→ Claude Haiku` という構成を、
`voice_loop.py → gakukoma_brain.py → Anthropic API（直接）→ Claude Haiku` に置き換えた。

主な変更点:
- `GAKUKOMABrain` クラスを新規作成し、Anthropic SDK直接呼び出し・ツール実行・会話履歴管理・日次メモ読み書きを一括管理
- `voice_loop.py` から OpenClaw 依存コード（`call_openclaw`, `build_message`, `_PRIMING_EXAMPLES`, セッション管理変数）を撤廃
- `voice_loop.py` は `call_brain()` 経由で `GAKUKOMABrain.invoke()` を呼ぶシンプルな構成に変更
- prompt caching（`cache_control: ephemeral`）を SYSTEM_PROMPT に適用

---

## 変更・作成したファイル一覧

| ファイル | 操作 |
|---|---|
| `/home/tukapontas/gakukoma/brain/gakukoma_brain.py` | 新規作成 |
| `/home/tukapontas/gakukoma/voice_loop/voice_loop.py` | 修正 |

ディレクトリ `/home/tukapontas/gakukoma/brain/` も新規作成。

---

## 実機テスト結果（2026-04-14）

| テスト | 内容 | 結果 |
|---|---|---|
| T-1 | 正常起動・音声「がくこまが起動しました。」出力 | **PASS** |
| T-2 | ウェイクワード→会話→スリープ・メモリ追記 | **PASS** |
| T-3 | トークン使用量確認 | **PASS**（詳細下記） |
| T-4 | 身体ツール連携（look_direction / see_around / look_at_user） | **PASS** |
| T-5 | キャラクター品質（2〜3文・繰り返しなし・定型句なし） | **PASS** |
| T-6 | エラーハンドリング | スキップ |
| T-7 | 日次メモ読み込み確認 | **PASS**（セッションサマリー追記確認済み） |
| T-8 | エラーハンドリング（APIキー無効） | スキップ |

### T-3 トークン実測値

| ターン | input tokens | cache_create | cache_read | output |
|---|---|---|---|---|
| Turn 1（右を見てくれる?） | 2,319 | 0 | 0 | 64 |
| Turn 2（もう一回） | 2,082 | 0 | 0 | 97 |
| Turn 3〜8 | 2,148〜2,539 | 0 | 0 | 36〜129 |

**input tokens: 旧 30,105 → 新 約 2,200〜2,500（約92%削減）**

#### キャッシュが効いていない理由（軽微・実害なし）

`cache_create=0` が続く原因は SYSTEM_PROMPT が短すぎてAnthropicキャッシュの最小閾値（claude-haiku-4-5: 2,048トークン）に届いていないため。ただし input tokens が既に ~2,300 と目標 12,000 を大幅下回っており、**キャッシュが効かなくても実用上の問題はない**。必要であれば後日 SYSTEM_PROMPT + TOOLS 定義を2,048トークン以上に増量して対応可。

### speak_textツール二重発話について

実機で問題なし。Claude が `speak_text` を呼んだターンの最終 output は 2〜3トークン（ほぼ空）になるため、`voice_loop.speak()` は実質何も発話しない。設計上意図通りの動作。

---

## 気づいた点・懸念事項

1. **`time` インポートが voice_loop.py に残存**: 使用箇所なし。指示書に削除指定がないためそのまま。
2. **APIキーパス固定**: `~/.openclaw/openclaw.json` を直接参照。パス変更時は修正必要。
3. **`local_history` の上限なし**: 長時間セッションでメモリ増加の可能性。必要に応じて上限トリムを追加すること。
4. **`max_tokens=200` 超過時**: `stop_reason=max_tokens` の場合は空文字列返却。現状未観測だが長応答要求時は注意。
