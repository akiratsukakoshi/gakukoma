# 指示書: voice_loop.py 4ステートマシン化

**作成**: ClaudeCode
**担当**: Antigravity
**対象ファイル**: `/home/tukapontas/gakukoma/voice_loop/voice_loop.py`
**フェーズ**: Phase 2.3 追加タスク

---

## 背景・課題

現在のvoice_loopには以下の問題がある。

### 問題1: sounddeviceストリームの開閉サイクル
`record_vad()` を呼ぶたびに `sd.InputStream` を開閉している。
STT転写中・OpenClaw API呼び出し中・TTS再生中はストリームが閉じているため、
その間にユーザーが話しかけても音声が失われる。

### 問題2: TTS残響によるVAD誤トリガー
TTS再生後、スピーカーの残響がマイクに入りVADが「発話あり」と誤判定する。
現在は `time.sleep(1.5)` でごまかしているが、まだ1〜2回の誤トリガーが残る。

---

## 目標

**ACTIVEモード中はいつ話しかけても受け付けられる状態にする。**
ただしTTS再生中（＋残響1.5秒）は意図的に音声を捨て、混線を防ぐ。

---

## 設計: 4ステートマシン

```
IDLE ──(ウェイクワード検出)──→ LISTENING
LISTENING ──(発話検出→録音→無音)──→ THINKING
THINKING ──(STT + API応答取得)──→ SPEAKING
SPEAKING ──(TTS完了 + フラッシュ1.5s)──→ LISTENING
LISTENING ──(おやすみ検出)──→ IDLE
```

### 各状態でのマイク動作

| 状態 | ストリーム | 動作 |
|---|---|---|
| IDLE | 開閉あり（既存のまま） | ウェイクワード検出専用 |
| LISTENING | 常時開放 | VAD有効、発話を検出・録音 |
| THINKING | 常時開放 | VAD無効、フレームを捨てる |
| SPEAKING | 常時開放 | VAD無効、フレームを捨てる |

ポイント: **ACTIVEモード（LISTENING/THINKING/SPEAKING）中は1つのストリームを維持し続ける。**

---

## 実装仕様

### 1. `self.state` 属性

`self.mode`（"idle"/"active"）を廃止し、`self.state` に統一する。

```python
self.state = "idle"  # "idle" | "listening" | "thinking" | "speaking"
```

### 2. ACTIVEモード用ストリーム管理

`run()` のACTIVEモードループに入る際に1度だけストリームを開き、IDLEに戻る際に閉じる。

```python
# IDLEに戻るときに閉じる
with sd.InputStream(device=self.device, channels=1,
                    samplerate=self.sample_rate, dtype='int16') as active_stream:
    while self.state != "idle":
        frames = self.record_vad_from_stream(active_stream)
        ...
```

### 3. `record_vad_from_stream(stream)` メソッド（新規）

既存の `record_vad()` を置き換える。引数として開いているストリームを受け取る。
内部ロジックはVADステートマシンのみ（ストリームの開閉は行わない）。

```python
def record_vad_from_stream(self, stream):
    """開いているストリームからVADで発話を録音する"""
    # 既存 record_vad() の内部ロジックをそのまま移植
    # ただし `with sd.InputStream(...) as stream:` のブロックを除去し、
    # 引数の stream を使う
    ...
    return frames  # 発話なし or 短すぎる場合は None
```

### 4. `flush_stream(stream, duration_sec)` メソッド（新規）

TTS再生後にバッファに溜まったエコーを捨てるためのフラッシュ処理。

```python
def flush_stream(self, stream, duration_sec):
    """ストリームのバッファをduration_sec秒分読み捨てる"""
    frames_to_discard = int(duration_sec * 1000 / self.frame_duration_ms)
    for _ in range(frames_to_discard):
        stream.read(self.frame_size)
```

### 5. `speak()` 関数の変更

`time.sleep(0.5)` および `time.sleep(1.5)` をすべて削除する。
フラッシュは `run()` 側で `flush_stream()` を呼ぶことで行う。

```python
def speak(text, tts_engine):
    ...
    for s in combined:
        if s.strip():
            print(f"GAKUKOMA: {s.strip()}")
            tts_engine.speak(s.strip())
    # sleep不要。呼び出し側でflush_streamを行う
```

### 6. `run()` のACTIVEループ全体像

