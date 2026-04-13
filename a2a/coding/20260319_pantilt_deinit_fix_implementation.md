# 指示書：pca.deinit() によるI2Cバス切断の完全修正

**担当**: Antigravity
**日付**: 2026-03-19
**優先度**: 緊急（前回修正後も0x70消失が継続）

---

## 背景・原因

前回の修正（`look_direction`/`set_pan_tilt` 内の `release()` 削除）後も 0x70 消失が継続している。
原因は以下の2点。

### 原因①：`PanTiltController.__del__` がスクリプト終了のたびに `deinit()` を呼ぶ

`set_pan_tilt.sh` は毎回 Python プロセスを起動・終了する。
プロセス終了時に `__del__` → `release()` → `pca.deinit()` が自動実行され、I2Cバスが切断される。

### 原因②：`look_at_user.py` の `finally` ブロックに `pt.release()` が残っている（120行目）

```python
finally:
    pt.release()   # ← deinit() が走る
    cam.release()
    pt._lock.release()
```

### 根本原因：`pca9685_ctrl.py` の `release()` で `pca.deinit()` を呼んでいる

SG90サーボはPWM信号が継続している間だけトルクを発生させる。
`deinit()` でI2Cを切断すると PCA9685 が停止し、0x70（All Callアドレス）も消える。
次の `i2cdetect` で 0x70 が見えなくなり、以後の I2C 操作が失敗する。

---

## 修正対象ファイル

1. `/home/tukapontas/gakukoma/servo/pca9685_ctrl.py`
2. `/home/tukapontas/gakukoma/servo/pan_tilt.py`
3. `/home/tukapontas/gakukoma/look_at_user.py`

---

## 修正内容

### 1. `pca9685_ctrl.py` の `release()` から `deinit()` を削除

**修正前：**
```python
def release(self):
    """リソース解放（サーボ脱力・I2C切断）"""
    try:
        for ch in range(16):
            self.pca.channels[ch].duty_cycle = 0
        self.pca.deinit()
    except:
        pass
```

**修正後：**
```python
def release(self):
    """PWMを停止してサーボを脱力（I2Cバスは維持）"""
    try:
        for ch in range(16):
            self.pca.channels[ch].duty_cycle = 0
    except:
        pass
```

`deinit()` を削除する。I2Cバスを切断する必要はない。

### 2. `pan_tilt.py` の `__del__` を削除

**修正前：**
```python
def __del__(self):
    try:
        self.release()
    except Exception:
        pass
```

**修正後：** この `__del__` メソッドを丸ごと削除する。

理由：`__del__` は Python の GC タイミングで呼ばれるため制御できない。
スクリプト型の短命プロセスでは毎回終了時に `release()` が走ってしまう。

### 3. `look_at_user.py` の `finally` ブロックから `pt.release()` を削除

**修正前（118〜122行目）：**
```python
finally:
    # リソース解放
    pt.release()
    cam.release()
    pt._lock.release()
```

**修正後：**
```python
finally:
    cam.release()
    pt._lock.release()
```

---

## テスト手順

**前提：** テスト前に `i2cdetect -y 1` で 0x40 と 0x70 が両方見えていることを確認する。
（見えていなければ再起動して復旧してからテスト開始）

### T-A：コマンド後も 0x70 が残ること
```bash
bash tools/set_pan_tilt.sh 45 90
i2cdetect -y 1
# → 0x40 と 0x70 が両方表示されること ← これが今回の核心テスト
```

### T-B：パン物理動作確認
```bash
bash tools/set_pan_tilt.sh 45 90
# → サーボが右方向に物理動作すること
bash tools/set_pan_tilt.sh 135 90
# → サーボが左方向に物理動作すること
bash tools/set_pan_tilt.sh 90 90
# → サーボが正面に戻ること
```

### T-C：look_direction 物理動作確認
```bash
bash tools/look_direction.sh right
bash tools/look_direction.sh left
bash tools/look_direction.sh front
# → それぞれ右・左・正面に物理動作し、0x70が消えないこと
```

### T-D：連続実行後の I2C 安定性
```bash
for i in $(seq 1 10); do bash tools/set_pan_tilt.sh 45 90; bash tools/set_pan_tilt.sh 135 90; done
i2cdetect -y 1
# → 0x40 と 0x70 が両方残っていること
```

### T-E：チルト物理動作確認
```bash
bash tools/set_pan_tilt.sh 90 70
bash tools/set_pan_tilt.sh 90 110
# → チルトが上下に物理動作すること（チルトの物理動作を今回初めて確認）
```

---

## 完了報告書

`coding/20260319_pantilt_deinit_fix_completed.md` を作成して報告してください。
T-A〜T-E 各テストの合否と、物理動作（パン・チルト両方）の確認結果を必ず記載すること。
