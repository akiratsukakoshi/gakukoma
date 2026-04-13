# Antigravity 指示書: パンチルト ジェスチャー機能実装

**作成日**: 2026-04-10
**担当**: Antigravity
**フェーズ**: Phase 2.3 追加要件

---

## 概要

ガクコマのパンチルト台座（DS3218サーボ）に3種類のジェスチャーを追加する。

1. **スリープ時センタリング**: 「おやすみ」検出時に首をニュートラルポジション（正面90°/90°）へ自動復帰
2. **シンキングジェスチャー**: `thinking` 状態中にゆっくりランダム風に首を動かす（考えているしぐさ）
3. **スピーキングジェスチャー**: `speaking` 状態中に上下の大きな動きで発話感を表現し、発話後に元の位置へ戻す

---

## ファイル構成

```
/home/tukapontas/gakukoma/
  servo/
    pan_tilt.py          ← 既存（変更なし）
    gesture_controller.py ← 新規作成
  voice_loop/
    voice_loop.py        ← 3箇所修正
```

---

## 実装詳細

### 1. `servo/gesture_controller.py`（新規作成）

```python
import time
import threading

class GestureController:
    """
    パンチルト台座のジェスチャーを管理するクラス。
    PanTiltController を受け取り、バックグラウンドスレッドで動作する。

    重要制約:
    - pan_tilt.release() を呼び出してはならない（脱力する）
    - set_pan_tilt / set_pan / set_tilt は PanTiltController のロックを内部で獲得する
    """

    # シンキングジェスチャーのパターン（pan, tilt のシーケンス）
    # center=90,90 から緩やかに外れてまた戻る動き
    _THINKING_PATTERN = [
        (87, 87),
        (93, 85),
        (90, 92),
        (85, 88),
        (95, 90),
        (88, 86),
        (91, 93),
        (90, 90),
    ]

    # スピーキングジェスチャーのパターン（頷き）
    # 上下に大きく動き、最後に中央へ戻る
    _SPEAKING_PATTERN = [
        (90, 80),   # 上を向く（大きく）
        (90, 90),   # 中央
        (90, 100),  # 下を向く
        (90, 90),   # 中央
        (90, 78),   # 上（やや大きく）
        (90, 90),   # 中央
    ]

    def __init__(self, pan_tilt_controller):
        """
        Args:
            pan_tilt_controller: servo.pan_tilt.PanTiltController のインスタンス
        """
        self._pt = pan_tilt_controller
        self._stop_event = threading.Event()
        self._thread = None

    def _run_thinking(self, stop_event):
        """シンキングジェスチャーのバックグラウンドスレッド"""
        idx = 0
        while not stop_event.is_set():
            pan, tilt = self._THINKING_PATTERN[idx % len(self._THINKING_PATTERN)]
            self._pt.set_pan_tilt(pan, tilt)
            idx += 1
            # 0.5秒ごとにstop_eventを確認しながら待機（interrupt可能）
            for _ in range(5):
                if stop_event.is_set():
                    break
                time.sleep(0.1)

    def _run_speaking(self, stop_event):
        """スピーキングジェスチャーのバックグラウンドスレッド"""
        idx = 0
        while not stop_event.is_set():
            pan, tilt = self._SPEAKING_PATTERN[idx % len(self._SPEAKING_PATTERN)]
            self._pt.set_pan_tilt(pan, tilt)
            idx += 1
            # 0.3秒ごとにstop_eventを確認（thinking より速い動き）
            for _ in range(3):
                if stop_event.is_set():
                    break
                time.sleep(0.1)

    def start_thinking(self):
        """シンキングジェスチャー開始。既存ジェスチャーは停止してから開始する。"""
        self.stop()
        self._stop_event = threading.Event()
        self._thread = threading.Thread(
            target=self._run_thinking,
            args=(self._stop_event,),
            daemon=True,
            name="gesture-thinking"
        )
        self._thread.start()

    def start_speaking(self):
        """スピーキングジェスチャー開始。既存ジェスチャーは停止してから開始する。"""
        self.stop()
        self._stop_event = threading.Event()
        self._thread = threading.Thread(
            target=self._run_speaking,
            args=(self._stop_event,),
            daemon=True,
            name="gesture-speaking"
        )
        self._thread.start()

    def stop(self):
        """現在のジェスチャーを停止してスレッドが終了するのを待つ。"""
        if self._thread and self._thread.is_alive():
            self._stop_event.set()
            self._thread.join(timeout=1.0)
        self._thread = None

    def go_center(self):
        """ジェスチャーを停止し、首をニュートラルポジション（正面）へ戻す。"""
        self.stop()
        self._pt.look_center()
```

