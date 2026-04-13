# Phase 3 Task D：TB6612FNG 配線

**作成日:** 2026-04-02
**作成者:** ClaudeCode（司令塔）
**担当:** Gemini
**前提条件:** Task B（系統B電源構築）+ Task C（シャーシ確認）完了後

---

## 目的

TB6612FNG モータードライバを Raspberry Pi 5 の GPIO に接続し、DCモーターと系統B電源（11.1V）を配線する。この完了後、Antigravity が `move_robot()` の実装に着手できる。

---

## GPIO ピンアサイン（変更不可・固定定義）

| TB6612FNG端子 | 接続先 | Pi5 ピン番号 | 備考 |
|---|---|---|---|
| PWMA | GPIO12 | Pin 32 | ハードウェアPWM0（左モーター速度） |
| AIN1 | GPIO20 | Pin 38 | 左モーター方向1 |
| AIN2 | GPIO21 | Pin 40 | 左モーター方向2 |
| PWMB | GPIO13 | Pin 33 | ハードウェアPWM1（右モーター速度） |
| BIN1 | GPIO24 | Pin 18 | 右モーター方向1 |
| BIN2 | GPIO25 | Pin 22 | 右モーター方向2 |
| STBY | GPIO16 | Pin 36 | LOW=スタンバイ / HIGH=動作有効 |
| VCC | 3.3V | Pin 1 | ロジック電源 |
| GND | 共通GND | ブレッドボード GND レール | Task B で Pi5 Pin 20 ↔ ブレッドボード GND レールとして確立済み |
| VM | 系統B 11.1V | - | Li-ionパックから直結（XT60変換ケーブル経由） |
| MOTORA+/MOTORA- | 左DCモーター | - | Task C でラベリング済みの左モーター配線 |
| MOTORB+/MOTORB- | 右DCモーター | - | Task C でラベリング済みの右モーター配線 |

> **注意**: 左右モーターの極性は、走行テスト（Task H）時にソフトウェア側で補正可能。ここでは物理的に接続するだけでよい。

---

## 手順

### Step 1: GPIO配線（Pi5 ↔ TB6612FNG）

ジャンパーワイヤ（メス-メス または オス-メス）を使用して上表の通り配線する。

配線時のコツ:
- Pi5 の GPIO 番号と物理ピン番号を混同しないこと（上表は両方記載済み）
- ジャンパーワイヤに色のルールをつけると後のデバッグが楽（例: 赤=電源, 黒=GND, 色付き=信号）

### Step 2: VCC（ロジック電源）接続

TB6612FNG の VCC 端子を Pi5 の **3.3V（Pin 1）** に接続する。

> **注意**: VCC は必ず 3.3V に接続。5V は TB6612FNG のロジック電圧範囲外になる場合がある。

### Step 3: VM（モーター電源）接続

1. Li-ionパック → XT60変換ケーブル → TB6612FNG VM 端子 に接続
2. **VM は系統B の 11.1V を直結**（LM2596を通さない）
3. GND は Task B で構築済みの共通GND ポイントに接続

### Step 4: DCモーター接続

- Task C でラベリングした左モーター配線 → TB6612FNG MOTORA（+/-）
- Task C でラベリングした右モーター配線 → TB6612FNG MOTORB（+/-）

### Step 5: 疎通確認

Pi5 からシェルコマンドで STBY を HIGH にしてドライバを有効化する:

```bash
python3 -c "
from gpiozero import OutputDevice
import time
stby = OutputDevice(16)
stby.on()
print('STBY HIGH: モータードライバ有効')
time.sleep(1)
stby.off()
print('STBY LOW: スタンバイ')
"
```

エラーなく実行されれば GPIO 接続は正常。

### Step 6: VM 電圧確認

テスターで TB6612FNG VM 端子の電圧を確認:
- **期待値**: Li-ionパック電圧（10.5〜12.6V）

---

## 完了条件

- [ ] 全 GPIO 配線（7本: PWMA/AIN1/AIN2/PWMB/BIN1/BIN2/STBY）が完了
- [ ] VCC に 3.3V が供給されていること
- [ ] VM に 11.1V（系統B）が供給されていること（テスター確認）
- [ ] GND が共通接地ポイントに接続されていること
- [ ] 左右DCモーターが接続されていること
- [ ] STBY 疎通確認スクリプトがエラーなく動作すること

---

## 完了報告書の作成

完了後、`hardware/20260402_phase3_tb6612_wiring_completed.md` を作成し、以下を記録すること:

- 全配線完了のチェックリスト（上記完了条件を転記）
- VM 端子電圧（テスター実測値）
- STBY 疎通確認の出力
- 左右モーターの MOTORA/MOTORB への接続対応（左=A, 右=B など）
- 特記事項
