# Phase 3 アクションプラン：大地への進出（Body & Power）

作成日: 2026-04-02
作成者: ClaudeCode（司令塔）
対象フェーズ: Phase 3

---

## 1. フェーズ目標

「自律走行できる、自立したロボット」の実現。

- Waveshare UPS HAT(B) による Pi5 の完全バッテリー駆動（系統A確立）
- 11.1V Li-ionパック + LM2596 + TB6612FNG による走行・サーボ独立電源（系統B確立）
- SainSmart タンクシャーシ（YP100）の組み立てと走行動作
- DS3218 サーボへの換装完了（アルミパンチルト台座移行）
- `move_robot()` ツールの実装と OpenClaw 統合
- 走行・首振り・電源の統合テスト合格

---

## 2. ハードウェア構成（全手配済み・タンク組立完了）

### 電源系統

| 系統 | 電源 | 変換 | 供給先 | ポイント |
|---|---|---|---|---|
| 系統A（脳用） | UPS HAT(B) + NCR18650×2 | 5V/5A | Pi5（Pogoピン） | GPIO非占有・自律起動対応 |
| 系統B→サーボ | 11.1V Li-ion | LM2596（6.0V固定） | PCA9685 V+ → DS3218×2 | 1000μFコンデンサ並列必須 |
| 系統B→モーター | 11.1V Li-ion | 直結 | TB6612FNG VM端子 | YP100モーターは12V対応 |
| 共通GND | - | - | 系統A・B全基板 | **必ず共通接地** |

### 走行系

| パーツ | 仕様 | 役割 |
|---|---|---|
| SainSmart タンクシャーシ | 金属製・DCモーター×2 | 本体・走行機構 |
| TB6612FNG | 最大1.2A/ch・PWM制御 | モータードライバ |

### 首振り系（DS3218換装）

| パーツ | 仕様 | 変更点 |
|---|---|---|
| DS3218 ×2 | 20kg-cm・金属ギア・4.8〜7.2V | ⚡ SG90から換装 |
| アルミ合金製パンチルト台座 | DS3218対応 | ⚡ プラスチック台座から換装 |
| PCA9685 | I2C 0x40 | 変更なし |

### GPIO ピンアサイン（TB6612FNG）

| TB6612FNG端子 | Pi5 GPIO | 備考 |
|---|---|---|
| PWMA | GPIO12 | ハードウェアPWM0（左モーター速度） |
| AIN1 | GPIO20 | 左モーター方向1 |
| AIN2 | GPIO21 | 左モーター方向2 |
| PWMB | GPIO13 | ハードウェアPWM1（右モーター速度） |
| BIN1 | GPIO24 | 右モーター方向1 |
| BIN2 | GPIO25 | 右モーター方向2 |
| STBY | GPIO16 | LOWでスタンバイ・HIGHで動作有効 |
| VCC | 3.3V（Pin1） | ロジック電源 |
| VM | 系統B 11.1V | モーター駆動電源 |
| GND | 共通GND | 系統A・B共通接地 |

> **注**: ピンアサインは指示書で固定・変更不可。`config.yaml` の `motor:` セクションに記載する。

---

## 3. タスク分解と依存関係

```
[Task A1: EEPROM設定 (Antigravity)]
         ↓
[Task A2: 系統A確立・UPS HATテスト (Gemini)]
         ↓
[Task B: 系統B電源構築 (Gemini)] ←── 並行着手可（A1完了後）
[Task C: タンクシャーシ整備確認 (Gemini)] ←── 独立・即着手可
         ↓
[Task D: TB6612FNG配線 (Gemini)] ←── B + C 完了後
[Task E: DS3218換装 (Gemini)] ←── B 完了後
         ↓
[Task F: 統合HW検証 (Gemini)] ←── A2 + D + E 完了後
         ↓
[Task G: move_robot() 実装 (Antigravity)] ←── F 完了後（D完了でほぼ並行開始可）
         ↓
[Task H: 統合テスト (Gemini + Antigravity)]
```

### 並行着手可能なタスク

| タスク | 担当 | 前提条件 |
|---|---|---|
| Task A1: Pi5 EEPROM設定 | Antigravity | Phase 2完了のみ |
| Task C: タンクシャーシ確認・配線準備 | Gemini | Phase 2完了のみ |

