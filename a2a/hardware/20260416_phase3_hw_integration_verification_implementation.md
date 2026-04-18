# 指示書：Phase 3 Task F 統合ハードウェア検証

**作成日:** 2026-04-16
**作成者:** ClaudeCode（司令塔）
**担当:** Gemini（ハードウェア担当）
**前提条件:** Task A2 + Task D + Task E 全完了（✅ 確認済み）

---

## 概要

全電源系統・全配線の最終確認と通電テストを行う。
ソフトウェア実装（Task G: `move_robot()` 実装）に進むための **最終ハードウェアGOサイン** を出すことが目的。

---

## ⚠️ 重要：変更済み配線情報

Task D 実施中に以下の変更が発生しています。**必ず変更後の情報で確認すること。**

### TB6612FNG GPIOアサイン（確定版）

| TB6612FNG端子 | Pi5物理ピン | GPIO番号 | 役割 |
| :--- | :---: | :---: | :--- |
| PWMA | Pin 32 | GPIO 12 | 左モーター速度 |
| AIN1 | Pin 38 | GPIO 20 | 左モーター方向1 |
| **AIN2** | **Pin 37** | **GPIO 26** | **左モーター方向2（★当初GPIO21から変更）** |
| PWMB | Pin 33 | GPIO 13 | 右モーター速度 |
| BIN1 | Pin 18 | GPIO 24 | 右モーター方向1 |
| BIN2 | Pin 22 | GPIO 25 | 右モーター方向2 |
| STBY | Pin 36 | GPIO 16 | スタンバイ解除 |
| VCC | Pin 1 | 3.3V | ロジック電源 |
| VM | - | 12V（系統B生電圧） | モーター駆動電源 |

> **変更理由:** Pin 40 (GPIO 21) はスピーカーアンプ MAX98357A が使用済みのため、AIN2 を Pin 37 (GPIO 26) へ恒久変更した。

### パンチルト設定（Task E 完了後にClaudeCodeが調整済み）

| パラメータ | 設定値 | 備考 |
| :--- | :---: | :--- |
| pan_min | 0° | |
| pan_max | **160°** | Pi5本体との物理干渉防止（170°から再変更） |
| tilt_min | 60° | |
| tilt_max | 120° | |
| tilt_invert | true | DS3218物理反転を吸収 |

---

## 検証チェックリスト

全項目に合格したら完了報告書を作成すること。

### 【電源系統確認】

| # | 確認項目 | 確認方法 | 合格基準 |
| :---: | :--- | :--- | :--- |
| P-1 | 系統A電圧（UPS HAT→Pi5） | UPS HAT表示またはテスター | 5V ±5% |
| P-2 | 系統B電圧（XL4015出力→PCA9685 V+） | テスター（PCA9685 V+端子で計測） | 6.0V ±0.1V |
| P-3 | 系統B電圧（Li-ionバッテリー生電圧→TB6612 VM） | テスター（TB6612 VM端子で計測） | 10.5〜12.6V（充電状態により変動） |
| P-4 | GND共通接地 | テスター導通モード | Pi5 GNDピン ↔ TB6612FNG GND ↔ PCA9685 GND が全て導通すること |

### 【パンチルト系（DS3218）確認】

Pi5上で以下のコマンドを実行して確認する。

```bash
# センター位置へ移動
bash /home/tukapontas/gakukoma/tools/set_pan_tilt.sh 90 90
```

```bash
# パン左方向確認
bash /home/tukapontas/gakukoma/tools/look_direction.sh left
```

```bash
# パン右方向確認
bash /home/tukapontas/gakukoma/tools/look_direction.sh right
```

```bash
# チルト上方向確認
bash /home/tukapontas/gakukoma/tools/look_direction.sh up
```

```bash
# チルト下方向確認
bash /home/tukapontas/gakukoma/tools/look_direction.sh down
```

| # | 確認項目 | 合格基準 |
| :---: | :--- | :--- |
| S-1 | I2C デバイス認識 | `i2cdetect -y 1` で `0x40` が表示されること |
| S-2 | センター（90, 90） | カメラが正面・水平を向くこと |
| S-3 | パン左（look_direction left） | カメラが左方向を向くこと（ぶつかりや異音なし） |
| S-4 | パン右（look_direction right） | カメラが右方向を向くこと（ぶつかりや異音なし） |
| S-5 | チルト上（look_direction up） | カメラが上方向を向くこと（ぶつかりや異音なし） |
| S-6 | チルト下（look_direction down） | カメラが下方向を向くこと（ぶつかりや異音なし） |

> **注意:** サーボ動作中に異音・振動・過熱がある場合は動作を中断し、完了報告書に記録すること。

