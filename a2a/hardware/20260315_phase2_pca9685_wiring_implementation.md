# 指示書：Phase 2 PCA9685サーボドライバ配線

作成日: 2026-03-15
作成者: ClaudeCode（司令塔）
担当: Gemini
完了報告ファイル名: `20260315_phase2_pca9685_wiring_completed.md`

---

## 前提条件

- パン・チルト台座の組み立て（`20260315_phase2_pantilt_assembly`）が完了していること
- SG90×2のケーブルに「パン/ch0」「チルト/ch1」のラベルが付いていること
- 以下のパーツが手元にあること:
  - PCA9685 16chサーボドライバボード
  - ジャンパーワイヤ（オス-メス）×5本以上
  - Raspberry Pi 5（起動済み）

---

## 作業概要

1. Raspberry Pi 5 の I2C を有効化
2. PCA9685 と RPi 5 を I2C 接続
3. SG90×2 を PCA9685 に接続
4. i2cdetect で接続確認
5. Python から疎通・サーボ動作確認

---

## タスク 1：I2C 有効化確認

### 1-1. 有効化状態の確認

```bash
ls /dev/i2c*
```

`/dev/i2c-1` が存在すればI2Cは有効。存在しない場合は以下を実行:

```bash
raspi-config nonint do_i2c 0
reboot
```

### 1-2. i2c-tools インストール

```bash
apt install -y i2c-tools
```

---

## タスク 2：PCA9685 配線

**必ず電源OFF（シャットダウン後）の状態で配線すること。**

### 配線表

| PCA9685 ピン | Raspberry Pi 5 ピン | 物理ピン番号 | 備考 |
|---|---|---|---|
| SDA | GPIO2 | Pin 3 | I2Cデータ線 |
| SCL | GPIO3 | Pin 5 | I2Cクロック線 |
| VCC | 3.3V | Pin 1 | ロジック電源（3.3V） |
| GND | GND | Pin 6 | 共通グランド |
| V+ | 5V | Pin 4 | サーボ駆動電源 |

> **V+ 電源について**: Phase 2 では暫定的に RPi 5V（Pin 4）から供給する。SG90×2 の電流合計は最大約 400mA 程度（停止時）のため、Pi 5 の電源（公式 USB-C PD 27W アダプタ使用の場合）で許容範囲内。ただし、サーボが連続負荷になる場合は外部 5V 電源（BEC 等）を検討すること。

### Raspberry Pi 5 ピン配置（参考）

```
   3.3V  [Pin 1]  [Pin 2]  5V
  GPIO2  [Pin 3]  [Pin 4]  5V
  GPIO3  [Pin 5]  [Pin 6]  GND
  ...
```

**注意**: ジャンパーワイヤを差し込む前にピン番号を必ずダブルチェックする。誤挿入による短絡・GPIO破損に注意。

---

## タスク 3：SG90 の PCA9685 への接続

SG90 のコネクタを PCA9685 のサーボ端子列に以下の通り接続する。

| SG90 | PCA9685 端子列 | チャンネル |
|---|---|---|
| パン用 SG90（左右） | ch0（0番ポート） | channel 0 |
| チルト用 SG90（上下） | ch1（1番ポート） | channel 1 |

**SG90 コネクタのピンアサイン**:

| コネクタの色 | 信号 | PCA9685端子 |
|---|---|---|
| 茶 | GND | G（下段） |
| 赤 | VCC (5V) | V（中段） |
| 橙 | Signal (PWM) | S（上段） |

PCA9685 のサーボ端子列は下から `G / V / S` の順（基板によって異なる場合があるため、シルク印刷を確認すること）。

---

## タスク 4：i2cdetect で接続確認

```bash
i2cdetect -y 1
```

以下のように `40` が表示されれば正常（PCA9685のデフォルトI2Cアドレスは `0x40`）:

```
     0  1  2  3  4  5  6  7  8  9  a  b  c  d  e  f
00:          -- -- -- -- -- -- -- -- -- -- -- -- --
10: -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- --
20: -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- --
30: -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- --
40: 40 -- -- -- -- -- -- -- -- -- -- -- -- -- -- --
...
```

`40` が表示されない場合は配線を再確認する（特に SDA/SCL の誤接続）。

---

## タスク 5：Python ライブラリインストールと疎通確認

### 5-1. ライブラリインストール

```bash
pip3 install adafruit-circuitpython-pca9685 adafruit-circuitpython-motor
```

### 5-2. 疎通確認

```bash
python3 -c "
import board, busio, adafruit_pca9685
i2c = busio.I2C(board.SCL, board.SDA)
pca = adafruit_pca9685.PCA9685(i2c)
pca.frequency = 50
print('PCA9685 接続OK。周波数設定50Hz完了。')
pca.deinit()
"
```

---

## タスク 6：サーボ動作確認

以下のスクリプトを実行し、SG90が実際に動くことを確認する。

```python
# /tmp/servo_test.py として実行
import board, busio, adafruit_pca9685, time

i2c = busio.I2C(board.SCL, board.SDA)
pca = adafruit_pca9685.PCA9685(i2c)
pca.frequency = 50

def angle_to_duty(angle: int) -> int:
    """SG90: 0°=1000μs, 90°=1500μs, 180°=2000μs → dutycycle（16bit）"""
    pulse_us = 1000 + (angle / 180.0) * 1000
    duty = int(pulse_us / 20000.0 * 65535)
    return duty

# パン ch0：90°（センター）→ 45°（左）→ 135°（右）→ 90°（センター）
print("パン ch0 テスト開始")
for angle in [90, 45, 135, 90]:
    print(f"  パン: {angle}°")
    pca.channels[0].duty_cycle = angle_to_duty(angle)
    time.sleep(1.0)

# チルト ch1：90°（センター）→ 70°（下）→ 110°（上）→ 90°（センター）
print("チルト ch1 テスト開始")
for angle in [90, 70, 110, 90]:
    print(f"  チルト: {angle}°")
    pca.channels[1].duty_cycle = angle_to_duty(angle)
    time.sleep(1.0)

print("テスト完了")
pca.deinit()
```

```bash
python3 /tmp/servo_test.py
```

**合格条件**:
- パン用SG90がセンター→左→右→センターと動く
- チルト用SG90がセンター→下→上→センターと動く
- どちらも物理的に可動し、異音・振動がないこと

**もし動かない場合のチェックリスト**:
- [ ] SG90コネクタのGND/VCC/Signalの向きが正しいか
- [ ] V+（5V）がPCA9685に入っているか
- [ ] `i2cdetect` で `0x40` が見えているか
- [ ] `pca.frequency = 50` が設定されているか（SG90は50Hz必須）

---

## 完了報告書の作成

全タスク完了後、`/home/tukapontas/a2a/hardware/20260315_phase2_pca9685_wiring_completed.md` を作成し、以下を記載すること：

- I2C有効化確認結果
- `i2cdetect -y 1` の出力全文（0x40が確認できること）
- `python3` からの疎通確認結果
- サーボ動作確認結果（パン・チルト各軸の動作可否）
- 電源構成（V+: RPi 5V / 外部電源 どちらを使用したか）
- SG90の回転方向とangle_to_dutyの対応確認（「45°にしたら左に動いた」等）
- 問題点・気になった点（あれば）
- 次の作業（`look_at_user()` 実装）への申し送り事項
  - 特に: サーボ回転方向の確認（角度を増やすと左右どちらに動くか）
