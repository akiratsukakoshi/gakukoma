# 指示書：Phase 2 `look_at_user()` ツール実装・統合テスト

作成日: 2026-03-15
作成者: ClaudeCode（司令塔）
担当: Antigravity
完了報告ファイル名: `20260315_phase2_look_at_user_completed.md`

---

## 前提条件（両方の完了報告書が存在することを確認してから着手）

1. `coding/20260315_phase2_camera_opencv_completed.md` が存在すること
2. `hardware/20260315_phase2_pca9685_wiring_completed.md` が存在すること

**作業前に上記2つの完了報告書を読み、以下を確認・メモすること**:
- カメラのデバイス番号（`/dev/video` 何番か）
- PCA9685の動作確認状況
- **サーボの回転方向**（Geminiの報告書に記載: 「角度を増やすと左右どちらに動くか」）

---

## 作業概要

1. `pca9685_ctrl.py`（サーボ制御クラス）実装
2. `pan_tilt.py`（パン・チルト制御クラス）実装
3. `look_at_user.py`（顔追跡統合スクリプト）実装
4. OpenClaw統合（シェルラッパー + TOOLS.md更新）
5. 統合テスト（T-1〜T-9全項目）

---

## 環境情報

- マシン: Raspberry Pi 5 Model B (16GB RAM, aarch64)
- OS: Debian GNU/Linux 13 (trixie)
- Python: 3.13.5（`python3`）
- 既存ファイル:
  - `~/gakukoma/camera/capture.py`（Phase 2 Task A で作成済み）
  - `~/gakukoma/camera/face_detect.py`（Phase 2 Task A で作成済み）
  - `~/gakukoma/voice_loop/config.yaml`（Phase 1 + Task A で更新済み）

---

## タスク 1：ディレクトリ作成

```bash
mkdir -p /home/tukapontas/gakukoma/servo
```

---

## タスク 2：`pca9685_ctrl.py` 実装

**ファイルパス**: `/home/tukapontas/gakukoma/servo/pca9685_ctrl.py`

**機能**: PCA9685 を操作して指定チャンネルのサーボを任意の角度に設定する。

**実装要件**:

```python
import board, busio, adafruit_pca9685

class PCA9685Controller:
    """PCA9685 サーボドライバの制御クラス"""

    SERVO_FREQ = 50          # SG90は50Hz PWM
    PULSE_MIN_US = 1000      # 0° = 1000μs
    PULSE_MAX_US = 2000      # 180° = 2000μs
    PERIOD_US = 20000        # 1/50Hz = 20000μs

    def __init__(self):
        i2c = busio.I2C(board.SCL, board.SDA)
        self.pca = adafruit_pca9685.PCA9685(i2c)
        self.pca.frequency = self.SERVO_FREQ

    def set_angle(self, channel: int, angle: int):
        """
        指定チャンネルのサーボを angle 度に設定する
        angle: 0〜180 の整数
        """
        # 角度 → パルス幅(μs) → duty cycle(16bit) の変換
        angle = max(0, min(180, angle))  # クランプ
        pulse_us = self.PULSE_MIN_US + (angle / 180.0) * (self.PULSE_MAX_US - self.PULSE_MIN_US)
        duty = int(pulse_us / self.PERIOD_US * 65535)
        self.pca.channels[channel].duty_cycle = duty

    def release(self):
        """リソース解放（サーボ脱力・I2C切断）"""
        # 全チャンネルのduty_cycleを0にして脱力
        for ch in range(16):
            self.pca.channels[ch].duty_cycle = 0
        self.pca.deinit()
```

---

## タスク 3：`pan_tilt.py` 実装

**ファイルパス**: `/home/tukapontas/gakukoma/servo/pan_tilt.py`

**機能**: パン・チルト台座の2軸をまとめて制御するクラス。角度制限・センター移動を提供する。

**実装要件**:

```python
import yaml
from servo.pca9685_ctrl import PCA9685Controller

class PanTiltController:
    """パン・チルト台座の2軸制御クラス"""

    def __init__(self, config_path="~/gakukoma/voice_loop/config.yaml"):
        # config.yaml から servo セクションを読み込む
        # pan_channel, tilt_channel,
        # pan_min, pan_max, tilt_min, tilt_max を取得
        self.ctrl = PCA9685Controller()
        # 現在角度の追跡
        self.current_pan = 90
        self.current_tilt = 90

    def set_pan(self, angle: int):
        """パン角度を設定（制限値にクランプして適用）"""
        angle = max(self.pan_min, min(self.pan_max, angle))
        self.ctrl.set_angle(self.pan_channel, angle)
        self.current_pan = angle

    def set_tilt(self, angle: int):
        """チルト角度を設定（制限値にクランプして適用）"""
        angle = max(self.tilt_min, min(self.tilt_max, angle))
        self.ctrl.set_angle(self.tilt_channel, angle)
        self.current_tilt = angle

    def center(self):
        """台座を正面（パン90°, チルト90°）に向ける"""
        self.set_pan(90)
        self.set_tilt(90)

    def release(self):
        self.ctrl.release()
```

**`config.yaml` への servo セクション追記**（既存ファイルに追記）:

```yaml
# サーボ設定（Phase 2追加）
servo:
  pan_channel: 0        # PCA9685 ch0 = パン（左右）
  tilt_channel: 1       # PCA9685 ch1 = チルト（上下）
  pan_min: 0
  pan_max: 180
  tilt_min: 60          # 機構的制限（下限）
  tilt_max: 120         # 機構的制限（上限）
  pan_gain: 0.1         # 1pxあたりの補正角度（要チューニング）
  tilt_gain: 0.1
  convergence_px: 30    # 収束判定の許容誤差（ピクセル）
  max_iterations: 20    # 最大追跡ループ回数
  loop_interval: 0.1    # ループ間隔（秒）
```

**サーボ回転方向の調整**:
Geminiの完了報告書に記載されたサーボ回転方向を確認し、`pan_gain` の符号を調整すること。
- パン: 「角度増加で右に動く」→ `pan_gain` は正のまま
- パン: 「角度増加で左に動く」→ `pan_gain` を負にするか、`set_pan` 内で角度を反転させる
- 同様にチルトも確認して調整する

---

## タスク 4：`look_at_user.py` 実装

**ファイルパス**: `/home/tukapontas/gakukoma/look_at_user.py`

**動作フロー**:

```
1. カメラ・サーボ初期化
2. サーボをセンター（正面）に向ける
3. 追跡ループ（max_iterations 回まで）:
   a. フレーム取得
   b. 顔検出
   c. 顔が見つからない場合 → リトライカウントを増やす（最大3回連続で顔なし→終了）
   d. 顔が複数検出された場合 → 最大面積の顔を使用（最も近いユーザーと仮定）
   e. 顔の中心座標 (cx, cy) を算出
   f. 画面中心 (width/2, height/2) とのオフセット (dx, dy) を算出
   g. 角度補正量 = オフセット × gain
   h. 新しい角度 = 現在角度 + 補正量（クランプ適用）
   i. サーボ更新
   j. |dx| < convergence_px かつ |dy| < convergence_px なら収束・終了
4. 終了メッセージを標準出力
   - 収束した場合: "顔追跡成功: pan={angle}° tilt={angle}°"
   - タイムアウト: "タイムアウト: 顔が見つかりませんでした"
5. サーボリソース解放
```

**実装要件**:

```python
import sys, time, yaml
sys.path.append('/home/tukapontas/gakukoma')

from camera.capture import CameraCapture
from camera.face_detect import detect_faces
from servo.pan_tilt import PanTiltController

# config.yaml のパスは os.path.expanduser で解決すること
CONFIG_PATH = os.path.expanduser("~/gakukoma/voice_loop/config.yaml")
```

