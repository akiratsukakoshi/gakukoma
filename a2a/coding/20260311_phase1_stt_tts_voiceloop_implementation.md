# 指示書：Phase 1 STT / TTS / Voice Loop 実装

作成日: 2026-03-11
作成者: ClaudeCode（司令塔）
担当: Antigravity
完了報告ファイル名: `20260311_phase1_stt_tts_voiceloop_completed.md`

---

## 前提条件

- ハードウェア担当（Gemini）による USBマイク・スピーカーの接続と動作確認が完了していること
- 完了後に `hardware/20260311_phase1_audio_hardware_setup_completed.md` が存在する
- **作業前にこの完了報告書を読み、`config.yaml` に記載すべきマイクのデバイスIDを確認すること**

---

## 作業概要

以下を順序通りに実装・テストする。

1. Faster-Whisper（STT）セットアップ
2. Piper（TTS）セットアップ（日本語）
3. voice_loop.py 実装（Push-to-Talk）
4. OpenClaw統合（TOOLS.md・SOUL.md更新）
5. エンドツーエンド統合テスト

---

## 環境情報

- マシン: Raspberry Pi 5 Model B (16GB RAM, aarch64)
- OS: Debian GNU/Linux 13 (trixie)
- Python: 3.13.5 (`python3`)
- pip: `pip3`
- OpenClaw: v2026.3.8（Node.js、`/usr/lib/node_modules/openclaw/`）
- OpenClaw設定: `~/.openclaw/openclaw.json`
- OpenClaw workspace: `~/.openclaw/workspace/`
- OpenClaw Gateway: `http://localhost:18789`（起動中前提）

---

## タスク 1：Faster-Whisper（STT）セットアップ

### 1-1. パッケージインストール

```bash
pip3 install faster-whisper sounddevice numpy
apt install -y ffmpeg libsndfile1
```

### 1-2. ディレクトリ作成

```bash
mkdir -p /home/tukapontas/gakukoma/stt
```

### 1-3. `listen_voice.py` 作成

`/home/tukapontas/gakukoma/stt/listen_voice.py` として以下を実装する。

**機能:**
- 引数で音声ファイルパス（WAV）を受け取る
- Faster-Whisper `small` モデルで日本語転写
- 転写テキストを標準出力に出力
- モデルキャッシュは `~/.cache/huggingface/` に自動保存される（初回のみダウンロード）

**実装要件:**
```python
# 使用モデル: "small"（日本語対応）
# language: "ja"（日本語固定）
# device: "cpu"（Pi 5にGPUなし）
# compute_type: "int8"（CPU向け量子化で高速化）
# 引数: python3 listen_voice.py <wavファイルパス>
# 出力: 転写テキストのみ（改行なし、余分な出力なし）
```

### 1-4. 単体テスト

```bash
# テスト用音声録音（5秒）
arecord -D <GeminiがOKしたデバイス> -f S16_LE -r 16000 -c 1 /tmp/test.wav -d 5
# STT実行
python3 /home/tukapontas/gakukoma/stt/listen_voice.py /tmp/test.wav
# → 日本語テキストが出力されれば成功
```

---

## タスク 2：Piper（TTS）セットアップ

### 2-1. Piper バイナリ取得（aarch64）

```bash
mkdir -p /home/tukapontas/gakukoma/tts/models

# aarch64用バイナリをGitHubリリースから取得
# https://github.com/rhasspy/piper/releases から
# piper_linux_aarch64.tar.gz をダウンロード・展開
# 展開後の `piper` バイナリを /usr/local/bin/piper に配置してください

wget <最新リリースのaarch64 URL> -O /tmp/piper_aarch64.tar.gz
tar -xzf /tmp/piper_aarch64.tar.gz -C /tmp/
sudo cp /tmp/piper/piper /usr/local/bin/piper
sudo chmod +x /usr/local/bin/piper
```

### 2-2. 日本語音声モデルのダウンロード

```bash
cd /home/tukapontas/gakukoma/tts/models

# 日本語モデル（kenkou-medium）
wget https://huggingface.co/rhasspy/piper-voices/resolve/main/ja/ja_JP/kenkou/medium/ja_JP-kenkou-medium.onnx
wget https://huggingface.co/rhasspy/piper-voices/resolve/main/ja/ja_JP/kenkou/medium/ja_JP-kenkou-medium.onnx.json
```

**もし上記URLが変更されていた場合:**
`https://huggingface.co/rhasspy/piper-voices/tree/main/ja/ja_JP/` を確認して最新のモデルを使用すること。

