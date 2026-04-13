# 指示書：パンチルト設定動的化 T-1〜T-6 テスト再実施

**作成日:** 2026-03-19
**作成者:** ClaudeCode（司令塔）
**担当:** Antigravity
**優先度:** 高（Phase 2.2 完了ブロッカー）

---

## 背景・目的

2026-03-18 に `coding/20260318_pantilt_config_fix_completed.md` として実装完了済みだが、T-1テストにてI2Cバススタックが原因のハングが発生し、⚠️保留状態となっていた。

2026-03-19 にGemini担当で **PCA9685電源リセット・配線ゆとり確保** が完了（`hardware/20260319_i2c_recovery_wiring_fix_completed.md`）。
以下を確認済み：
- `i2cdetect -y 1` にて `0x40` / `0x70` 正常応答
- `set_pan_tilt.sh 90 90` がハングせず成功
- `look_direction.sh left` が配線ストレスなく成功
- `180 90` 指定時に `pan=170°` クランプが機能

ハードウェア側のハング要因は **完全に排除された**。
本指示書は、保留中テスト（T-1〜T-6）の再実施と、タスク完了確認のみを依頼する。

---

## 作業内容

### 前提確認（作業前）

```bash
# I2Cバスが正常であることを確認
i2cdetect -y 1
# → 0x40 (PCA9685) と 0x70 (All Call) が表示されること

# ロックファイルの残滓がないことを確認
ls /tmp/gakukoma_servo.lock 2>/dev/null && echo "LOCK EXISTS" || echo "CLEAN"
# → CLEAN であること（残っていれば削除）
```

### テスト再実施（T-1〜T-6）

以下のテストを **番号順に実施**すること。T-1が合格しない場合は後続テストを実施しないこと。

| ID | コマンド | 期待結果 |
|---|---|---|
| T-1 | `bash /home/tukapontas/gakukoma/pan_tilt/set_pan_tilt.sh 180 90` | **ハングしない**。出力に `pan=170°`（クランプ）が確認できること |
| T-2 | `bash /home/tukapontas/gakukoma/pan_tilt/look_direction.sh left` | ハングしない。左向きにサーボが動作すること |
| T-3 | `bash /home/tukapontas/gakukoma/pan_tilt/set_pan_tilt.sh 90 50` | ハングしない。出力に `tilt=60°`（クランプ）が確認できること |
| T-4 | `bash /home/tukapontas/gakukoma/pan_tilt/set_pan_tilt.sh 90 130` | ハングしない。出力に `tilt=120°`（クランプ）が確認できること |
| T-5 | config.yamlの `pan_max` を `160` に変更 → `set_pan_tilt.sh 180 90` 実行 → `160` でクランプされること → テスト後 `170` に戻す | 動的設定が反映されること |
| T-6 | config.yamlの `pan_offset` を `5` に変更 → `set_pan_tilt.sh 90 90` 実行 → 物理的に `95°` 相当に動くこと → テスト後 `0` に戻す | オフセット補正が機能すること |

---

## 完了条件

- T-1〜T-6 全テスト合格
- config.yamlが最終値（`pan_max: 170`, `pan_offset: 0`）に戻っていること

---

## 完了報告書

`coding/20260319_pantilt_config_retest_completed.md` として作成・保存すること。

報告書には以下を含めること：
- T-1〜T-6 各テストの実際の出力と合否
- 発生した問題があれば対処内容
- 次担当者（ClaudeCode）への申し送り
