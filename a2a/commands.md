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

## 顔認証・顔登録

### 顔を登録する

がくこまが起動中（voice_loop）に話しかける：

```
「がくこま、これが〇〇だよ」
```

がくこまが `register_face` ツールを呼び出し、カメラで **15フレーム撮影→LBPH学習** を行う。
「〇〇の顔を登録した」と返答が来れば成功。

> **ポイント**: カメラ正面に立ち、顔全体が映るようにする。距離は50〜100cm程度が目安。

### 顔を識別する

```
「誰かいる？」「見て」など
```

がくこまが `look_at_user` を呼び出してサーボ追跡→識別を行う。

| 識別結果 | がくこまの返答例 |
|---|---|
| 登録済みの人物 | 「〇〇がいるね！」と名前で呼ぶ |
| 未登録の人物 | 「知らない人がいる」 |
| 顔なし | 「顔が見つからなかった」 |

### 登録済み人物を確認する（デバッグ用）

```bash
cd /home/tukapontas/gakukoma
python3 -c "from camera.face_recognizer import FaceRecognizer; print(FaceRecognizer().list_registered())"
```

### 識別の confidence 値を確認する（閾値チューニング用）

```bash
cd /home/tukapontas/gakukoma
python3 look_at_user.py 2>&1 | grep "識別結果"
# 出力例: [FaceRecognizer] 識別結果: label=0, confidence=85.3
```

- **confidence が低い（〜80）**: 確実に一致している
- **confidence が 110 前後**: 閾値付近（不安定）
- **confidence が高い（130〜）**: 一致していない（unknown）

閾値は `camera/face_recognizer.py` の `LBPH_THRESHOLD = 110.0` を変更する。

### 顔データをリセットして再登録する

```bash
rm /home/tukapontas/gakukoma/camera/face_data/_model.yml
rm /home/tukapontas/gakukoma/camera/face_data/_labels.txt
```

その後、voice_loop 起動中に再度「これが〇〇だよ」で登録しなおす。

> **注意**: 削除すると全員分のデータが失われる（LBPH の仕様）。

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
