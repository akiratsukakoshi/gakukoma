# Phase 1 行動計画書：脳の覚醒と音声対話

作成日: 2026-03-11
作成者: ClaudeCode（司令塔）
対象フェーズ: Phase 1 — Brain & Voice

---

## 1. フェーズ目標

Raspberry Pi 5 上で、**音声で話しかけると音声で答える自律エージェント**を構築する。
この段階では物理的な移動・カメラ機能は不要。「動かないが賢く、話せる」状態がゴール。

---

## 2. 技術選定の結論

### 2.1 LLM（ブレイン）

| 選択肢 | 決定 | 理由 |
|--------|------|------|
| GLM-4.7（ZAI API） | **採用（初期）** | 無償・高速・日本語◎・OpenClaw既設定済み |
| Claude Haiku / Sonnet / Opus | 移行候補 | 品質不満時はコストと相談しながら切り替え |
| Ollama（ローカルLLM） | **不採用** | CPU専用のPi 5では品質・速度ともにGLM-4.7に劣る。Wi-Fiなし環境は現時点で不要 |

### 2.2 STT（音声→テキスト）

| 選択肢 | 決定 | 理由 |
|--------|------|------|
| Faster-Whisper（ローカル） | **採用** | トークン消費ゼロ・オフライン・日本語対応・aarch64動作確認済み |
| OpenAI Whisper API | 不採用 | 毎回APIコスト発生 |

使用モデル: `small`（日本語精度と速度のバランス点）
動作確認後に `medium` への変更も選択肢。

### 2.3 TTS（テキスト→音声）

| 選択肢 | 決定 | 理由 |
|--------|------|------|
| Piper（ローカル） | **採用** | トークン消費ゼロ・オフライン・日本語モデルあり・高速 |
| OpenAI TTS / ElevenLabs | 不採用 | APIコスト発生 |
| Microsoft Edge TTS | 候補 | Piperの日本語品質不満時のフォールバックとして検討 |

日本語音声モデル: `ja_JP-kenkou-medium`（rhasspy/piper-voices）

### 2.4 Wake Word

| フェーズ | 方針 |
|---------|------|
| Phase 1 | **なし（Push-to-Talkで実装）** — Enterキーで録音開始/終了 |
| Phase 1.5 | openWakeWord（OSS）を追加。「ねえがくこま」等のカスタム日本語ワード |

---

## 3. システムアーキテクチャ

```
ユーザー（Enterキー押下）
        ↓
[voice_loop.py] ← Pythonサービス
        ↓ arecord でUSBマイクから録音
[Faster-Whisper] → テキスト
        ↓ HTTP POST
[OpenClaw Gateway] (localhost:18789)
        ↓ GLM-4.7 が推論・ツール呼び出し
[OpenClaw Agent] → 応答テキスト
        ↓
[Piper TTS] → 音声ファイル
        ↓ aplay
[スピーカー]
```

### ツール定義（OpenClaw TOOLS.md に登録）

| ツール名 | 実体 | 呼び出し元 |
|---------|------|-----------|
| `listen_voice()` | `listen_voice.sh` → `listen_voice.py` | OpenClaw Agent |
| `speak_text(text)` | `speak_text.sh` → `speak_text.py` | OpenClaw Agent |

※ voice_loop.py からの入力（Push-to-Talk）とエージェントからのツール呼び出しは**両方**サポートする設計にする。

---

## 4. ディレクトリ構成（新規作成分）

```
/home/tukapontas/
├── gakukoma/                        ← Phase 1 実装ルート
│   ├── stt/
│   │   ├── listen_voice.py          ← Faster-Whisper STT（録音→テキスト変換）
│   │   └── requirements.txt
│   ├── tts/
│   │   ├── speak_text.py            ← Piper TTS（テキスト→音声再生）
│   │   ├── models/                  ← Piper 日本語音声モデル置き場
│   │   └── requirements.txt
│   ├── voice_loop/
│   │   ├── voice_loop.py            ← メイン音声対話ループ（Push-to-Talk）
│   │   ├── config.yaml              ← マイクデバイスID・モデル設定
│   │   └── requirements.txt
│   └── tools/                       ← OpenClaw カスタムツール用シェルラッパー
│       ├── listen_voice.sh
│       └── speak_text.sh
└── .openclaw/workspace/
    ├── TOOLS.md                     ← カスタムツール定義追記（既存ファイル更新）
    └── SOUL.md                      ← GAKUKOMAキャラクター定義（更新）
```

---

## 5. タスク一覧と担当

### ハードウェアタスク（Gemini担当）

| # | タスク | 指示書 |
|---|--------|--------|
| H-1 | USBマイク・スピーカー接続と動作確認 | `20260311_phase1_audio_hardware_setup_implementation.md` |

### ソフトウェアタスク（Antigravity担当）

| # | タスク | 依存 | 指示書 |
|---|--------|------|--------|
| S-1 | Faster-Whisper（STT）セットアップ | H-1完了後 | `20260311_phase1_stt_tts_voiceloop_implementation.md` |
| S-2 | Piper（TTS）セットアップ | H-1完了後 | 同上 |
| S-3 | voice_loop.py 実装（Push-to-Talk） | S-1, S-2 完了後 | 同上 |
| S-4 | OpenClaw統合（TOOLS.md・SOUL.md更新） | S-3 完了後 | 同上 |
| S-5 | エンドツーエンド統合テスト | S-4 完了後 | 同上 |

---

## 6. 技術的懸念点と対策

| リスク | 対策 |
|--------|------|
| Piper 日本語モデルの音質が不十分 | Microsoft Edge TTS（オンライン）をフォールバックとして設定 |
| Faster-Whisper `small` の誤認識 | `medium` モデルへの切り替え（速度とのトレードオフを計測） |
| USBマイクのデバイスID変動 | `config.yaml` で固定。`arecord -l` での確認手順を指示書に記載 |
| GLM-4.7 のレスポンス遅延 | タイムアウト設定、待機中のビープ音フィードバックで体験を補う |
| OpenClaw Gateway API 仕様の不明点 | Antigravity が `openclaw --help` および `/usr/lib/node_modules/openclaw/` を調査して解決 |

---

## 7. Phase 1.5（次のフェーズ予定）

- Wake Word 実装（openWakeWord + 日本語カスタムワード）
- 音声対話品質チューニング（Faster-Whisperモデル選定・Piper音声調整）
- SOUL.md の GAKUKOMAキャラクター詳細化

---

## 8. 完了条件

以下が全て動作することを確認する：

- [ ] USBマイクで音声を録音し、日本語テキストに変換できる
- [ ] テキストをPiperで日本語音声合成し、スピーカーから再生できる
- [ ] Enterキーで録音→STT→GLM-4.7推論→TTS→再生 の一連の流れが動く
- [ ] OpenClaw上のエージェントが `speak_text()` ツールを呼び出せる
- [ ] 「こんにちは」と話しかけると、自然な日本語で返答が返ってくる

