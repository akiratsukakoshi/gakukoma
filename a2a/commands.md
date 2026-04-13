# GAKUKOMA 操作コマンドメモ

> 実機操作で使うコマンドをここに記録していく。

---

## voice_loop（音声対話）

### 起動

```
python3 /home/tukapontas/gakukoma/voice_loop/voice_loop.py
```

`[IDLE] ウェイクワード待機中...` と表示されたら準備完了。

### 使い方

| 操作 | 動作 |
|---|---|
| 「おはよう」と話す | アクティブモードに移行（会話開始） |
| 普通に話しかける | Whisperで認識 → OpenClawが応答 → TTS発話 |
| 「おやすみ」と話す | IDLEモードに戻る（待機） |

### 終了

```
Ctrl + C
```

---

## パン・チルト（首振り）

### 方向指定

```bash
bash /home/tukapontas/gakukoma/tools/look_direction.sh <方向>
```

| 引数 | 動作 |
|---|---|
| `front` / `正面` | 正面を向く（デフォルト） |
| `left` / `左` | 左を向く（pan_max方向） |
| `right` / `右` | 右を向く（pan_min方向） |
| `up` / `上` | 上を向く（tilt_min方向） |
| `down` / `下` | 下を向く（tilt_max方向） |

### 角度直接指定

```bash
bash /home/tukapontas/gakukoma/tools/set_pan_tilt.sh <pan角度> <tilt角度>
```

- pan: 10〜170°（中央=90°）
- tilt: 60〜180°（中央=120°）

例：
```bash
bash /home/tukapontas/gakukoma/tools/set_pan_tilt.sh 90 90   # 正面やや上
bash /home/tukapontas/gakukoma/tools/set_pan_tilt.sh 45 120  # 右斜め
```

### センター復帰

```bash
bash /home/tukapontas/gakukoma/tools/look_center.sh
```

---
