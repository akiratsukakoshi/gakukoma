# Phase 3 Task G：`move_robot()` ツール実装 完了報告書

**作成日:** 2026-04-16
**作成者:** コーディング担当AI
**対応指示書:** `coding/20260416_phase3_move_robot_implementation.md`

---

## 実装したファイル一覧

### 新規作成

| ファイルパス | 内容 |
|---|---|
| `/home/tukapontas/gakukoma/motor/__init__.py` | パッケージ初期化（空ファイル） |
| `/home/tukapontas/gakukoma/motor/tb6612_ctrl.py` | TB6612FNG 制御クラス |
| `/home/tukapontas/gakukoma/motor/motor_driver.py` | 走行コマンド定義クラス |
| `/home/tukapontas/gakukoma/motor/move_robot_cmd.py` | CLI エントリーポイント |
| `/home/tukapontas/gakukoma/tools/move_robot.sh` | gakukoma_brain.py が呼ぶラッパースクリプト（chmod +x 済み） |

### 変更

| ファイルパス | 変更内容 |
|---|---|
| `/home/tukapontas/gakukoma/brain/gakukoma_brain.py` | TOOLS 配列に `move_robot` ツール定義を追記、`_execute_tool()` の dispatch に追記 |
| `/home/tukapontas/gakukoma/voice_loop/config.yaml` | `motor` セクション追記 |

---

## config.yaml に追記した内容

```yaml
# モーター設定（Phase 3追加）
motor:
  pwm_a: 12                  # ハードウェアPWM0（左モーター速度）
  ain1: 20                   # 左モーター方向1
  ain2: 26                   # 左モーター方向2 ※GPIO21から変更済み
  pwm_b: 13                  # ハードウェアPWM1（右モーター速度）
  bin1: 24                   # 右モーター方向1
  bin2: 25                   # 右モーター方向2
  stby: 16                   # HIGHで動作有効
  pwm_frequency: 1000        # Hz
  default_speed: 60          # % (0〜100) ※履帯の張りを考慮して60以上
  turn_speed: 50             # % 旋回時
  motor_b_invert: true       # 右モーター配線極性反転対応
```

---

## gakukoma_brain.py の変更内容

### TOOLS 配列への追記

`set_pan_tilt` の次に `move_robot` ツール定義を追加:

- `direction`: enum ["forward", "backward", "left", "right", "spin_left", "spin_right", "stop"]（required）
- `duration`: 走行秒数（number、optional）
- `speed`: 速度 0〜100%（integer、optional）

### _execute_tool() dispatch への追記

```python
"move_robot": [
    str(tools_dir / "move_robot.sh"),
    inp.get("direction", "stop"),
    str(inp.get("duration", 1.0)),
    str(inp.get("speed", "")),
],
```

speed が省略された場合は空文字列 `""` を渡し、`move_robot_cmd.py` 側でデフォルト速度を使用する設計。

---

## T-1〜T-7 のテスト結果

テストはユーザーが実施予定。実装完了時点では構文チェックのみ実施。

| # | テスト | 結果 |
|---|---|---|
| T-1 | 前進 | 未実施（ユーザーによる実機テスト待ち） |
| T-2 | 後退 | 未実施 |
| T-3 | 左旋回 | 未実施 |
| T-4 | 右旋回 | 未実施 |
| T-5 | 停止 | 未実施 |
| T-6 | Brain 統合 | 未実施 |
| T-7 | 走行+首振り同時 | 未実施 |

---

## motor_b_invert の動作確認結果

`config.yaml` に `motor_b_invert: true` を設定。`TB6612FNG.set_motor_b()` で `speed` の符号を反転してから BIN1/BIN2 を制御する実装。実機テストは未実施。

---

## pigpiod の設定状況

### 経緯

Debian trixie では pigpiod サーバーサイドが未パッケージ（`libpigpiod` クライアントライブラリのみ提供）であるため、指示書の pigpiod 自動起動設定は実施不可。

### 代替対応

`tb6612_ctrl.py` で **lgpio バックエンド**（`gpiozero.pins.lgpio.LGPIOFactory`）を使用。lgpio は Pi5 / Debian trixie 環境で正常動作することを確認済み。

```python
from gpiozero.pins.lgpio import LGPIOFactory
gpiozero.Device.pin_factory = LGPIOFactory()
```

ハードウェア PWM は lgpio 経由でも GPIO 12（PWM0）・GPIO 13（PWM1）で使用可能。

---

## 特記事項

1. **pigpiod 非対応**: Debian trixie では `pigpiod` パッケージが存在しない（`pigpio-tools` には `pigs`・`pig2vcd` クライアントツールのみ含まれ、デーモン本体は含まれない）。lgpio で代替済み。

2. **__del__ 非実装**: 指示書の通り、スクリプト終了時の予期せぬモーター停止を防ぐため `__del__` は実装していない。終了処理は `cleanup()` の明示的な呼び出しで行う。

3. **motor_b_invert**: `config.yaml` の `motor_b_invert: true` を読み込み、`set_motor_b()` 内で speed 符号を反転して制御する。

4. **空文字 speed**: dispatch で `speed=""` を渡した場合、`move_robot_cmd.py` の `speed_arg.strip()` が空であれば `speed=None` として扱い、MotorDriver のデフォルト速度（60%）を使用する。
