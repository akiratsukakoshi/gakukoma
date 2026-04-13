# 2026-03-13 Piper TTS 日本語モデル調査依頼

## 対象エージェント
Gemini

## 依頼背景

Phase 1 の STT/TTS/Voice Loop 実装が完了した。TTS エンジン（Piper TTS）は現在、英語モデル `en_US-lessac-medium` で暫定動作中。日本語対話を実現するために、日本語 ONNX モデルへの切り替えが必要。

## 調査してほしいこと

### 1. 日本語 Piper モデルの入手先
- Hugging Face `rhasspy/piper-voices` リポジトリに `ja_JP` モデルが存在するか確認
- 存在する場合: モデル名・品質ランク（low / medium / high）・ファイルの正確な URL
- 存在しない・取得困難な場合: 代替の入手方法（GitHub リリース、直接 DL リンク等）

### 2. 推奨モデルの提案
- Raspberry Pi 5 (aarch64, Cortex-A76, RAM 8GB) で実用的なレイテンシ（目標 < 1秒）で動くモデルを推奨
- `medium` と `low` の品質・速度トレードオフを教えてほしい

### 3. ダウンロード手順
- `wget` または `curl` で直接取得できるコマンドを記載
- `.onnx` ファイルと対応する `.json` ファイルの両方が必要

### 4. 注意点・既知の問題
- Hugging Face のパス変更・非公開化などのトラブル事例があれば記載

## 現在の環境情報

| 項目 | 内容 |
|---|---|
| 環境 | Raspberry Pi 5 (aarch64), Debian GNU/Linux 13 (trixie) |
| TTS エンジン | Piper TTS (rhasspy/piper) |
| 現在のモデル | `en_US-lessac-medium`（英語・暫定） |
| 必要ファイル形式 | `.onnx` + 同名 `.json` のペア |
| 配置先ディレクトリ | `~/voice_app/tts/models/` |
| 切り替え方法 | `config.yaml` の `tts.model_path` を書き換えるだけで完了 |

## 期待する回答形式

```
## 推奨モデル
- モデル名:
- 品質ランク:
- 推定レイテンシ（Pi5）:

## ダウンロードコマンド
wget <.onnx の URL>
wget <.json の URL>

## 注意事項
- ...
```

## 完了報告書の記載事項

調査完了後、以下の内容を含む完了報告書を `research/20260313_piper-tts-japanese-model_completed.md` として作成してください。

- 推奨モデル名・品質ランク・入手先 URL
- ダウンロードコマンド（`.onnx` + `.json`）
- Pi5 での推定レイテンシ（わかれば）
- 注意事項・既知の問題
- ClaudeCode・Antigravity への申し送り事項