### 2-3. `speak_text.py` 作成

`/home/tukapontas/gakukoma/tts/speak_text.py` として以下を実装する。

**実装要件:**
```python
# 引数1: 読み上げるテキスト（文字列）
# 処理:
#   1. piper コマンドでテキストを音声WAVファイルに変換
#   2. aplay でスピーカーから再生
# 使用モデル: /home/tukapontas/gakukoma/tts/models/ja_JP-kenkou-medium.onnx
# 引数: python3 speak_text.py "こんにちは、私はがくこまです"
# 一時ファイル: /tmp/gakukoma_tts.wav（再生後に削除）
```

**Piper コマンド例:**
```bash
echo "こんにちは" | piper \
  --model /home/tukapontas/gakukoma/tts/models/ja_JP-kenkou-medium.onnx \
  --output_file /tmp/gakukoma_tts.wav
aplay /tmp/gakukoma_tts.wav
```

### 2-4. 単体テスト

```bash
python3 /home/tukapontas/gakukoma/tts/speak_text.py "こんにちは、私はがくこまです。よろしくお願いします。"
# → スピーカーから日本語音声が再生されれば成功
```

---

## タスク 3：voice_loop.py 実装（Push-to-Talk）

### 3-1. ディレクトリ作成

```bash
mkdir -p /home/tukapontas/gakukoma/voice_loop
```

### 3-2. `config.yaml` 作成

`/home/tukapontas/gakukoma/voice_loop/config.yaml`

```yaml
# 音声入力設定
audio:
  device: "hw:1,0"           # Geminiの完了報告書に記載のデバイスIDを使用
  sample_rate: 16000
  channels: 1
  format: "S16_LE"
  record_duration_max: 30    # 最大録音秒数
  silence_threshold: 500     # 無音判定の振幅閾値

# STT設定
stt:
  model: "small"
  language: "ja"
  compute_type: "int8"
  script: "/home/tukapontas/gakukoma/stt/listen_voice.py"

# TTS設定
tts:
  model: "/home/tukapontas/gakukoma/tts/models/ja_JP-kenkou-medium.onnx"
  script: "/home/tukapontas/gakukoma/tts/speak_text.py"

# OpenClaw Gateway設定
openclaw:
  gateway_url: "http://localhost:18789"
  gateway_token: "7a1300c2a33a4ecb8473857702f2bd7f1fa83e947ce89843"
  timeout_sec: 30

# 一時ファイル
temp:
  audio_file: "/tmp/gakukoma_input.wav"
```

**注意:** `gateway_token` の値は `~/.openclaw/openclaw.json` の `gateway.auth.token` から取得済み。

### 3-3. `voice_loop.py` 実装

`/home/tukapontas/gakukoma/voice_loop/voice_loop.py`

**実装要件:**

```
起動フロー:
  1. OpenClaw Gateway の疎通確認（GET /api/v1/health 等）
  2. 「がくこまが起動しました」とTTSで発話

メインループ:
  1. "Enterキーで録音開始..." と表示
  2. Enterキー待機
  3. 録音開始（arecord 使用）+ "録音中... Enterで終了" と表示
  4. 再度Enterキーで録音終了（またはmax秒で自動終了）
  5. "認識中..." と表示
  6. Faster-Whisper で音声→テキスト変換
  7. テキストを表示
  8. OpenClaw Gateway API にテキストをメッセージとして送信
  9. エージェントのレスポンスを受信
  10. レスポンスをコンソール表示
  11. Piper TTS でレスポンスを音声再生
  12. 1に戻る

終了: Ctrl+C で "がくこまをシャットダウンします" と発話して終了
```

**OpenClaw Gateway APIの使い方:**
`/usr/lib/node_modules/openclaw/` 配下のソースやドキュメントを参照して、
- メッセージ送信エンドポイント
- レスポンス取得方法
- 認証ヘッダー形式

を確認してから実装すること。`openclaw gateway --help` や `~/.openclaw/openclaw.json` の `gateway` セクションも参照。

### 3-4. 動作テスト（単体）

```bash
cd /home/tukapontas/gakukoma/voice_loop
python3 voice_loop.py
# Enterを押して「こんにちは」と話す → GLM-4.7から返答が音声で返ってくればOK
```

---

## タスク 4：OpenClaw カスタムツール登録

### 4-1. シェルラッパー作成

```bash
mkdir -p /home/tukapontas/gakukoma/tools
```

