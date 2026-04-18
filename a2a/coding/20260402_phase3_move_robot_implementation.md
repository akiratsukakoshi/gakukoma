# Phase 3 Task G：`move_robot()` ツール実装

> **⛔ この指示書は中止です。**
> GAKUKOMA Brain 移行（2026-04-14）によりアーキテクチャが変わったため、OpenClaw前提の本指示書は無効。
> **新指示書: `coding/20260416_phase3_move_robot_implementation.md` を使用すること。**

**作成日:** 2026-04-02
**作成者:** ClaudeCode（司令塔）
**担当:** Antigravity
**前提条件:** Task F（統合ハードウェア検証）完了後

---

## 目的

TB6612FNG モータードライバを gpiozero で制御するスクリプトを実装し、`move_robot()` ツールとして OpenClaw に統合する。がくこまが「前に進んで」「右に曲がって」などの走行コマンドに反応できるようになる。

---

## GPIO ピンアサイン（固定・変更不可）

| TB6612FNG端子 | GPIO番号 | 備考 |
|---|---|---|
| PWMA | 12 | ハードウェアPWM0（左モーター速度） |
| AIN1 | 20 | 左モーター方向1 |
| AIN2 | 21 | 左モーター方向2 |
| PWMB | 13 | ハードウェアPWM1（右モーター速度） |
| BIN1 | 24 | 右モーター方向1 |
| BIN2 | 25 | 右モーター方向2 |
| STBY | 16 | HIGHで動作有効 |

---

## ディレクトリ構成

```
~/gakukoma/
  motor/
    __init__.py         # 空ファイルでよい
    tb6612_ctrl.py      # TB6612FNG制御クラス
    motor_driver.py     # 走行コマンド定義
  tools/
    move_robot.sh       # OpenClaw用ラッパー（既存スクリプトと同様の形式）
```

---

## config.yaml 追記内容

`/home/tukapontas/gakukoma/voice_loop/config.yaml` に以下を追記する:

```yaml
motor:
  pwm_a: 12          # GPIO12 / ハードウェアPWM0（左モーター）
  ain1: 20
  ain2: 21
  pwm_b: 13          # GPIO13 / ハードウェアPWM1（右モーター）
  bin1: 24
  bin2: 25
  stby: 16
  pwm_frequency: 1000    # PWM周波数 (Hz)
  default_speed: 50      # デフォルト速度 (0〜100%)
  turn_speed: 40         # 旋回時速度 (0〜100%)
```

---

## tb6612_ctrl.py の実装仕様

```python
"""
TB6612FNG 制御クラス
- gpiozero を使用（RPi.GPIO は Pi5 非対応のため使用禁止）
- __del__ を実装しないこと（スクリプト終了時にモーターが予期せず停止する）
- 終了処理は stop() + cleanup() を明示的に呼ぶ設計にすること
"""

from gpiozero import OutputDevice, PWMOutputDevice
import yaml, os

class TB6612FNG:
    def __init__(self, config_path=None):
        # config.yaml から設定を読み込む
        # self.pwm_a, self.ain1, ... を設定
        # STBY を HIGH に設定してドライバを有効化
        pass

    def set_motor_a(self, speed):
        """左モーター制御。speed: -100(後退)〜0(停止)〜100(前進)"""
        # speed > 0: AIN1=H / AIN2=L / PWMA=speed/100
        # speed < 0: AIN1=L / AIN2=H / PWMA=abs(speed)/100
        # speed == 0: AIN1=L / AIN2=L（コースト停止）
        pass

    def set_motor_b(self, speed):
        """右モーター制御。speed: -100(後退)〜0(停止)〜100(前進)"""
        pass

    def stop(self):
        """両モーターを停止（コースト）"""
        # AIN1=L / AIN2=L / PWMA=0
        # BIN1=L / BIN2=L / PWMB=0
        pass

    def brake(self):
        """両モーターをブレーキ停止（急停車）"""
        # AIN1=H / AIN2=H
        # BIN1=H / BIN2=H
        pass

    def cleanup(self):
        """STBY を LOW にしてドライバをスタンバイ状態にする"""
        pass
```

---

## motor_driver.py の実装仕様

```python
"""
走行コマンド定義
TB6612FNG クラスを使って高レベルの走行操作を提供する
"""

import time
from motor.tb6612_ctrl import TB6612FNG

class MotorDriver:
    def __init__(self):
        self.motor = TB6612FNG()

    def forward(self, speed=50, duration=1.0):
        """前進: 両モーター同速で前進"""
        # set_motor_a(speed), set_motor_b(speed)
        # time.sleep(duration)
        # stop()
        pass

    def backward(self, speed=50, duration=1.0):
        """後退: 両モーター同速で後退"""
        pass

    def turn_left(self, speed=40, duration=0.5):
        """左旋回: 右モーター前進・左モーター停止"""
        # set_motor_a(0), set_motor_b(speed)
        pass

    def turn_right(self, speed=40, duration=0.5):
        """右旋回: 左モーター前進・右モーター停止"""
        # set_motor_a(speed), set_motor_b(0)
        pass

    def spin_left(self, speed=40, duration=0.5):
        """左スピン（超信地旋回）: 左後退・右前進"""
        # set_motor_a(-speed), set_motor_b(speed)
        pass

    def spin_right(self, speed=40, duration=0.5):
        """右スピン（超信地旋回）: 左前進・右後退"""
        # set_motor_a(speed), set_motor_b(-speed)
        pass

    def stop(self):
        """停止"""
        self.motor.stop()

    def cleanup(self):
        self.motor.cleanup()
```

