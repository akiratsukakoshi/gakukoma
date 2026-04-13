# 指示書: ジェスチャー修正（Thinking動作スロー化 + Listening移行時停止）

**作成日**: 2026-04-11
**担当**: Antigravity
**優先度**: 高（実機テストでバグ確認済み）

---

## 背景・経緯

実機テストでT-1〜T-4はOK。以下2点の修正が必要：

1. **thinkingジェスチャーが小刻み過ぎる** → 「じっくり考えている」描写に変更したい
2. **発話を聞き取れずlistening遷移するとき、ジェスチャーが止まらないループが発生した**
   （サーボ音を拾う → thinking → 認識失敗 → listening → またサーボ音... の悪循環）

---

## 修正1: `gesture_controller.py` — thinkingパターン再設計

### ファイル
`/home/tukapontas/gakukoma/servo/gesture_controller.py`

### 変更内容

**現状**: `_THINKING_PATTERN` は8点の微小揺れ（±5°）を0.5秒刻みでループ。小刻みすぎる。

**変更後**: 右斜め上 2.5秒 → 左斜め上 2.5秒 → 右下 2秒 のゆったりしたループにする。

#### `_THINKING_PATTERN` を削除して `_THINKING_SEQUENCE` に置き換える

```python
# (pan, tilt, hold_sec) の3タプル
_THINKING_SEQUENCE = [
    (115, 72, 2.5),   # 右斜め上（ゆっくり視線を上右へ）
    (65,  72, 2.5),   # 左斜め上（ゆっくり視線を上左へ）
    (115, 108, 2.0),  # 右下（考え込む）
]
```

#### `_run_thinking()` を書き換える

```python
def _run_thinking(self, stop_event):
    """シンキングジェスチャーのバックグラウンドスレッド（ゆったりした動き）"""
    idx = 0
    while not stop_event.is_set():
        pan, tilt, hold_sec = self._THINKING_SEQUENCE[idx % len(self._THINKING_SEQUENCE)]
        self._pt.set_pan_tilt(pan, tilt)
        idx += 1
        # hold_sec 秒間、0.1秒ごとに stop_event を確認しながら保持
        steps = int(hold_sec / 0.1)
        for _ in range(steps):
            if stop_event.is_set():
                return
            time.sleep(0.1)
```

#### 旧 `_THINKING_PATTERN` リストは完全削除する

---

## 修正2: `voice_loop.py` — listening遷移時にジェスチャーを止める

### ファイル
`/home/tukapontas/gakukoma/voice_loop/voice_loop.py`

### 変更内容

**問題のある箇所（現在の `run()` メソッド内、L347〜358あたり）**:

```python
if not text:
    print("（認識不能な音声）")
    self._consecutive_failures = getattr(self, '_consecutive_failures', 0) + 1
    if self._consecutive_failures >= 3:
        print("連続認識失敗3回 → IDLEに戻ります")
        self._consecutive_failures = 0
        self.state = "idle"
        self.led.set_state("idle")
    else:
        self.state = "listening"
        self.led.set_state("listening")
    continue  # ← ここでジェスチャーが止まらないまま次ループへ
```

**修正後**: `not text` ブロックの先頭にジェスチャー停止を追加する。

```python
if not text:
    print("（認識不能な音声）")
    # listening に戻るときは必ずジェスチャーを停止する
    if self._gesture:
        self._gesture.stop()
    self._consecutive_failures = getattr(self, '_consecutive_failures', 0) + 1
    if self._consecutive_failures >= 3:
        print("連続認識失敗3回 → IDLEに戻ります")
        self._consecutive_failures = 0
        self.state = "idle"
        self.led.set_state("idle")
    else:
        self.state = "listening"
        self.led.set_state("listening")
    continue
```

**注意**: `go_center()` ではなく `stop()` を使う。`go_center()` は `look_center()` を呼んで正面に向かせるが、listenig中に首をガチッと動かすのは不自然。`stop()` でジェスチャースレッドだけ終了し、現在位置に留まらせるのが自然。

---

## 完了条件・テスト

| テストID | 内容 | 期待結果 |
|---|---|---|
| T-1 | thinking状態を目視確認 | 右斜め上→左斜め上→右下 のゆったりした動き（各2〜3秒） |
| T-2 | 発話不明瞭を意図的に発生させる（小声で「あー」など） | thinkingジェスチャーが停止し、静止したままlistening状態に戻る |
| T-3 | 上記を連続3回 → IDLEに戻ることを確認 | ジェスチャーが動き続けるループに入らない |
| T-4 | 通常会話（thinking→speaking→listening） | 従来通り正常動作すること |

---

## 恒久注意事項の確認（変更不要・念のため）

- `PanTiltController.release()` を `GestureController` 内から呼び出してはならない
- `PanTiltController.__del__` を追加してはならない
- ジェスチャースレッドは引き続き `daemon=True`

---

## 完了報告書

完了したら `coding/20260411_gesture_fix_completed.md` を作成すること。
