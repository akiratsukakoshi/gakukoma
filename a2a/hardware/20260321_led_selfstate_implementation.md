# 指示書: LEDによるself-state可視化（ハードウェア配線）

**作成**: ClaudeCode
**担当**: Gemini
**フェーズ**: Phase 2.3 追加タスク
**関連コード**: `/home/tukapontas/gakukoma/voice_loop/voice_loop.py`

---

## 背景・目的

`voice_loop.py` の4ステートマシン化が完了し、GAKUKOMAの内部状態が以下の4つに明確に管理されるようになった。

| state | 意味 |
|---|---|
| `idle` | ウェイクワード待機中 |
| `listening` | 発話を聞いている |
| `thinking` | STT処理・API応答待ち |
| `speaking` | TTS発話中 |

この状態をRGB LEDで可視化することで、GAKUKOMAが「今何をしているか」を外部から一目で把握できるようにする。

---

## 完成形イメージ

| state | LED表示 | 意味 |
|---|---|---|
| `idle` | 青・低輝度でゆっくり点滅（1秒周期） | 眠っている・待機中 |
| `listening` | 緑・常時点灯 | 聞いている |
| `thinking` | 黄（赤+緑同時点灯）・速く点滅（0.3秒周期） | 考えている |
| `speaking` | 赤・常時点灯 | 話している |

---

## 必要備品

### 新規購入が必要なもの

| 品名 | 仕様・検索キーワード | 数量 | 備考 |
|---|---|---|---|
| フルカラーLED | 5mm RGB LED コモンカソード（4本足） | 2個（予備含む） | 1個で青・緑・赤・黄の4色を表現できる |
| カーボン抵抗 | 抵抗器セット 100Ω〜330Ω （1/4W） | 各5本程度 | 手持ちになければ購入。詳細は下記参照 |

> **注意**: ジャンパーワイヤ（オス-メス）はすでに手配済みのため追加購入不要。

### 抵抗の選定（詳細）

Pi5のGPIO出力電圧は3.3V、目標電流は10mA（輝度控えめ・GPIO保護重視）。

| LED端子 | 順電圧 (Vf) | 必要抵抗値 | 使用推奨値 |
|---|---|---|---|
| 赤 (R) | 約2.0V | (3.3-2.0)/0.01 = 130Ω | **150Ω** |
| 緑 (G) | 約2.2V | (3.3-2.2)/0.01 = 110Ω | **150Ω** |
| 青 (B) | 約3.0V | (3.3-3.0)/0.01 = 30Ω | **47Ω**（最低33Ω） |

> **実用上の簡略化**: 全色に **150Ω** を使えば安全側で動作する（青は若干暗くなるが許容範囲）。手持ちに150Ωがあれば3本統一でも可。

---

## GPIO割り当て

| 信号 | GPIOピン（BCM番号） | 物理ピン番号 |
|---|---|---|
| R（赤） | GPIO 17 | Pin 11 |
| G（緑） | GPIO 27 | Pin 13 |
| B（青） | GPIO 22 | Pin 15 |
| GND（コモンカソード） | GND | Pin 14（または任意のGNDピン） |

> **選定理由**: PCA9685がI2C（GPIO2/3）を占有しているが、GPIO17/27/22はI2Cと干渉しない。ソフトウェアPWM点滅はvoice_loop.py内のスレッドで実装するため、専用PWMピンは不要。

---

## 配線手順

### 1. LED足の確認

5mm RGB LED（コモンカソード・4本足）の足の識別：

```
[正面から見て左から]
足1: R（赤）
足2: K（コモンカソード = GND） ← 最長の足
足3: G（緑）
足4: B（青）
```

> メーカーにより順序が異なる場合がある。データシートまたはテスターで確認すること。

### 2. 各足への抵抗接続

各信号足（R/G/B）とジャンパーワイヤの間に抵抗を直列に挿入する。
抵抗はブレッドボード上またはジャンパーワイヤに直接はんだ付けして保護チューブを被せるどちらでも可。

### 3. Pi5への接続

| LED足 | 接続先 |
|---|---|
| R足 → 150Ω抵抗経由 | Pi5 Pin 11（GPIO17） |
| G足 → 150Ω抵抗経由 | Pi5 Pin 13（GPIO27） |
| B足 → 150Ω抵抗経由 | Pi5 Pin 15（GPIO22） |
| K足（GND） | Pi5 Pin 14（GND） |

---

## 動作確認

配線後、以下のPythonスクリプトで各色の点灯を確認する。

```python
#!/usr/bin/env python3
"""LED動作確認スクリプト: 各色1秒ずつ点灯"""
import RPi.GPIO as GPIO
import time

R_PIN = 17
G_PIN = 27
B_PIN = 22

GPIO.setmode(GPIO.BCM)
GPIO.setup([R_PIN, G_PIN, B_PIN], GPIO.OUT, initial=GPIO.LOW)

tests = [
    ("赤 (speaking)", [R_PIN]),
    ("緑 (listening)", [G_PIN]),
    ("青 (idle)", [B_PIN]),
    ("黄 (thinking = R+G)", [R_PIN, G_PIN]),
    ("消灯", []),
]

try:
    for label, pins in tests:
        GPIO.output([R_PIN, G_PIN, B_PIN], GPIO.LOW)
        if pins:
            GPIO.output(pins, GPIO.HIGH)
        print(f"  → {label}")
        time.sleep(1.5)
finally:
    GPIO.output([R_PIN, G_PIN, B_PIN], GPIO.LOW)
    GPIO.cleanup()
    print("完了")
```

実行方法：
```bash
python3 /tmp/led_test.py
```

---

## 確認項目

| ID | 内容 | 期待結果 |
|---|---|---|
| H-1 | 赤色点灯 | R足に電圧→明確な赤色 |
| H-2 | 緑色点灯 | G足に電圧→明確な緑色 |
| H-3 | 青色点灯 | B足に電圧→明確な青色（若干暗くても可） |
| H-4 | 黄色点灯 | R+G同時→黄〜橙色に見える |
| H-5 | 消灯 | 全足LOW→完全消灯 |
| H-6 | GPIO番号の確認 | `gpio readall` または `pinout` コマンドで配線ミスがないことを確認 |

---

## ソフトウェア実装について（Antigravity向け後続作業）

本指示書はハードウェア配線のみを対象とする。
配線完了後、以下の内容でAntigravityへコーディング指示書を別途作成する予定：

- `voice_loop.py` への `led_set_state(state)` メソッド追加
- 各 `self.state = "xxx"` 直後にLED制御を挿入
- 点滅（idle: 1秒周期 / thinking: 0.3秒周期）はバックグラウンドスレッドで実装

---

## 完了報告

完了後、`hardware/20260321_led_selfstate_completed.md` を作成すること。
報告書には以下を記載すること：

1. 使用したLEDの仕様（購入先・型番・コモンカソード/アノードの別）
2. 使用した抵抗値（R/G/B各足）
3. H-1〜H-6の確認結果（PASS/FAIL）
4. 実際に使用したGPIOピン番号（変更があれば明記）
5. 気になった点・申し送り事項