### 【TB6612FNG モータードライバ確認】

Pi5上で以下のスクリプトを実行して確認する。

```bash
# STBY疎通確認（モータードライバ制御権確認）
python3 -c "
from gpiozero import OutputDevice
import time
stby = OutputDevice(16)
stby.on()
print('STBY HIGH: モータードライバが命令を受け付けられる状態になりました')
time.sleep(1)
stby.off()
print('STBY LOW: スタンバイ状態に戻しました')
"
```

```bash
# モーター前進確認（左モーター単体・低速・1秒）
python3 -c "
from gpiozero import OutputDevice, PWMOutputDevice
import time
stby = OutputDevice(16)
ain1 = OutputDevice(20)
ain2 = OutputDevice(26)
pwma = PWMOutputDevice(12, frequency=1000)
stby.on()
ain1.on()
ain2.off()
pwma.value = 0.3  # 30%速度
print('左モーター前進中（30%速度）...')
time.sleep(1)
ain1.off()
pwma.value = 0
stby.off()
print('停止')
"
```

```bash
# モーター前進確認（右モーター単体・低速・1秒）
python3 -c "
from gpiozero import OutputDevice, PWMOutputDevice
import time
stby = OutputDevice(16)
bin1 = OutputDevice(24)
bin2 = OutputDevice(25)
pwmb = PWMOutputDevice(13, frequency=1000)
stby.on()
bin1.on()
bin2.off()
pwmb.value = 0.3  # 30%速度
print('右モーター前進中（30%速度）...')
time.sleep(1)
bin1.off()
pwmb.value = 0
stby.off()
print('停止')
"
```

| # | 確認項目 | 合格基準 |
| :---: | :--- | :--- |
| M-1 | STBY疎通確認 | スクリプトがエラーなく完了し、`STBY HIGH: ...` メッセージが表示されること |
| M-2 | 左モーター前進 | 左モーター（AO1/AO2接続）が約1秒間回転すること |
| M-3 | 右モーター前進 | 右モーター（BO1/BO2接続）が約1秒間回転すること |
| M-4 | モーター停止 | 停止コマンド後にモーターが止まること |

> **注意事項:**
> - モーター試験時はタンクが動き出す可能性があるため、**手で軽く押さえるか、持ち上げた状態で実施**すること
> - 異臭・発熱・異常振動が発生した場合は即座に電源を切断すること

---

## バッテリー駆動最終確認

ACアダプタを完全に切断した状態で P-1〜P-4 + S-1〜S-6 + M-1〜M-4 のうち主要項目が合格することを確認する。

```bash
# バッテリー駆動状態でのスロットル確認
vcgencmd get_throttled
# → 0x0 が理想（非ゼロの場合は電流不足の疑い）
```

| # | 確認項目 | 合格基準 |
| :---: | :--- | :--- |
| B-1 | UPS HAT単独起動 | ACアダプタなしでPi5が起動すること |
| B-2 | スロットルなし | `vcgencmd get_throttled` が `0x0` を返すこと |
| B-3 | I2C正常（バッテリー駆動） | `i2cdetect -y 1` で `0x40` が表示されること |

---

## 完了条件

以下の全項目を満たしたら完了とする。

- [ ] P-1〜P-4：電源系統全確認合格
- [ ] S-1〜S-6：パンチルト全方向動作確認合格
- [ ] M-1〜M-4：モータードライバ・左右モーター動作確認合格
- [ ] B-1〜B-3：バッテリー駆動最終確認合格

---

## 完了報告書の記載事項

完了報告書（`20260416_phase3_hw_integration_verification_completed.md`）に以下を記録すること。

1. **電圧実測値一覧**（P-1〜P-4 の全テスター計測値）
2. **パンチルト動作確認結果**（S-1〜S-6 各項目の合否）
3. **左右モーター回転方向の記録**
   - 左モーター: AIN1=H/AIN2=L のとき「前進方向に回転する」か「後退方向に回転するか」
   - 右モーター: BIN1=H/BIN2=L のとき「前進方向に回転する」か「後退方向に回転するか」
   - ※ Task G（`move_robot()` 実装）でこの情報を使用する
4. **バッテリー駆動確認結果**（B-1〜B-3 の合否 + `vcgencmd get_throttled` の出力値）
5. **特記事項**（異音・発熱・振動など気になった点があれば記録）

---

## 次のステップ

本タスク完了後、ClaudeCode が Task G（`move_robot()` 実装）の指示書を作成する。
**指示書作成に必要なため、左右モーターの回転方向情報を必ず完了報告書に記録すること。**
