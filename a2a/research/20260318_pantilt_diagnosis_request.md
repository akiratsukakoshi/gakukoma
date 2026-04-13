# パンチルト実機診断依頼

**依頼者**: ClaudeCode
**担当**: Gemini
**日付**: 2026-03-18
**関連フェーズ**: Phase 2.1 → Phase 2.2 改修前診断

---

## 目的

現在のパンチルト制御に2つの問題が報告されています。改修方針を確定するため、実機での診断結果を報告してください。

---

## 診断項目

### 診断A: 左向き失敗（I2C初期化エラー）の再現確認

#### 準備
```bash
# I2Cデバイス検出（PCA9685が0x40で見えるか確認）
i2cdetect -y 1
```
→ `0x40` が表示されることを確認してください。

#### 診断手順

1. **正面（front）に向ける**
   ```bash
   /home/tukapontas/gakukoma/tools/look_direction.sh front
   ```
   → 結果を記録

2. **右向きに向ける**
   ```bash
   /home/tukapontas/gakukoma/tools/look_direction.sh right
   ```
   → 結果を記録

3. **左向きに向ける（問題の操作）**
   ```bash
   /home/tukapontas/gakukoma/tools/look_direction.sh left
   ```
   → 結果を記録。失敗した場合は**エラーメッセージ全文**を記録

4. **3を5回繰り返し**、成功回数と失敗パターンを記録

5. **左向き失敗時、すぐにi2cdetect**
   ```bash
   i2cdetect -y 1
   ```
   → 0x40が消えているか？

#### 報告してほしいこと
- 5回中何回成功したか
- 失敗時のエラーメッセージ
- 失敗直後のi2cdetect結果（0x40の有無）
- 右向きは安定して成功するか

---

### 診断B: チルト（上下）の実際の機構的限界値の確認

現在の設定は `tilt_min: 60`（上限）、`tilt_max: 120`（下限）です。実際の機械的な限界を調べてください。

#### 診断手順（上方向）

以下のコマンドで角度を徐々に下げて、物理的に無理のある角度を特定してください。
サーボが異音（ガガガ）を出したり、台座が当たる手前の角度を「機構的限界」とします。

```bash
# tilt=60（現在の上限）
/home/tukapontas/gakukoma/tools/set_pan_tilt.sh 90 60
# 問題なければ次へ

/home/tukapontas/gakukoma/tools/set_pan_tilt.sh 90 55
/home/tukapontas/gakukoma/tools/set_pan_tilt.sh 90 50
/home/tukapontas/gakukoma/tools/set_pan_tilt.sh 90 45
# 以降、異音が出る直前の角度を記録
```

#### 診断手順（下方向）

```bash
# tilt=120（現在の下限）
/home/tukapontas/gakukoma/tools/set_pan_tilt.sh 90 120
# 問題なければ次へ

/home/tukapontas/gakukoma/tools/set_pan_tilt.sh 90 125
/home/tukapontas/gakukoma/tools/set_pan_tilt.sh 90 130
/home/tukapontas/gakukoma/tools/set_pan_tilt.sh 90 135
# 以降、異音が出る直前の角度を記録
```

#### 報告してほしいこと
- 上方向：異音・当たりが出ない安全な最小角度（例: 「50°まで問題なし、45°でガガガ」）
- 下方向：異音・当たりが出ない安全な最大角度
- 診断後は必ず正面に戻す: `/home/tukapontas/gakukoma/tools/look_direction.sh front`

---

### 診断C: パン（左右）の限界確認（任意）

同様に左右方向の限界も確認できれば報告してください。
- 現在の設定: `pan_min: 0`（右端）、`pan_max: 180`（左端）
- 左: pan=135、右: pan=45 が定義済み
- 実際に0°や180°まで動かして機構的な干渉がないか

---

## 完了報告

完了報告書は `/home/tukapontas/a2a/research/20260318_pantilt_diagnosis_completed.md` に作成してください。

報告書に含めてほしい内容：
1. 診断A結果（左向きエラーの再現率・エラーメッセージ・i2cdetect結果）
2. 診断B結果（tilt安全範囲: min=?°, max=?°）
3. 診断C結果（可能なら）
4. 気になった点・推察されるハードウェア原因があれば

これによってAntigravityへの実装指示書（config.yaml修正値）を確定します。
