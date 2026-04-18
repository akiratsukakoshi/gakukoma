# Phase 3 Task D 補足：TB6612FNG AIN2 ピン変更対応

**作成日:** 2026-04-16
**作成者:** ClaudeCode（司令塔）
**担当:** Gemini
**前提条件:** Task D 配線作業の途中（AIN2以外の全配線完了済み）

---

## 問題

元の指示書（`20260402_phase3_tb6612_wiring_implementation.md`）では AIN2 を **Pin 40 (GPIO 21)** に割り当てていたが、このピンはスピーカーアンプ（MAX98357A）の I2S DIN として Phase 1 で使用済みであることが判明した。

```
青: DIN ↔ Pi 40番ピン (GPIO 21)  ← アンプがここを使用中
```

---

## 対応方針

AIN2 の接続先を **Pin 37 (GPIO 26)** に変更する。

- GPIO 26 は現在どの機能でも未使用
- AIN2 はデジタル出力（HIGH/LOW）なので、任意の汎用 GPIO ピンで代替可能
- ハードウェア PWM 不要（PWM が必要なのは PWMA/PWMB のみ）
- ソフトウェア（move_robot.py）は Task G で新規実装のため、今の段階でピン番号を変更しても問題なし

---

## 変更後の GPIO アサイン（AIN2のみ変更）

| TB6612FNG端子 | 接続先 | Pi5 ピン番号 | 変更 |
|---|---|---|---|
| PWMA | GPIO12 | Pin 32 | 変更なし |
| AIN1 | GPIO20 | Pin 38 | 変更なし |
| **AIN2** | **GPIO26** | **Pin 37** | **★変更** |
| PWMB | GPIO13 | Pin 33 | 変更なし |
| BIN1 | GPIO24 | Pin 18 | 変更なし |
| BIN2 | GPIO25 | Pin 22 | 変更なし |
| STBY | GPIO16 | Pin 36 | 変更なし |

---

## 参考：Pi5 40ピン配置（変更ポイント周辺）

```
Pin 35 (GPIO 19, LRC) ─── アンプ黄
Pin 36 (GPIO 16) ────────── STBY ← 配線済み
Pin 37 (GPIO 26) ────────── ★ここに AIN2 を接続
Pin 38 (GPIO 20) ────────── AIN1 ← 配線済み
Pin 39 (GND)
Pin 40 (GPIO 21, DIN) ───── アンプ青（使用中・接続しない）
```

---

## 作業手順

### Step 1: AIN2 ジャンパーワイヤの接続

TB6612FNG の **AIN2** 端子から **Pi5 の Pin 37** にジャンパーワイヤを接続する。

- Pin 37 は STBY（Pin 36）の隣なので位置を確認してから挿す
- 誤って Pin 38（AIN1 接続済み）や Pin 39（GND）と混同しないよう注意

### Step 2: 疎通確認

元指示書の Step 5（STBY 疎通確認スクリプト）をそのまま実行してよい。AIN2 の論理確認は Task H（走行テスト）で行う。

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

---

## 完了条件

- [ ] AIN2 を Pin 37 (GPIO 26) に接続済み
- [ ] Pin 40 にはアンプ配線のみが接続されていること（TB6612FNG の配線はない）
- [ ] STBY 疎通確認スクリプトがエラーなく動作すること

---

## 完了報告書の作成

`hardware/20260402_phase3_tb6612_wiring_completed.md` に以下を追記すること:

- AIN2 ピン変更の事実（元：Pin40/GPIO21 → 変更後：Pin37/GPIO26）
- 変更理由（Pin40はMAX98357A DINで使用中）
- STBY 疎通確認の出力
- VM 端子電圧（テスター実測値）
- 全完了条件のチェックリスト