---

## move_robot.sh（OpenClaw用ラッパー）

`/home/tukapontas/gakukoma/tools/move_robot.sh`:

```bash
#!/bin/bash
# 使用例: move_robot.sh forward 1.0 50
# 引数: direction [duration] [speed]
python3 /home/tukapontas/gakukoma/motor/move_robot_cmd.py "$@"
```

`chmod +x tools/move_robot.sh` で実行権限を付与すること。

---

## move_robot_cmd.py の実装仕様

```python
"""
move_robot.sh から呼ばれるコマンドラインエントリーポイント
引数: direction [duration] [speed]
出力: 実行した動作の結果を標準出力（OpenClawが読み取る）
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
    duration = float(sys.argv[2]) if len(sys.argv) > 2 else 1.0
    speed = int(sys.argv[3]) if len(sys.argv) > 3 else 50

    driver = MotorDriver()
    try:
        # direction に応じたメソッドを呼ぶ
        # 成功したら標準出力に結果を出力
        print(f"{VALID_DIRECTIONS.get(direction, direction)} 完了（{duration}秒・速度{speed}%）")
    finally:
        driver.cleanup()  # 必ず実行

if __name__ == "__main__":
    main()
```

---

## モーター方向補正について

走行テスト（Task H）で左右モーターの回転方向が期待と逆になった場合:

1. **config.yaml に `motor_a_invert: true` / `motor_b_invert: true` フラグを追加**して、`tb6612_ctrl.py` 内で符号反転させる方法を推奨
2. 物理的なモーター配線の差し替えは行わないこと（再現性が下がる）

---

## OpenClaw 統合

### TOOLS.md への追記

```markdown
## move_robot
走行コマンドを実行する。前進・後退・左右旋回・スピン・停止が可能。

**シェルコマンド**: `/home/tukapontas/gakukoma/tools/move_robot.sh`

**引数**:
- direction: forward / backward / left / right / spin_left / spin_right / stop
- duration: 秒数（デフォルト: 1.0）
- speed: 速度 0〜100%（デフォルト: 50）

**使用例**:
- `move_robot.sh forward 2.0 60` → 2秒間、速度60%で前進
- `move_robot.sh left 0.5` → 0.5秒間、左旋回
- `move_robot.sh stop` → 即停止
```

### SOUL.md への追記

Phase 3 能力として「走行可能（前進・後退・左右旋回）」を追記すること。

---

## テスト仕様

以下のシナリオで動作を確認すること（Task H の統合テストで Gemini と合同実施）:

| # | テスト | コマンド | 合格条件 |
|---|---|---|---|
| T-5 | 前進 | `move_robot.sh forward 1.0` | 1秒間前進して停止 |
| T-6 | 後退 | `move_robot.sh backward 1.0` | 1秒間後退して停止 |
| T-7 | 左旋回 | `move_robot.sh left 0.5` | 左に旋回 |
| T-8 | 右旋回 | `move_robot.sh right 0.5` | 右に旋回 |
| T-9 | 停止 | `move_robot.sh stop` | 即時停止 |
| T-10 | 走行+首振り同時 | 手動並行実行 | 走行中に look_at_user() が正常動作 |
| T-11 | OpenClaw統合 | 「前に進んで」と発話 | move_robot() が起動し走行 |

---

## 注意事項

- **gpiozero を使用すること**（RPi.GPIO は Pi5 非対応・RuntimeError）
- **`__del__` を実装しないこと**（スクリプト終了時の予期せぬモーター停止を防ぐ）
- **`finally` ブロックで `cleanup()` を必ず実行すること**（走りっぱなし防止）
- **PWMはハードウェアPWMを使用すること**（GPIO12/GPIO13 はハードウェアPWM対応）。ソフトウェアPWMはモーター制御で音が出たり不安定になる場合がある
- gpiozero でハードウェアPWMを使う場合は `PWMOutputDevice` または `pigpio` ファクトリが必要。以下を参照:
  ```bash
  # pigpio デーモンを使う場合（推奨）
  sudo pigpiod
  GPIOZERO_PIN_FACTORY=pigpio python3 ...
  ```
  あるいは systemd で pigpiod を自動起動させる設定を追加すること。

---

## 完了報告書の作成

完了後、`coding/20260402_phase3_move_robot_completed.md` を作成し、以下を記録すること:

- 実装したファイル一覧とパス
- config.yaml に追記した内容
- TOOLS.md / SOUL.md の更新内容
- T-5〜T-11 のテスト結果
- モーター方向補正の有無（invert フラグの設定状況）
- 特記事項（pigpiod の設定方法など）