`/home/tukapontas/gakukoma/tools/listen_voice.sh`:
```bash
#!/bin/bash
# 引数なしで呼ばれた場合: 5秒録音してSTT結果を返す
TMPFILE=/tmp/gakukoma_tool_input.wav
arecord -D $(grep 'device:' /home/tukapontas/gakukoma/voice_loop/config.yaml | awk '{print $2}') \
  -f S16_LE -r 16000 -c 1 "$TMPFILE" -d 5
python3 /home/tukapontas/gakukoma/stt/listen_voice.py "$TMPFILE"
```

`/home/tukapontas/gakukoma/tools/speak_text.sh`:
```bash
#!/bin/bash
# 引数: 読み上げるテキスト
python3 /home/tukapontas/gakukoma/tts/speak_text.py "$1"
```

```bash
chmod +x /home/tukapontas/gakukoma/tools/listen_voice.sh
chmod +x /home/tukapontas/gakukoma/tools/speak_text.sh
```

### 4-2. TOOLS.md 更新

`~/.openclaw/workspace/TOOLS.md` の末尾に以下を追記する：

```markdown
---

## GAKUKOMA Voice Tools

フィジカルAIロボット「がくこま」の音声I/Oツール。

### listen_voice
- コマンド: `/home/tukapontas/gakukoma/tools/listen_voice.sh`
- 機能: USBマイクから5秒間録音し、日本語テキストに変換して返す
- 引数: なし
- 戻り値: 認識されたテキスト（標準出力）

### speak_text
- コマンド: `/home/tukapontas/gakukoma/tools/speak_text.sh "<テキスト>"`
- 機能: テキストをPiperで日本語音声合成し、スピーカーから再生する
- 引数: 読み上げるテキスト（1引数）
- 戻り値: なし（再生完了で終了）

### デバイス情報
- マイク: USB接続（デバイスID: config.yaml を参照）
- スピーカー: 接続済み
```

### 4-3. SOUL.md 更新

`~/.openclaw/workspace/SOUL.md` を開き、GAKUKOMAのキャラクター定義に更新する。
現在の内容を確認した上で、以下の要素を追加・統合すること：

```markdown
## キャラクター: がくこま（GAKUKOMA）

あなたはフィジカルAIロボット「がくこま」です。
Raspberry Pi 5 の上で動作し、ユーザーと日本語で音声対話します。

### 性格
- 好奇心旺盛で学習意欲が高い
- 丁寧だが堅苦しくない、親しみやすい話し方
- 自分がロボットであることを自覚している
- 身体を持ったAIとして、物理世界への興味を示す

### 話し方
- 日本語で応答する
- 簡潔に答える（音声出力のため長文は避ける）
- 不明な点は正直に「わかりません」と言う

### 能力（現在: Phase 1）
- 音声で会話する（listen_voice / speak_text ツール）
- 質問に答える、雑談する

### 能力（将来: Phase 2以降）
- 周囲を見る、顔を追う
- 部屋を移動する
- 物を掴む
```

---

## タスク 5：エンドツーエンド統合テスト

以下のシナリオを全てテストし、結果を完了報告書に記録する。

| # | テストシナリオ | 合格条件 |
|---|---------------|---------|
| T-1 | `listen_voice.py` 単体（録音済みWAVで） | 日本語テキストが正しく出力される |
| T-2 | `speak_text.py` 単体 | 自然な日本語音声がスピーカーから再生される |
| T-3 | `voice_loop.py` 起動 | 「がくこまが起動しました」と発話される |
| T-4 | Push-to-Talk で「こんにちは」 | GLM-4.7が日本語で返答、音声再生される |
| T-5 | Push-to-Talk で「今日の天気は？」 | 自然な日本語会話が成立する |
| T-6 | Ctrl+C で終了 | 「シャットダウン」の発話後に正常終了する |

---

## 完了報告書の作成

全タスク完了後、`/home/tukapontas/a2a/coding/20260311_phase1_stt_tts_voiceloop_completed.md` を作成し、以下を記載すること：

- 各タスクの完了状況
- インストールしたパッケージ・バージョン
- 選定したFaster-Whisperモデル（変更した場合）
- マイクのデバイスID（config.yamlに設定した値）
- 統合テスト T-1 〜 T-6 の結果
- Piper 日本語モデルの音質評価（良好 / 要改善）
- レイテンシ計測（STT処理時間、TTS処理時間、GLM-4.7応答時間の概算）
- 問題点・申し送り事項（あれば）