### 順次タスク

| タスク | 担当 | 前提条件 |
|---|---|---|
| Task A2: UPS HAT取り付け・自律起動テスト | Gemini | **A1完了後** |
| Task B: 系統B電源構築 | Gemini | A1完了後（A2と並行可） |
| Task D: TB6612FNG配線 | Gemini | B + C 完了後 |
| Task E: DS3218換装 | Gemini | B 完了後 |
| Task F: 統合HW検証 | Gemini | A2 + D + E 完了後 |
| Task G: move_robot() 実装 | Antigravity | F 完了後（D確定で先行着手も可） |
| Task H: 統合テスト | Gemini + Antigravity | F + G 完了後 |

---

## 4. 各タスク詳細

---

### Task A1：Pi5 EEPROM設定（Antigravity）

**概要**: Raspberry Pi 5 の EEPROM に `PSU_MAX_CURRENT=5000` を設定し、UPS HAT(B)からの5A給電を安定化させる。

**背景**: Pi5 はデフォルトで USB-C 電源の最大電流を制限している。UPS HAT(B) の 5V/5A 給電を正常に認識させるため EEPROM 設定が必要。

**実装手順**:
```bash
# EEPROM設定ファイルを編集
sudo rpi-eeprom-config --edit
```

以下の行を追加または変更する:
```
PSU_MAX_CURRENT=5000
```

保存後、再起動:
```bash
sudo reboot
```

再起動後に確認:
```bash
sudo rpi-eeprom-config | grep PSU_MAX_CURRENT
# → PSU_MAX_CURRENT=5000 が表示されること
```

**完了条件**:
- `PSU_MAX_CURRENT=5000` が設定・反映されていること
- 再起動後もPi5が正常起動すること

---

### Task A2：UPS HAT(B) 取り付け・Pi5自律起動テスト（Gemini）

**前提**: Task A1（EEPROM設定）完了後

**概要**: Waveshare UPS HAT(B) を Pi5 背面の Pogo ピンに取り付け、バッテリー駆動で自律起動することを確認する。

**手順**:
1. NCR18650生セル（65mm）をUPS HAT(B)のバッテリースロットに挿入
   - **注意**: 保護回路付きセル（69mm）は物理的に入らないため使用不可
2. UPS HAT(B) を Pi5 背面の Pogo ピンに装着
3. ACアダプタを抜いた状態でPi5の電源ボタンを押して起動確認
4. `vcgencmd get_throttled` を実行し、電圧不足（throttling）が発生していないか確認
   ```bash
   vcgencmd get_throttled
   # → 0x0 が理想（非ゼロの場合は電流不足の疑い）
   ```
5. UPS HAT(B) の充電LED・残量表示が正常に機能していることを確認

**完了条件**:
- ACアダプタなしでPi5が起動すること
- `vcgencmd get_throttled` が `0x0` を返すこと
- UPS HAT(B) の状態表示が正常であること

**完了報告で記録**:
- `vcgencmd get_throttled` の出力値
- バッテリー電圧（UPS HAT表示 or テスター計測値）
- 起動成功スクリーンショットまたはterminal出力

---

### Task B：系統B電源構築（Gemini）

**前提**: Task A1完了後（A2と並行可）

**概要**: 11.1V Li-ionパックから LM2596 で 6.0V に降圧し、PCA9685 V+ 端子に供給する。1000μFコンデンサでノイズ対策を施す。GND共通接地を確立する。

**手順**:

1. **LM2596 電圧設定**
   - Li-ionパックの XT60コネクタ → LM2596 入力に接続
   - LM2596 の可変抵抗（トリマーポテンショメータ）をドライバーで調整
   - テスターで出力電圧が **6.0V（±0.1V）** になるまで調整
   - **注意**: 先にバッテリーを接続しない状態でテスト、テスターで確認してから本接続

2. **1000μFコンデンサ挿入**
   - LM2596 出力と PCA9685 V+ 端子の間のラインに 1000μF電解コンデンサを並列挿入
   - **極性注意**: プラス端子が 6Vライン、マイナス端子がGNDライン

