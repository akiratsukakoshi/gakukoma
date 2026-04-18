# Phase 3 Task G：`move_robot()` ツール実装（改訂版）

**作成日:** 2026-04-16
**作成者:** ClaudeCode（司令塔）
**担当:** コーディング担当AI
**前提条件:** Task F（統合ハードウェア検証）完了 ✅
**旧指示書:** `coding/20260402_phase3_move_robot_implementation.md`（中止・本指示書に置き換え）

---

## 目的

TB6612FNG モータードライバを gpiozero で制御するスクリプトを実装し、`move_robot` ツールとして `gakukoma_brain.py` に統合する。がくこまが「前に進んで」「右に曲がって」などの走行コマンドに反応できるようになる。

---

## 現在のアーキテクチャ（必ず把握すること）

```
voice_loop.py
  └─ GAKUKOMABrain.invoke()
       └─ Anthropic API（直接呼び出し）
            ├─ TOOLS 配列でツール定義
            └─ _execute_tool() でシェルスクリプト実行
                 └─ /home/tukapontas/gakukoma/tools/*.sh
```

OpenClaw は廃止済み。TOOLS.md・SOUL.md への追記は不要。
ツール追加は **`gakukoma_brain.py`** の2箇所のみ行う。

---

## GPIO ピンアサイン（確定版・変更不可）

| TB6612FNG端子 | GPIO番号 | 備考 |
|---|---|---|
| PWMA | 12 | ハードウェアPWM0（左モーター速度） |
| AIN1 | 20 | 左モーター方向1 |
| **AIN2** | **26** | **左モーター方向2 ※GPIO21から変更済み** |
| PWMB | 13 | ハードウェアPWM1（右モーター速度） |
| BIN1 | 24 | 右モーター方向1 |
| BIN2 | 25 | 右モーター方向2 |
| STBY | 16 | HIGHで動作有効 |

---

## ハードウェア検証で判明した重要事項（Task F申し送り）

1. **右モーター（BIN）の配線極性反転**: 「前進命令=後退回転」のため、`set_motor_b()` の speed 符号を左と逆にすること。
   → `config.yaml` に `motor_b_invert: true` フラグを設けて対応する。

2. **左モーターの最小PWM**: 履帯の張りが強く、PWM 0.3 では脱調音（ピー音）が発生する。
   → `default_speed` を 60%（0.6）以上に設定すること。

---

## 実装対象ファイル

### 新規作成

```
~/gakukoma/
  motor/
    __init__.py          # 空ファイル
    tb6612_ctrl.py       # TB6612FNG制御クラス
    motor_driver.py      # 走行コマンド定義
    move_robot_cmd.py    # move_robot.sh から呼ばれるCLIエントリーポイント
  tools/
    move_robot.sh        # gakukoma_brain.py が呼ぶラッパー
```

### 変更

```
~/gakukoma/
  brain/
    gakukoma_brain.py    # TOOLS配列 + _execute_tool() dispatch に追記
  voice_loop/
    config.yaml          # motor セクション追記
```

---

## config.yaml 追記内容

`/home/tukapontas/gakukoma/voice_loop/config.yaml` に以下を追記する:

```yaml
motor:
  pwm_a: 12
  ain1: 20
  ain2: 26                  # GPIO21から変更済み
  pwm_b: 13
  bin1: 24
  bin2: 25
  stby: 16
  pwm_frequency: 1000       # Hz
  default_speed: 60         # % (0〜100) ※履帯の張りを考慮して60以上
  turn_speed: 50            # % 旋回時
  motor_b_invert: true      # 右モーター配線極性反転対応
```

---

## tb6612_ctrl.py の実装仕様