**エラーハンドリング**:
- カメラが開けない場合: 「カメラが見つかりません」と出力して終了コード1で終了
- PCA9685が見つからない場合: 「サーボドライバが見つかりません（PCA9685未接続）」と出力して終了コード1で終了
- 上記エラーはOpenClaw経由で呼ばれた際にも伝わるよう標準出力に出すこと（標準エラーではなく）

---

## タスク 5：OpenClaw統合

### 5-1. シェルラッパー作成

**ファイルパス**: `/home/tukapontas/gakukoma/tools/look_at_user.sh`

```bash
#!/bin/bash
python3 /home/tukapontas/gakukoma/look_at_user.py
```

```bash
chmod +x /home/tukapontas/gakukoma/tools/look_at_user.sh
```

### 5-2. TOOLS.md 更新

`~/.openclaw/workspace/TOOLS.md` の `GAKUKOMA Vision Tools` セクションに以下を追記:

```markdown
### look_at_user
- コマンド: `/home/tukapontas/gakukoma/tools/look_at_user.sh`
- 機能: Webカメラで顔を検出し、パン・チルトサーボを制御してカメラをユーザーの顔に向ける
- 引数: なし
- 戻り値: 「顔追跡成功: pan=X° tilt=Y°」または「タイムアウト: 顔が見つかりませんでした」
- 備考: 実行には PCA9685（I2C 0x40）が接続されている必要がある
```

### 5-3. SOUL.md 更新

`~/.openclaw/workspace/SOUL.md` を開き、Phase 2 能力の記述を最終版に更新する。
（「look_at_user ツール ※サーボ手配後に有効化」となっている仮記述を削除し、確定版に書き換える）

---

## タスク 6：統合テスト

以下の全テストを実行し、完了報告書に結果を記録する。

| # | テスト | 合格条件 |
|---|---|---|
| T-1 | カメラ認識 | `VideoCapture(device).isOpened()` が True |
| T-2 | フレーム取得 | `/tmp/gakukoma_capture.jpg` が生成される |
| T-3 | 顔検出（正面顔あり） | 少なくとも1件の矩形が返る |
| T-4 | 顔検出（顔なし） | 空リスト `[]` が返り、エラーにならない |
| T-5 | `see_around()` 単体 | 日本語の説明文が標準出力に表示される |
| T-6 | サーボ単体（パン） | ch0が 0°/90°/180° に動く |
| T-7 | サーボ単体（チルト） | ch1が 60°/90°/120° に動く |
| T-8 | `look_at_user()` 単体 | 人物の顔がある場合にサーボが動き収束メッセージが出る |
| T-9-a | OpenClaw統合 `see_around` | 「周りを見て」と言うと see_around() が起動し結果を音声で返す |
| T-9-b | OpenClaw統合 `look_at_user` | 「こっちを見て」と言うと look_at_user() が起動しサーボが動く |
| T-10 | エラー耐性 | 顔が見つからない場合にエラーにならず終了メッセージが返る |

**T-8のチューニング方法**:
収束しない・オーバーシュートする場合は `config.yaml` の `pan_gain` / `tilt_gain` を調整する。
- ゆっくり動く（収束が遅い）→ gain を増やす（0.1 → 0.15〜0.2）
- 振動する / 行き過ぎる → gain を減らす（0.1 → 0.05〜0.08）

---

## 完了報告書の作成

全タスク完了後、`/home/tukapontas/a2a/coding/20260315_phase2_look_at_user_completed.md` を作成し、以下を記載すること：

- 各タスクの完了状況
- 統合テスト T-1〜T-10 の結果（全項目）
- 最終的な `pan_gain` / `tilt_gain` の値（チューニング後）
- サーボ回転方向の確認結果（angle増加で右/左/上/下のどちらに動くか）
- `look_at_user()` の追跡速度・収束精度の評価（良好 / 要改善）
- 問題点・申し送り事項（あれば）
- Phase 3 への申し送り（サーボ・カメラに関する注意点）