3. **PCA9685 V+ 接続**
   - LM2596 出力（6.0V）→ PCA9685 の V+ 端子に接続
   - ※ PCA9685 の VCC（ロジック電源）は引き続き Pi5 の 3.3V（Pin1）から取得

4. **GND共通接地**
   - 系統A（UPS HAT 経由 Pi5 GND）と 系統B（Li-ionパック GND）を 共通GNDポイントで結線
   - Pi5 の GND ピン（Pin6 または任意の GND ピン）と TB6612FNG GND・PCA9685 GND を同一ポイントに接続

5. **電圧確認**
   - テスターで PCA9685 V+ 端子での電圧が 6.0V であることを確認
   - 系統A・B GND が導通していることを確認（テスター導通モード）

**完了条件**:
- LM2596 出力が 6.0V（±0.1V）
- PCA9685 V+ 端子で 6.0V を確認
- 1000μFコンデンサが正しく挿入されていること
- 系統A・B の GND が共通接地されていること

**完了報告で記録**:
- LM2596输入電圧（Li-ionパック電圧）
- LM2596 出力電圧（テスター実測値）
- PCA9685 V+端子電圧（テスター実測値）
- GND共通接地の配線状況（スケッチまたは写真）

---

### Task C：タンクシャーシ確認・モーター配線準備（Gemini）

**前提**: 独立タスク（即着手可）

**概要**: 組み上がったタンクシャーシのDCモーター配線を確認し、TB6612FNGへの接続準備を行う。

**手順**:
1. DCモーター×2の配線色・コネクタを確認しラベリング（左モーター / 右モーター）
2. モーター配線を延長ケーブル等でロボット上部まで引き出す（TB6612FNG配線スペース確保）
3. タンクシャーシにPi5・基板類を搭載できるスペースのレイアウト確認
   - Pi5（UPS HAT装着済み）の搭載位置
   - PCA9685、TB6612FNGの搭載位置
   - 11.1V Li-ionパックの搭載位置
4. 各基板を M3スペーサーまたは両面テープで仮固定

**完了条件**:
- 左右モーターの配線が識別・ラベリングされていること
- 各基板の搭載レイアウトが決まっていること

**完了報告で記録**:
- モーター配線の色と左右対応
- 搭載レイアウトのスケッチ

---

### Task D：TB6612FNG 配線（Gemini）

**前提**: Task B（系統B電源構築）+ Task C（タンクシャーシ確認）完了後

**概要**: TB6612FNG モータードライバをRaspberry Pi 5のGPIOに接続し、DCモーターと電源を配線する。

**TB6612FNG 配線仕様**:

| TB6612FNG端子 | 接続先 | 備考 |
|---|---|---|
| PWMA | GPIO12（Pin 32） | ハードウェアPWM0 |
| AIN1 | GPIO20（Pin 38） | 左モーター方向 |
| AIN2 | GPIO21（Pin 40） | 左モーター方向 |
| PWMB | GPIO13（Pin 33） | ハードウェアPWM1 |
| BIN1 | GPIO24（Pin 18） | 右モーター方向 |
| BIN2 | GPIO25（Pin 22） | 右モーター方向 |
| STBY | GPIO16（Pin 36） | HIGHで動作有効 |
| VCC | 3.3V（Pin 1） | ロジック電源 |
| VM | 系統B 11.1V | モーター駆動電源 |
| GND | 共通GND | 系統A・B共通接地済みGND |
| MOTORA+ / MOTORA- | 左DCモーター | 極性は後でソフト修正可 |
| MOTORB+ / MOTORB- | 右DCモーター | 極性は後でソフト修正可 |

**手順**:
1. TB6612FNGをジャンパーワイヤでPi5のGPIOに上表の通り接続
2. VM に 11.1V（系統B、XT60変換ケーブル経由）を接続
3. GND を共通GNDに接続
4. 左右モーター配線を MOTORA / MOTORB に接続
5. STBY を GPIO16 に接続（HIGHでスタンバイ解除）

**疎通確認**（Pi5上でシェルコマンドで実施）:
```bash
# GPIOをHIGHに設定してSTBYを解除
python3 -c "
from gpiozero import OutputDevice
stby = OutputDevice(16)
stby.on()
print('STBY HIGH: モータードライバ有効')
"
```