```python
"""
TB6612FNG 制御クラス
- gpiozero を使用（RPi.GPIO は Pi5 非対応・RuntimeError が発生するため使用禁止）
- __del__ を実装しないこと（スクリプト終了時の予期せぬ停止を防ぐ）
- 終了処理は cleanup() を明示的に呼ぶ設計にすること
"""

from gpiozero import OutputDevice, PWMOutputDevice
import yaml, os

class TB6612FNG:
    def __init__(self, config_path=None):
        """
        config_path が None の場合は
        /home/tukapontas/gakukoma/voice_loop/config.yaml を読む。
        motor セクションを読み込んで各ピン番号・設定を初期化。
        STBY を HIGH にしてドライバを有効化。
        motor_b_invert フラグを読み込んで self.motor_b_invert に保持。
        """
        pass

    def set_motor_a(self, speed: float):
        """
        左モーター制御。speed: -100(後退)〜0(停止)〜100(前進)
        speed > 0: AIN1=H / AIN2=L / PWMA=speed/100
        speed < 0: AIN1=L / AIN2=H / PWMA=abs(speed)/100
        speed == 0: AIN1=L / AIN2=L / PWMA=0（コースト停止）
        """
        pass

    def set_motor_b(self, speed: float):
        """
        右モーター制御。speed: -100(後退)〜0(停止)〜100(前進)
        motor_b_invert=True の場合は speed の符号を反転してから set_motor_a と同様の制御を行う。
        """
        pass

    def stop(self):
        """両モーターをコースト停止（set_motor_a(0), set_motor_b(0)）"""
        pass

    def brake(self):
        """両モーターをブレーキ停止（AIN1=H/AIN2=H, BIN1=H/BIN2=H）"""
        pass

    def cleanup(self):
        """STBY を LOW にしてドライバをスタンバイ状態にする"""
        pass
```

---

## motor_driver.py の実装仕様

```python
"""
走行コマンド定義。TB6612FNG クラスを使って高レベルな走行操作を提供する。
time.sleep(duration) で走行時間を制御し、終了後は stop() する。
"""

import time
from motor.tb6612_ctrl import TB6612FNG

class MotorDriver:
    def __init__(self):
        self.motor = TB6612FNG()
        # config から default_speed / turn_speed を読んで保持

    def forward(self, speed: int = None, duration: float = 1.0):
        """前進: 両モーター同速前進 → duration 秒後に停止"""
        pass

    def backward(self, speed: int = None, duration: float = 1.0):
        """後退: 両モーター同速後退 → duration 秒後に停止"""
        pass

    def turn_left(self, speed: int = None, duration: float = 0.5):
        """左旋回: 右モーター前進・左モーター停止"""
        pass

    def turn_right(self, speed: int = None, duration: float = 0.5):
        """右旋回: 左モーター前進・右モーター停止"""
        pass

    def spin_left(self, speed: int = None, duration: float = 0.5):
        """左スピン（超信地旋回）: 左後退・右前進"""
        pass

    def spin_right(self, speed: int = None, duration: float = 0.5):
        """右スピン（超信地旋回）: 左前進・右後退"""
        pass

    def stop(self):
        self.motor.stop()

    def cleanup(self):
        self.motor.cleanup()
```

---

## move_robot_cmd.py の実装仕様

```python
"""
move_robot.sh から呼ばれるCLIエントリーポイント。
引数: direction [duration] [speed]
出力: 実行結果を標準出力（gakukoma_brain.py が tool_result として受け取る）
"""

import sys
from motor.motor_driver import MotorDriver

VALID_DIRECTIONS = {
    "forward": "前進",
    "backward": "後退",
    "left": "左旋回",
    "right": "右旋回",
    "spin_left": "左スピン",
    "spin_right": "右スピン",
    "stop": "停止",
}

def main():
    direction = sys.argv[1] if len(sys.argv) > 1 else "stop"
    duration  = float(sys.argv[2]) if len(sys.argv) > 2 else 1.0
    speed     = int(sys.argv[3]) if len(sys.argv) > 3 else None  # None → MotorDriver デフォルト使用

    if direction not in VALID_DIRECTIONS:
        print(f"不明な方向: {direction}")
        sys.exit(1)

    driver = MotorDriver()
    try:
        method = getattr(driver, direction if direction != "left" else "turn_left", None)
        # direction → MotorDriver メソッドのマッピング
        # forward / backward / turn_left / turn_right / spin_left / spin_right / stop
        kwargs = {}
        if direction != "stop":
            kwargs["duration"] = duration
            if speed is not None:
                kwargs["speed"] = speed
        # 対応するメソッドを呼び出す
        print(f"{VALID_DIRECTIONS[direction]} 完了（{duration}秒・速度{speed if speed else 'デフォルト'}%）")
    finally:
        driver.cleanup()

if __name__ == "__main__":
    main()
```

> ※ direction → MotorDriver メソッドのマッピングを明示した実装にすること（上記は概要）。

---

## move_robot.sh