```python
def run(self):
    speak("がくこまが起動しました。", self.tts_engine)

    while True:
        if self.state == "idle":
            print("\n[IDLE] ウェイクワード待機中...")
            frames = self.record_wakeword_candidate()
            if frames:
                self.save_wav(frames, self.audio_file)
                text = self.transcribe(self.audio_file, model_type="tiny")
                print(f"WAKEVOICE: {text}")
                if self.is_wakeword(text):
                    speak("はい、なんでしょう", self.tts_engine)
                    self.session_id = None
                    self.state = "listening"
                    self._consecutive_failures = 0

        elif self.state in ("listening", "thinking", "speaking"):
            # ACTIVEモード: ストリームを1度だけ開く
            with sd.InputStream(device=self.device, channels=1,
                                samplerate=self.sample_rate, dtype='int16') as active_stream:
                while self.state != "idle":
                    print("\n[LISTENING] 発話待機中...")
                    self.state = "listening"
                    frames = self.record_vad_from_stream(active_stream)

                    if not frames:
                        continue

                    self.save_wav(frames, self.audio_file)
                    self.state = "thinking"
                    print("[THINKING] 認識中...")
                    text = self.transcribe(self.audio_file, model_type="small")

                    if not text:
                        print("（認識不能な音声）")
                        self._consecutive_failures = getattr(self, '_consecutive_failures', 0) + 1
                        if self._consecutive_failures >= 3:
                            print("連続認識失敗3回 → IDLEに戻ります")
                            self._consecutive_failures = 0
                            self.state = "idle"
                        else:
                            self.state = "listening"
                        continue

                    self._consecutive_failures = 0
                    print(f"YOU: {text}")

                    if self.is_sleepword(text):
                        speak("おやすみなさい", self.tts_engine)
                        self.flush_stream(active_stream, 1.5)
                        self.state = "idle"
                        continue

                    response = self.call_openclaw(text)
                    self.state = "speaking"
                    speak(response, self.tts_engine)
                    self.flush_stream(active_stream, 1.5)  # TTS残響を捨てる
                    self.state = "listening"
```

---

## 変更対象の整理

| メソッド/関数 | 変更内容 |
|---|---|
| `record_vad()` | `record_vad_from_stream(stream)` に置き換え（旧メソッドは削除） |
| `flush_stream()` | 新規追加 |
| `speak()` | `time.sleep` を削除 |
| `run()` のACTIVEループ | ストリームを外で開き、内部でステートを管理 |
| `self.mode` | `self.state` に置き換え（"idle"/"active" → "idle"/"listening"/"thinking"/"speaking"） |

---

## テスト項目

| ID | 内容 | 期待結果 |
|---|---|---|
| T-1 | ガクコマと呼ぶ → 即座に返答 | `はい、なんでしょう` |
| T-2 | 返答中に話しかける | TTS中は無視、終了後に受け付ける |
| T-3 | 返答終了直後（0.5秒後）に話しかける | フラッシュ中のため無視される |
| T-4 | 返答終了1.5秒後に話しかける | 正常に認識・応答する |
| T-5 | 認識不能音声を3回続ける | IDLEに戻る |
| T-6 | おやすみ → IDLEに戻る | `おやすみなさい` → IDLE |
| T-7 | THINKING中（API呼び出し中）に話しかける | 無視される（ロスト許容） |

T-7は「ロスト許容」とする。THINKINGとSPEAKINGはユーザーが発話できない状態のため、UX上は問題なし。

---

## 将来の拡張アイデア（実装不要・記録のみ）

**LEDによる状態可視化**（Phase 3以降を想定）

`self.state` が既に4状態に分かれているため、各状態変更時にGPIO制御を追加するだけで実現できる。

| state | LED色（案） | GPIO |
|---|---|---|
| idle | 青（低輝度点滅） | 未定 |
| listening | 緑（常時点灯） | 未定 |
| thinking | 黄（点滅） | 未定 |
| speaking | 赤（常時点灯） | 未定 |

実装時は `voice_loop.py` の状態遷移箇所（`self.state = "xxx"` の直後）に `self.led_set_state(state)` を呼ぶ設計が最もクリーン。`led_set_state()` は初期はpass、ハードウェア接続後に実装する。

---

## 完了報告

完了後、`coding/20260321_voiceloop_4state_completed.md` を作成すること。