**完了条件**:
- 全GPIO配線が完了していること
- VM に 11.1V が供給されていること（テスター確認）
- STBY HIGH でドライバが有効になること

**完了報告で記録**:
- 全配線完了の確認（チェックリスト形式）
- VM端子電圧（テスター実測値）
- STBY 疎通確認の結果

---

### Task E：DS3218換装・アルミパンチルト台座移行（Gemini）

**前提**: Task B（系統B電源構築・6V供給確認）完了後

**概要**: 既設のSG90×2とプラスチック台座を取り外し、DS3218×2 + アルミ合金製パンチルト台座に換装する。

**手順**:
1. 現在のパン・チルト台座（SG90+プラスチック）をPCA9685から取り外し
   - ch0（パン）・ch1（チルト）コネクタを抜く
2. アルミ合金製台座を組み立て
   - DS3218をパン軸・チルト軸に取り付け
   - Webカメラを最上部に固定（既設と同様）
3. DS3218のコネクタをPCA9685の **ch0（パン）・ch1（チルト）** に接続
4. PCA9685 V+ が LM2596 の 6V 出力から供給されていることを確認
   - **重要**: DS3218はラズパイ直結NG。必ずLM2596経由6V供給であること
5. サーボホーンのセンター位置出し（90°に設定してからホーンを取り付け）
   ```bash
   python3 /home/tukapontas/gakukoma/tools/set_pan_tilt.sh 90 90
   ```
6. 手動でパン・チルトがスムーズに動くことを確認

**完了条件**:
- DS3218×2がアルミ台座に取り付けられ、Webカメラが固定されていること
- ch0/ch1コネクタが正しく接続されていること
- PCA9685 V+に 6Vが供給されていること（テスター確認）
- `set_pan_tilt.sh 90 90` でサーボが90°に動くこと

**完了報告で記録**:
- DS3218のコネクタ向き（パン: どちら向き、チルト: どちら向き）
- PCA9685 V+端子電圧（テスター実測値）
- センター位置出し確認結果
- 台座の外観写真またはスケッチ

---

### Task F：統合ハードウェア検証（Gemini）

**前提**: Task A2 + Task D + Task E 全完了後

**概要**: 全電源系統・全配線の最終確認と通電テストを行う。ソフトウェアテスト（Task G・H）に進むための最終ハードウェアGOサインを出す。

**チェックリスト**:

| 確認項目 | 確認方法 | 合格基準 |
|---|---|---|
| 系統A電圧 | テスター or UPS HAT表示 | Pi5 5V ±5% |
| 系統B電圧（LM2596出力） | テスター | 6.0V ±0.1V |
| 系統B電圧（Li-ion生電圧） | テスター | 10.5V〜12.6V（充電状態で変動） |
| GND共通接地 | テスター（導通モード） | Pi5 GND ↔ TB6612FNG GND 導通確認 |
| PCA9685 I2C | `i2cdetect -y 1` | `0x40` が表示されること |
| DS3218 ch0動作 | `set_pan_tilt.sh 90 90` → `45 90` | パンサーボが動くこと |
| DS3218 ch1動作 | `set_pan_tilt.sh 90 90` → `90 120` | チルトサーボが動くこと |
| TB6612FNG STBY | GPIO16 HIGH設定 | スタンバイ解除の確認 |

**全チェック合格 → Antigravity に `move_robot()` 実装指示を出す**

---

### Task G：`move_robot()` 実装（Antigravity）

**前提**: Task F（統合HW検証）完了後

**概要**: TB6612FNG を GPIO で制御するモーター制御スクリプトを実装し、`move_robot()` ツールとして OpenClaw に統合する。

**ディレクトリ構成**:
```
~/gakukoma/
  motor/
    tb6612_ctrl.py      # TB6612FNG制御クラス
    motor_driver.py     # 走行コマンド定義
  tools/
    move_robot.sh       # OpenClaw用ラッパー
```

**GPIO ピン定義（config.yaml に追記）**:
```yaml
motor:
  pwm_a: 12        # GPIO12 / ハードウェアPWM0（左）
  ain1: 20
  ain2: 21
  pwm_b: 13        # GPIO13 / ハードウェアPWM1（右）
  bin1: 24
  bin2: 25
  stby: 16
  pwm_frequency: 1000   # PWM周波数 (Hz)
  default_speed: 50     # デフォルト速度 (0〜100%)
```