`/home/tukapontas/gakukoma/tools/move_robot.sh`:

```bash
#!/bin/bash
# 使用例: move_robot.sh forward 1.0 60
# 引数: direction [duration] [speed]
cd /home/tukapontas/gakukoma
python3 -m motor.move_robot_cmd "$@"
```

`chmod +x tools/move_robot.sh` で実行権限を付与すること。
`cd /home/tukapontas/gakukoma` を行うのは `motor` パッケージの相対インポートを解決するため。

---

## gakukoma_brain.py への追記

### 1. TOOLS 配列に追記

`TOOLS = [` リストの末尾（`set_pan_tilt` の次）に以下を追加する:

```python
    {
        "name": "move_robot",
        "description": "ロボットを走行させる。前進・後退・左右旋回・スピン・停止が可能。",
        "input_schema": {
            "type": "object",
            "properties": {
                "direction": {
                    "type": "string",
                    "enum": ["forward", "backward", "left", "right", "spin_left", "spin_right", "stop"],
                    "description": "走行方向。forward=前進, backward=後退, left=左旋回, right=右旋回, spin_left=左スピン, spin_right=右スピン, stop=停止"
                },
                "duration": {
                    "type": "number",
                    "description": "走行秒数（デフォルト: 1.0）"
                },
                "speed": {
                    "type": "integer",
                    "description": "速度 0〜100%（省略時はデフォルト速度60%）"
                }
            },
            "required": ["direction"]
        }
    },
```

### 2. _execute_tool() の dispatch 辞書に追記

`dispatch = {` の中に以下を追加する:

```python
            "move_robot": [
                str(tools_dir / "move_robot.sh"),
                inp.get("direction", "stop"),
                str(inp.get("duration", 1.0)),
                str(inp.get("speed", "")),
            ],
```

> ※ speed が省略された場合は空文字列 `""` を渡し、move_robot_cmd.py 側で `sys.argv[3]` が空か判定してデフォルト使用とすること（または speed が空文字のとき引数を渡さない形でも可）。

---

## pigpiod の設定（ハードウェアPWM使用）

gpiozero でハードウェアPWMを使用するには pigpio ファクトリが必要。

```bash
# pigpiod インストール確認
sudo apt-get install pigpio

# 自動起動設定
sudo systemctl enable pigpiod
sudo systemctl start pigpiod
```

`tb6612_ctrl.py` の先頭で以下を設定すること:

```python
import gpiozero
from gpiozero.pins.pigpio import PiGPIOFactory
gpiozero.Device.pin_factory = PiGPIOFactory()
```

---

## テスト仕様

以下を順に確認すること（Task H の統合テストで Gemini と合同実施予定）:

| # | テスト | コマンド | 合格条件 |
|---|---|---|---|
| T-1 | 前進 | `tools/move_robot.sh forward 1.0` | 1秒間前進して停止 |
| T-2 | 後退 | `tools/move_robot.sh backward 1.0` | 1秒間後退して停止 |
| T-3 | 左旋回 | `tools/move_robot.sh left 0.5` | 左に旋回 |
| T-4 | 右旋回 | `tools/move_robot.sh right 0.5` | 右に旋回 |
| T-5 | 停止 | `tools/move_robot.sh stop` | 即時停止 |
| T-6 | Brain統合 | 「前に進んで」と発話 | move_robot が呼ばれ走行 |
| T-7 | 走行+首振り同時 | 「右に進みながら右を向いて」と発話 | 走行中に look_direction が正常動作 |

---

## 注意事項

- **gpiozero を使用すること**（RPi.GPIO は Pi5 非対応）
- **`__del__` を実装しないこと**（スクリプト終了時の予期せぬモーター停止防止）
- **`finally` ブロックで `cleanup()` を必ず実行すること**（走りっぱなし防止）
- **pigpiod が起動していないとハードウェアPWMが動作しない**。systemctl enable で自動起動させること

---

## 完了報告書の作成

完了後、`coding/20260416_phase3_move_robot_completed.md` を作成し、以下を記録すること:

- 実装したファイル一覧とパス
- config.yaml に追記した内容
- gakukoma_brain.py の変更内容（TOOLS追記・dispatch追記）
- T-1〜T-7 のテスト結果
- motor_b_invert の動作確認結果
- pigpiod の設定状況
- 特記事項