---

### 2. `voice_loop/voice_loop.py` の修正

#### 修正箇所 A: インポートと初期化（`__init__` 内）

`VoiceLoop.__init__` に以下を追加する。

```python
# 既存インポート群の末尾に追加
from servo.pan_tilt import PanTiltController
from servo.gesture_controller import GestureController
```

`VoiceLoop.__init__` の末尾（`self.is_first_turn = True` の後あたり）に追加:

```python
# ジェスチャーコントローラー初期化
try:
    self._pan_tilt = PanTiltController()
    self._gesture = GestureController(self._pan_tilt)
except Exception as e:
    print(f"Warning: ジェスチャーコントローラー初期化失敗 ({e}). ジェスチャー機能は無効。")
    self._pan_tilt = None
    self._gesture = None
```

---

#### 修正箇所 B: スリープワード処理（`run()` 内）

現在のコード（約350-355行）:
```python
if self.is_sleepword(text):
    speak("おやすみなさい", self.tts_engine)
    self.flush_stream(active_stream, 1.5)
    self.state = "idle"
    self.led.set_state("idle")
    continue
```

修正後:
```python
if self.is_sleepword(text):
    speak("おやすみなさい", self.tts_engine)
    self.flush_stream(active_stream, 1.5)
    self.state = "idle"
    self.led.set_state("idle")
    # 首をニュートラルポジション（正面）へ戻す
    if self._gesture:
        self._gesture.go_center()
    continue
```

---

#### 修正箇所 C: シンキング状態の開始

現在のコード（`self.state = "thinking"` の直後あたり）:
```python
self.state = "thinking"
self.led.set_state("thinking")
print("[THINKING] 認識中...")
text = self.transcribe(self.audio_file, model_type="small")
```

修正後:
```python
self.state = "thinking"
self.led.set_state("thinking")
if self._gesture:
    self._gesture.start_thinking()
print("[THINKING] 認識中...")
text = self.transcribe(self.audio_file, model_type="small")
```

---

#### 修正箇所 D: スピーキング状態の処理

現在のコード（`response = self.call_openclaw(text)` 以降）:
```python
response = self.call_openclaw(text)
self.state = "speaking"
self.led.set_state("speaking")
speak(response, self.tts_engine)
self.flush_stream(active_stream, 1.5)  # TTS残響を捨てる
self.state = "listening"
self.led.set_state("listening")
```

修正後:
```python
response = self.call_openclaw(text)
self.state = "speaking"
self.led.set_state("speaking")
# スピーキングジェスチャー開始（speak() は同期なのでバックグラウンドで実行）
if self._gesture:
    self._gesture.start_speaking()
speak(response, self.tts_engine)
# 発話終了後: ジェスチャー停止 → 正面に戻る
if self._gesture:
    self._gesture.go_center()
self.flush_stream(active_stream, 1.5)  # TTS残響を捨てる
self.state = "listening"
self.led.set_state("listening")
```

---

## 恒久注意事項（再掲・厳守）

- `PanTiltController.release()` を `GestureController` 内から呼び出してはならない（サーボが脱力する）
- `PanTiltController.__del__` を追加してはならない（スクリプト終了時に `deinit()` が走りI2Cバスが切断される）
- ジェスチャースレッドは必ず `daemon=True` にすること（KeyboardInterrupt時にブロックしないため）

---

## テスト計画

| テストID | 内容 | 期待結果 |
|---|---|---|
| T-1 | 「おやすみ」発話後の首の動き | TTS発話後、首が正面（90°/90°）に戻る |
| T-2 | 発話認識後〜LLM応答返却中の首の動き | thinking状態中、首がゆっくりパターン通りに動く |
| T-3 | LLM応答発話中の首の動き | speaking状態中、首が上下に動く |
| T-4 | 発話終了後の首の位置 | 発話終了後、首が正面（90°/90°）に戻る |
| T-5 | PCA9685 I2C接続なし時の起動 | WarningログのみでVoiceLoopが正常起動する（ジェスチャー無効でフォールバック） |
| T-6 | 連続会話（3ターン以上） | 各ターンでジェスチャーが正しく切り替わり、スレッドリークがない |

---

## 完了報告

完了後、`coding/20260410_pantilt_gesture_completed.md` を作成して報告すること。
