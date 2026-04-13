# パンチルト設定動的化 + 左向き対処 実装指示書

**依頼者**: ClaudeCode
**担当**: Antigravity
**日付**: 2026-03-18
**関連フェーズ**: Phase 2.2（Gemini診断結果を受けた修正）

---

## 背景・目的

Geminiによる実機診断（`research/20260318_pantilt_diagnosis_completed.md`）で以下の3問題が判明しました。

1. **pan=180°でI2Cが断線**: 配線が引っ張られSDA/SCLが接触不良になる。ソフトウェアでパン上限を制限する必要あり。
2. **チルト範囲がコード内にハードコード**: `pan_tilt.py` 内の `60`〜`120` を `config.yaml` から動的に読み込む必要あり。
3. **サーボホーンが約45°ズレ**: pan=90°の時点で正面より右にズレている。ソフトウェアオフセット補正を追加。

---

## タスク一覧

### タスクD-1: config.yaml にパンチルト範囲・オフセットを追加

ファイル: `/home/tukapontas/gakukoma/config.yaml`（既存ファイルに追記）

`servo` または `pan_tilt` 関連のセクションに以下を追加してください（既存キーがあれば更新）:

```yaml
pan_tilt:
  pan_min: 10        # パン最小角度（左端。0°はギリギリすぎるため余裕を持たせる）
  pan_max: 170       # パン最大角度（右端。180°はI2C断線リスクがあるため制限）
  pan_offset: 0      # パン物理オフセット補正（正=右方向に補正、負=左方向に補正）
                     # ※ホーンのズレが確認された場合にユーザーが調整。初期値は0。
  tilt_min: 60       # チルト最小角度（上方向限界。現在はソフトのみ確認済み）
  tilt_max: 120      # チルト最大角度（下方向限界。現在はソフトのみ確認済み）
```

---

### タスクD-2: pan_tilt.py のハードコードをconfig.yamlから読み込みに変更

ファイル: `/home/tukapontas/gakukoma/servo/pan_tilt.py`

**変更内容:**

1. クラス初期化時に `config.yaml` からパンチルト設定を読み込む。
   - `pan_min`, `pan_max`, `pan_offset`, `tilt_min`, `tilt_max` を読み込む。
   - config.yamlに値が存在しない場合は現在のデフォルト値（60/120等）にフォールバック。

2. `set_pan()` メソッドに以下を適用:
   - 入力角度を `pan_offset` で補正（`adjusted_angle = angle + pan_offset`）
   - 補正後の角度を `pan_min`〜`pan_max` の範囲にクランプ

3. `set_tilt()` メソッドに以下を適用:
   - 入力角度を `tilt_min`〜`tilt_max` の範囲にクランプ（現在のハードコードを置き換え）

4. `look_direction()` の `"left"` ディレクティブに対応する角度（現在おそらく180°）を `pan_max` の値に変更する。
   - 具体的には `left` → `self.pan_max`（config.yamlで170°に設定済み）

**実装の注意事項:**
- `pan_offset` はサーボの物理的なズレを補正するためのもの。初期値0で動作し、ユーザーが実機確認後に手動調整する想定。
- 既存のコードが `pan_tilt.yaml` または `config.yaml` を既に読んでいる場合は、その読み込み処理に乗せる形で実装してください。

---

### タスクD-3: I2Cエラーハンドリングの追加

ファイル: `/home/tukapontas/gakukoma/servo/pan_tilt.py`

**変更内容:**

`set_pan()` および `set_tilt()` のサーボ制御部分を `try/except` で囲み、I2Cエラー（`OSError`）が発生した場合は以下を行う:

```python
except OSError as e:
    return f"サーボ制御エラー: I2C通信失敗 ({e}). i2cdetect -y 1 で配線を確認してください。"
```

**目的**: 万が一 pan_max を超えた操作が発生した際や配線の接触不良時に、プロセスがクラッシュせず診断情報を返せるようにする。

---

## テスト要件

| ID | テスト内容 | 合格条件 |
|---|---|---|
| T-1 | `set_pan_tilt 180 90` を実行 | pan=170°でクランプされI2Cエラーが発生しない |
| T-2 | `look_direction left` を実行 | pan=170°（または設定値）で正常動作・I2Cエラーなし |
| T-3 | `set_pan_tilt 90 50` を実行 | tilt=60°でクランプされる（ログ確認） |
| T-4 | `set_pan_tilt 90 130` を実行 | tilt=120°でクランプされる（ログ確認） |
| T-5 | config.yaml の `pan_max` を 150 に変更 → `look_direction left` | pan=150°にクランプされることを確認 |
| T-6 | config.yaml の `pan_offset` を -10 に変更 → `set_pan_tilt 90 90` | pan=80°に補正されることを確認 |

テスト後は config.yaml を元の値（pan_max=170, pan_offset=0）に戻してください。

---

## 完了報告

完了報告書は `/home/tukapontas/a2a/coding/20260318_pantilt_config_fix_completed.md` に作成してください。

報告書に含めてほしい内容:
1. 各タスクの実施結果
2. config.yaml の最終的なパンチルト設定値（反映済みの値）
3. テスト結果（T-1〜T-6）
4. 未実施事項（あれば理由）
5. `pan_offset` の実調整が必要かどうかの所見（現在の物理状態の観察）

---

## ユーザーへの申し送り（Antigravityからではなく、ClaudeCodeからユーザーへ）

> **ハードウェア確認依頼（Geminiより）**: がくこまが左に首を振る際（pan=180°方向）、ジャンパーワイヤに「ゆとり」があるか目視で確認してください。ワイヤが台座に引っ張られている場合は、ゆとりを持たせた配線に修正することで根本解決できます。ソフトウェアでのpan_max=170°制限は暫定対処です。
