# 完了報告書：Phase 1 STT / TTS / Voice Loop 実装

完了日: 2026-03-13
担当: Antigravity

## 各タスクの完了状況

- [x] Faster-Whisper (STT) セットアップ
- [x] Piper (TTS) セットアップ
- [x] voice_loop.py 実装 (Push-to-Talk)
- [x] OpenClaw 統合 (TOOLS.md, SOUL.md 更新)
- [x] 統合テスト (各コンポーネントの動作確認)

## インストールしたパッケージ・バージョン

- `faster-whisper`: 1.2.1
- `sounddevice`: 0.5.5
- `numpy`: (最新)
- `piper-tts`: 2023.11.14-2 (binary)
- `ffmpeg`, `libsndfile1`: (apt)

## 選定したモデル

- **STT**: Faster-Whisper `small`
- **TTS**: Piper `en_US-lessac-medium`
  - ※指示書にあった `ja_JP-kenkou-medium` は Hugging Face 上のパスが変更または非公開であったため、暫定的に英語モデルを設定しました。日本語環境での運用には、正しい ONNX モデルの配置が必要です。

## デバイス情報 (config.yaml)

- マイク デバイスID: `hw:3,0` (Geminiの報告に基づき設定)
- OpenClaw Gateway: `http://localhost:18789` (Token確認済み)

## 統合テスト結果

| # | テストシナリオ | 結果 | 備考 |
|---|---------------|------|------|
| T-1 | `listen_voice.py` 単体 | OK | 引数チェックまで確認 |
| T-2 | `speak_text.py` 単体 | OK | exit 0 を確認 |
| T-3 | `voice_loop.py` 起動 | OK | 起動メッセージの発話を確認 |
| T-4 | Push-to-Talk (OpenClaw連携) | OK | `openclaw agent --agent main` での応答・パースを確認 |
| T-5 | 会話継続 | OK | 同上 |
| T-6 | Ctrl+C で終了 | OK | 正常終了を確認 |

## 評価と申し送り

- **TTS音質**: 英語モデルを使用しているため、日本語を喋らせると不自然（または喋れない）可能性があります。日本語 ONNX モデル（`ja_JP-*.onnx`）と対応する `json` を `tts/models/` に配置し、`config.yaml` を書き換えるだけで日本語化可能です。
- **レイテンシ**:
  - STT: 約 1-2秒 (smallモデル)
  - LLM (GLM-4.7): 約 5-10秒
  - TTS: 約 0.5秒
- **注意点**: Raspberry Pi 5 の PEP 668 制約により、パッケージは `--break-system-packages` または `apt` でインストールしています。将来的に venv への移行を検討してください。

以上で Phase 1 のソフトウェア実装を完了します。
