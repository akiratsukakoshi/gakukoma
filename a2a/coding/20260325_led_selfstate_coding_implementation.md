# 指示書: LEDによるself-state可視化（コーディング実装）

**作成**: ClaudeCode
**担当**: Antigravity
**フェーズ**: Phase 2.3 追加タスク
**関連ハードウェア報告書**: `hardware/20260321_led_selfstate_completed.md`

---

## 背景・目的

Geminiによるハードウェア配線が完了した（報告書確認済み）。
`voice_loop.py` の4ステートマシンに対応したLED制御を実装し、GAKUKOMAの内部状態を外部から視覚的に確認できるようにする。

---

## 確定済みハードウェア仕様（変更不可）

| 信号 | GPIO (BCM) | 物理ピン |
|---|---|---|
| 赤 (R) | GPIO 17 | Pin 11 |
| 緑 (G) | GPIO 27 | Pin 13 |
| 青 (B) | GPIO 22 | Pin 15 |
| GND (K) | GND | Pin 14 |

**重要**: `RPi.GPIO` は Raspberry Pi 5 で動作しない（RuntimeError）。
**必ず `gpiozero` ライブラリを使用すること。**

---

## LED表示仕様

| state | 色 | パターン | 周期 |
|---|---|---|---|
| `idle` | 青 | 点滅 | on=0.5秒 / off=0.5秒（1秒周期） |
| `listening` | 緑 | 常時点灯 | - |
| `thinking` | 黄（R+G同時） | 点滅 | on=0.15秒 / off=0.15秒（0.3秒周期） |
| `speaking` | 赤 | 常時点灯 | - |

---

## 実装方針

### 新規ファイル
`/home/tukapontas/gakukoma/voice_loop/led_controller.py`

### 変更ファイル
`/home/tukapontas/gakukoma/voice_loop/voice_loop.py`

---

## Task 1: `led_controller.py` の作成

`/home/tukapontas/gakukoma/voice_loop/led_controller.py` を新規作成する。

### 設計

- `gpiozero.RGBLED` を使用（コモンカソード・`active_high=True` がデフォルトなのでそのまま使う）
- `set_state(state: str)` メソッド1本のみを公開するシンプルな設計
- 点滅は `RGBLED.blink()` の `background=True` で処理（スレッド管理は gpiozero に任せる）
- 状態変更時は必ず現在の動作を止めてから新しいパターンを設定する（`led.off()` で停止）
- `close()` メソッドでGPIOリソースを解放する

### 実装例（参考）

```python
from gpiozero import RGBLED

class LedController:
    def __init__(self):
        self.led = RGBLED(red=17, green=27, blue=22)

    def set_state(self, state: str):
        self.led.off()  # 先に止める（blink中でも安全に止まる）
        if state == "idle":
            self.led.blink(on_time=0.5, off_time=0.5,
                           on_color=(0, 0, 1), off_color=(0, 0, 0),
                           background=True)
        elif state == "listening":
            self.led.color = (0, 1, 0)
        elif state == "thinking":
            self.led.blink(on_time=0.15, off_time=0.15,
                           on_color=(1, 1, 0), off_color=(0, 0, 0),
                           background=True)
        elif state == "speaking":
            self.led.color = (1, 0, 0)
        # 未知のstateは消灯のまま（off()済み）

    def close(self):
        self.led.off()
        self.led.close()
```

---

## Task 2: `voice_loop.py` への統合

以下の3点を修正する。

### 2-1. インポート追加（ファイル先頭）

```python
from led_controller import LedController
```

### 2-2. `VoiceLoop.__init__` にLED初期化を追加

`self.state = "idle"` の直後に追記：

```python
self.led = LedController()
self.led.set_state("idle")
```

### 2-3. 全ての `self.state = "xxx"` の直後に `self.led.set_state("xxx")` を追加

現在のコード上の対象箇所は以下の通り（行番号は参考）：

| 箇所 | 変更後の状態 |
|---|---|
| `self.state = "listening"` (wakeword検出後・L308) | listening |
| `self.state = "listening"` (ACTIVEループ先頭・L317) | listening |
| `self.state = "thinking"` (VAD後・L324) | thinking |
| `self.state = "idle"` (連続失敗3回・L334) | idle |
| `self.state = "listening"` (認識失敗・L336) | listening |
| `self.state = "idle"` (スリープワード・L345) | idle |
| `self.state = "speaking"` (TTS前・L349) | speaking |
| `self.state = "listening"` (TTS後・L352) | listening |

**パターン**（毎回この2行をセットで書く）：
```python
self.state = "xxx"
self.led.set_state("xxx")
```

### 2-4. `KeyboardInterrupt` 時のリソース解放

`except KeyboardInterrupt` ブロック内の `sys.exit(0)` 直前に追加：

```python
self.led.close()
```

---

## 確認テスト

### T-1: idle状態のLED確認

1. `voice_loop.py` を起動する
2. 起動直後（ウェイクワード待機中）に**青色点滅（1秒周期）**が点灯することを確認

### T-2: listening状態のLED確認

1. ウェイクワード「おはよう」を発声してACTIVEモードに遷移させる
2. 発話待機中に**緑色・常時点灯**になることを確認

### T-3: thinking状態のLED確認

1. ACTIVEモード中に発話する
2. STT処理〜API応答待ち中に**黄色点滅（0.3秒周期）**になることを確認

### T-4: speaking状態のLED確認

1. APIレスポンスが返ってきてTTS発話が始まったら
2. **赤色・常時点灯**になることを確認

### T-5: idle復帰のLED確認

1. 「おやすみ」を発声する
2. スリープワード処理後に**青色点滅**に戻ることを確認

### T-6: 状態遷移のちらつきなし確認

- T-1〜T-5の遷移中に意図しない色や消灯が挟まらないことを目視確認する

---

## 完了報告

完了後、`coding/20260325_led_selfstate_coding_completed.md` を作成すること。
報告書には以下を記載すること：

1. T-1〜T-6の確認結果（PASS/FAIL）
2. 実装上で工夫した点・変更した点（仕様と異なる実装をした場合はその理由）
3. 次の担当者への申し送り事項