**tb6612_ctrl.py の実装**:
```python
# gpiozero または RPi.GPIO (gpiozero推奨・Pi5対応確認済み)
# TB6612FNGのAIN1/AIN2/PWMA の組み合わせでモーター方向・速度制御
# 前進: AIN1=H / AIN2=L / PWMA=duty
# 後退: AIN1=L / AIN2=H / PWMA=duty
# ブレーキ: AIN1=H / AIN2=H
# コースト: AIN1=L / AIN2=L
# STBY=HIGH で動作有効（初期化時に必ず設定）
```

**motor_driver.py の走行コマンド**:
```python
def forward(speed=50, duration=1.0)   # 前進
def backward(speed=50, duration=1.0)  # 後退
def turn_left(speed=50, duration=0.5) # 左回転（右モーター前進・左モーター停止）
def turn_right(speed=50, duration=0.5) # 右回転（左モーター前進・右モーター停止）
def spin_left(speed=50, duration=0.5) # 左スピン（右前進・左後退）
def spin_right(speed=50, duration=0.5) # 右スピン（左前進・右後退）
def stop()                             # 停止
```

**move_robot() ツール仕様**:
- 引数: `direction`（"forward" / "backward" / "left" / "right" / "spin_left" / "spin_right" / "stop"）, `duration`（秒、デフォルト1.0）, `speed`（0〜100%、デフォルト50）
- 出力: 実行した動作と経過時間を標準出力
- シェルラッパー: `tools/move_robot.sh`

**OpenClaw 統合**:
- `TOOLS.md` に `move_robot` ツール定義を追記
- `SOUL.md` の Phase 3 能力欄を「走行可能」に更新

**注意事項**:
- gpiozero を使用すること（RPi.GPIO は Pi5 非対応）
- `__del__` を実装しないこと（進行中モーターが脱力するリスク）
- `stop()` を確実に呼ぶ終了処理を実装すること（走りっぱなし防止）

---

### Task H：統合テスト（Gemini + Antigravity）

**前提**: Task F + Task G 完了後

**テストシナリオ**:

| # | テスト | 担当 | 合格条件 |
|---|---|---|---|
| T-1 | 電源系統A確認 | Gemini | Pi5がUPS HAT駆動で起動。`vcgencmd get_throttled` が `0x0` |
| T-2 | 電源系統B確認 | Gemini | LM2596出力 6.0V。TB6612FNG VMに11.1V |
| T-3 | DS3218動作（パン） | Gemini | ch0が 0°/90°/170° に動くこと（pan_max=170に従う） |
| T-4 | DS3218動作（チルト） | Gemini | ch1が 60°/90°/180° に動くこと |
| T-5 | モーター前進単体 | Antigravity | `move_robot.sh forward 1.0` で前進1秒 |
| T-6 | モーター後退単体 | Antigravity | `move_robot.sh backward 1.0` で後退1秒 |
| T-7 | モーター左旋回 | Antigravity | `move_robot.sh left 0.5` で左旋回 |
| T-8 | モーター右旋回 | Antigravity | `move_robot.sh right 0.5` で右旋回 |
| T-9 | 停止コマンド | Antigravity | `move_robot.sh stop` で即停止 |
| T-10 | 走行+首振り同時 | Antigravity + Gemini | 走行中に `look_at_user()` が正常動作すること |
| T-11 | OpenClaw統合 | Antigravity | 「前に進んで」でmove_robot()が起動し走行すること |
| T-12 | OpenClaw統合 | Antigravity | 「右を向いて」でlook_direction()が起動し首が動くこと |
| T-13 | バッテリー駆動 | Gemini | ACアダプタ完全切断状態でT-5〜T-9が全合格 |

---

## 5. 指示書ファイル計画

プラン確認後、以下の指示書を作成する（ファイル名はWorkflowルールに従う）:

| ファイル名 | 格納先 | 担当 | 作成タイミング |
|---|---|---|---|
| `20260402_phase3_eeprom_setup_implementation.md` | `coding/` | Antigravity | 即時 |
| `20260402_phase3_ups_hat_test_implementation.md` | `hardware/` | Gemini | 即時 |
| `20260402_phase3_power_system_b_implementation.md` | `hardware/` | Gemini | 即時 |
| `20260402_phase3_chassis_prep_implementation.md` | `hardware/` | Gemini | 即時 |
| `20260402_phase3_tb6612_wiring_implementation.md` | `hardware/` | Gemini | B+C完了後 |
| `20260402_phase3_ds3218_swap_implementation.md` | `hardware/` | Gemini | B完了後 |
| `20260402_phase3_move_robot_implementation.md` | `coding/` | Antigravity | F完了後 |

---

## 6. リスクと対策

| リスク | 対策 |
|---|---|
| DS3218換装後、パン方向反転・チルト方向反転が発生する | 完了報告でコネクタ向きを記録。ソフト補正（pan_gain/tilt_gain の符号）で対応。config.yaml 修正のみで解決可能 |
| LM2596電圧が変動しDS3218が誤動作 | 1000μFコンデンサで対策済み。再現するなら出力に0.1μFセラミックコンデンサを追加（要Gemini判断） |
| TB6612FNG VM端子に11.1Vでモーターが過熱 | YP100のDCモーターは12V対応のため許容範囲内。ただしPWMデューティ50%以下で運用し、走行中の発熱を観察すること |
| GND未共通接地によるGPIO誤動作 | Task BのGND共通接地を先行して完了させる。Task D・E開始前に必ず確認 |
| gpiozero でPWM制御が不安定 | `gpiozero.PWMOutputDevice` または `RPi.GPIO`（非推奨だが緊急時）。`pigpio` デーモン経由の gpiozero を使うと安定（`GPIOZERO_PIN_FACTORY=pigpio`） |
| UPS HAT(B)がPi5で認識されない | EEPROM設定（Task A1）が未完了の可能性。`vcgencmd get_throttled` でスロットル確認 |
| タンクシャーシ搭載後の重心バランス不良 | Li-ionパックを車体中央〜後部に搭載。Pi5+基板類を中央寄りに配置 |

---

## 7. Phase 3 完了条件

- [ ] Pi5がUPS HAT(B)バッテリー単独で起動・安定動作すること
- [ ] 系統B: LM2596 6.0V出力・PCA9685 V+端子への給電確認
- [ ] DS3218×2がアルミ台座に換装され、6V給電で正常動作すること
- [ ] TB6612FNG配線完了・GPIOからモーター制御できること
- [ ] `move_robot()` ツールがOpenClaw経由で呼び出せること
- [ ] T-1〜T-13の全テストに合格すること
- [ ] SOUL.md が Phase 3 能力（走行可能）を反映していること
- [ ] 各担当者が完了報告書を提出済みであること

---

## 8. 申し送り事項（Phase 2からの引き継ぎ）

- **サーボ制御ソフトに変更不要**: DS3218はSG90と同じPWMプロトコル（50Hz / 1000〜2000μs）のため、既存の `pan_tilt.py` はそのまま使用可能。ただし換装後にカメラ向きの方向反転が発生した場合は `config.yaml` の `pan_gain` / `tilt_gain` の符号で対応。
- **pan_max=170°の制限は維持**: アルミ台座換装後もケーブル干渉リスクがあるため、Phase 2.2で設定した `pan_max=170` を維持すること。
- **GPIOライブラリは gpiozero を使用**: RPi.GPIO は Pi5 非対応（RuntimeError）。モーター制御も `gpiozero` 使用。
- **`__del__` を実装しないこと**: `pan_tilt.py` と同様、`tb6612_ctrl.py` にも `__del__` を実装してはならない（スクリプト終了時に意図しないブレーキがかかる）。代わりに `stop()` を明示的に呼ぶ設計にすること。
- **walk前にlook_center()**: `move_robot()` 実行前に首を正面向きにする動作をデフォルト動作として組み込むことを推奨（走行中の障害物確認）。
- **config.yaml パス**: `/home/tukapontas/gakukoma/voice_loop/config.yaml`。`motor:` セクションを追記すること。
- **EEPROM設定は Pi5 1台につき1回**: Task A1 は一度設定すれば永続的に有効。再実行不要。
