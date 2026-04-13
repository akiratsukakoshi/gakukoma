# 完了報告書：Phase 1 統合テスト・チューニング

完了日: 2026-03-15
担当: ClaudeCode（司令塔・直接対応）

---

## 概要

Phase 1 の全コンポーネント（STT / TTS / Voice Loop / ハードウェア）の統合テストを実施した。
テスト中に発見された4件の不具合・改善課題をその場で修正し、全て解消した。

---

## 統合テスト結果

| 確認項目 | 結果 | 備考 |
|---|---|---|
| スピーカー音声出力（ノイズ確認） | ✅ 合格 | はんだ付け後、ノイズ完全消失 |
| meiモデルによる日本語TTS発話 | ✅ 合格 | 音質・声質ともに良好 |
| PTT録音 → STT認識 → LLM応答 → TTS発話の一気通貫フロー | ✅ 合格 | 全フロー正常動作を確認 |

---

## 発見・対処した不具合・改善事項

### 1. HuggingFace Hub 認証警告（STT起動時）

**現象**: 入力処理時に `Warning: unauthenticated requests to the HF Hub` が表示される。
**原因**: `WhisperModel("small", ...)` が毎回HF Hubへ接続確認リクエストを送っていた。
**対処**: `listen_voice.py` の `WhisperModel` 初期化に `local_files_only=True` を追加。ローカルキャッシュのみ使用するよう変更。
**ファイル**: `~/gakukoma/stt/listen_voice.py`

---

### 2. 録音ファイルが生成されない（致命的バグ）

**現象**: Enter押下後に録音→認識ステップで `FileNotFoundError: /tmp/gakukoma_input.wav` が発生しクラッシュ。
**原因**: `config.yaml` の `audio.device` が `plughw:2,0`（スピーカー）になっており、`arecord` がマイクではなくスピーカーデバイスに録音しようとしていた。TTS移行時にAntigravityが再生デバイスに合わせて `device` を書き換えたことが原因。
**対処**: `config.yaml` の `audio.device` を `record_device`（マイク用）と `playback_device`（スピーカー用）に分離。`voice_loop.py` と `speak_text.py` の参照キーを更新。

```yaml
# 変更前
audio:
  device: "plughw:2,0"

# 変更後
audio:
  record_device: "hw:3,0"       # USBマイク (card 3)
  playback_device: "plughw:2,0"  # MAX98357A スピーカー (card 2)
```

**ファイル**: `~/gakukoma/voice_loop/config.yaml`, `voice_loop.py`, `tts/speak_text.py`

---

### 3. LLMレスポンス速度の改善

**現象**: 入力→発話までの全体レイテンシが20秒強。目標8秒。
**原因①**: LLMモデルが `GLM-4.7`（低速）だった。
**対処①**: OpenClaw設定を変更し、LLMモデルを `claude-haiku-4-5-20251001` に切り替え。→ 約5秒短縮。

**原因②**: STT（Faster-Whisper）がサブプロセスとして毎回起動され、WhisperModelのロード（約2〜3秒）が毎回発生していた。
**対処②**: `voice_loop.py` 起動時に `WhisperModel` を1回だけロードしてメモリ常駐させ、サブプロセス呼び出しをインプロセス処理に変更。→ 呼び出しごとのオーバーヘッドを解消。

**変更ファイル**:
- `~/.openclaw/openclaw.json`（プロバイダー `anthropic-messages` 追加、デフォルトモデル変更）
- `~/.openclaw/agents/main/agent/auth-profiles.json`（Anthropic APIキー登録）
- `~/gakukoma/voice_loop/voice_loop.py`（WhisperModel常駐化）

---

### 4. 固有名詞「がくこま」のSTT未認識

**現象**: 「がくこま」と発話しても正しく認識されない。
**原因**: Faster-Whisperに固有名詞のヒントが与えられていなかった。
**対処**: `initial_prompt` パラメータに固有名詞を登録。

```python
# 変更前
model.transcribe(audio_file, beam_size=5, language="ja")

# 変更後
model.transcribe(audio_file, beam_size=5, language="ja",
                 initial_prompt="がくこま、ガクコマ、学コマ")
```

**ファイル**: `~/gakukoma/stt/listen_voice.py`（常駐化後は `voice_loop.py` 内のインライン呼び出しに統合）

---

## 最終的なデバイス・モデル構成

| コンポーネント | 設定値 |
|---|---|
| 録音デバイス | `hw:3,0`（USBマイク, card 3） |
| 再生デバイス | `plughw:2,0`（MAX98357A, card 2） |
| STTモデル | Faster-Whisper `small`（int8, CPU常駐） |
| LLMモデル | Claude Haiku 4.5（`claude-haiku-4-5-20251001`） |
| TTSエンジン | Open JTalk（meiモデル, レイテンシ約76ms） |

---

## 残課題・次フェーズへの申し送り

- LLMレスポンス速度は改善したが、目標の8秒に達しているか要継続観測。さらに短縮が必要な場合はストリーミング発話（LLM生成と並行してTTSを開始する）の実装が有効。
- Phase 2（カメラ・パン・チルト）に着手可能な状態。
