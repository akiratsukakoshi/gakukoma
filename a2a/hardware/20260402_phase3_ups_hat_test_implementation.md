# Phase 3 Task A2：UPS HAT(B) Pi5 自律起動テスト

**作成日:** 2026-04-02
**作成者:** ClaudeCode（司令塔）
**担当:** Gemini
**前提条件:** Task A1（EEPROM設定）完了後

---

## 目的

Waveshare UPS HAT(B) + NCR18650生セル×2 を Pi5 に取り付け、ACアダプタなしでの自律起動を確認する。これが系統A（脳用電源）の確立となる。

---

## 使用パーツ

| パーツ | 仕様 | 注意 |
|---|---|---|
| Waveshare UPS HAT(B) | Pi5対応 Pogo ピン給電 | GPIO を塞がないモデル |
| GASLIKE NCR 18650生セル | 65mm（保護回路なし） | **69mm保護回路付きは物理的に入らない・使用不可** |

---

## 手順

### Step 1: バッテリー挿入

1. NCR18650生セルの極性（+/-）をUPS HAT(B)のスロット表示に合わせて挿入
2. セルが2本ともしっかり入っていることを確認
3. **バッテリーの残量を事前にテスターで確認**（1本あたり 3.0V以上あること）

### Step 2: UPS HAT(B) 取り付け

1. Pi5 を完全にシャットダウン・電源オフにした状態で作業
2. UPS HAT(B) を Pi5 背面の Pogo ピンに位置合わせして装着
3. ネジ（付属のスペーサーとネジ）で固定

### Step 3: 自律起動テスト

1. ACアダプタを **接続しない** 状態で Pi5 の電源ボタンを押す
2. Pi5 が起動することを確認
3. SSH または直接接続で Pi5 にログインする

### Step 4: 電圧・スロットリング確認

ログイン後に以下を実行:

```bash
# スロットリング確認（0x0が正常）
vcgencmd get_throttled

# CPU温度・電圧確認
vcgencmd measure_volts core
vcgencmd measure_temp
```

**合格基準:**
- `throttled=0x0`（非ゼロの場合は電流不足の疑い）
- `volt=` が 0.8V 以上（コア電圧）

### Step 5: 充電動作確認（ACアダプタ接続）

ACアダプタを接続し:

1. UPS HAT(B) の充電LED が点灯していることを確認
2. 充電中に Pi5 が引き続き動作していることを確認（電源切断されないこと）

---

## 完了条件

- [ ] ACアダプタなしで Pi5 が起動すること
- [ ] `vcgencmd get_throttled` が `0x0` を返すこと
- [ ] ACアダプタ接続時に充電LEDが点灯すること

---

## 完了報告書の作成

完了後、`hardware/20260402_phase3_ups_hat_test_completed.md` を作成し、以下を記録すること:

- `vcgencmd get_throttled` の出力
- `vcgencmd measure_volts core` の出力
- バッテリー電圧（挿入前のテスター実測値）
- 充電LED動作確認の有無
- 特記事項（問題があれば詳細）
