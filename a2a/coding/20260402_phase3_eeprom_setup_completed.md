# Phase 3 Task A1: Pi5 EEPROM設定 完了報告書

**完了日:** 2026-04-06
**実施者:** Antigravity

## 実施内容

Raspberry Pi 5 の EEPROM に `PSU_MAX_CURRENT=5000` を設定し、Waveshare UPS HAT(B) からの 5V/5A 給電を安定認識させるための設定を行いました。

### 1. 現在のEEPROM設定確認
設定前の状態を確認し、`PSU_MAX_CURRENT` が未設定であることを確認しました。

### 2. EEPROM設定の更新
`/tmp/config.txt` を介して `PSU_MAX_CURRENT=5000` を追加し、`sudo rpi-eeprom-config --apply` にて適用しました。

### 3. 再起動
`sudo reboot` を実行し、システムを再起動しました。

### 4. 設定反映の確認
再起動後、設定が正しく反映されていることを確認しました。

**確認コマンド:**
```bash
sudo rpi-eeprom-config | grep PSU_MAX_CURRENT
```

**出力結果:**
```
PSU_MAX_CURRENT=5000
```

## 完了条件の確認

- [x] `PSU_MAX_CURRENT=5000` が設定・反映されていること
- [x] 再起動後も Pi5 が正常起動すること
- [x] 上記 grep コマンドで値が確認できること

## 次のステップへの申し送り

- UPS HAT(B) からの 5V/5A 給電が Pi5 本体によって上限 5A として認識されるようになりました。
- これにより、Task A2（UPS HAT取り付けテスト）の開始準備が整いました。
