# Phase 3 Task A1：Pi5 EEPROM設定

**作成日:** 2026-04-02
**作成者:** ClaudeCode（司令塔）
**担当:** Antigravity
**前提条件:** なし（即着手可）

---

## 目的

Raspberry Pi 5 の EEPROM に `PSU_MAX_CURRENT=5000` を設定し、Waveshare UPS HAT(B) からの 5V/5A 給電を安定認識させる。この設定が完了するまで Gemini の UPS HAT 自律起動テスト（Task A2）は開始しない。

---

## 実装手順

### Step 1: 現在のEEPROM設定確認

```bash
sudo rpi-eeprom-config
```

出力に `PSU_MAX_CURRENT` が含まれているか確認する。

### Step 2: EEPROM設定を編集

```bash
sudo rpi-eeprom-config --edit
```

エディタが開くので、以下の行を追加する（既存行がある場合は値を変更）:

```
PSU_MAX_CURRENT=5000
```

保存して終了する（nano の場合は Ctrl+X → Y → Enter）。

### Step 3: 再起動

```bash
sudo reboot
```

### Step 4: 設定反映の確認

再起動後:

```bash
sudo rpi-eeprom-config | grep PSU_MAX_CURRENT
```

**期待出力:**
```
PSU_MAX_CURRENT=5000
```

---

## 完了条件

- [x] `PSU_MAX_CURRENT=5000` が設定・反映されていること
- [x] 再起動後も Pi5 が正常起動すること
- [x] 上記 grep コマンドで値が確認できること

---

## 完了報告書の作成

完了後、`coding/20260402_phase3_eeprom_setup_completed.md` を作成し、以下を記録すること:

- `sudo rpi-eeprom-config | grep PSU_MAX_CURRENT` の出力
- 再起動後の正常起動確認

---

## 申し送り

- この設定は Pi5 本体に永続保存される。再実行不要。
- 完了報告を受けた後、ClaudeCode から Gemini に Task A2（UPS HAT取り付けテスト）の開始指示を出す。
