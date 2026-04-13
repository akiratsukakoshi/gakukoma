# TOOLS.md - がくこまのツール一覧

ここに書かれているコマンドが、あなた（がくこま）の手足です。
ユーザーの言葉を受け取ったら、このファイルを参照してどのツールを使うか判断してください。

---

## 音声

### speak_text
- **いつ使う**: 何かを声で伝えたいとき
- **コマンド**: `/home/tukapontas/gakukoma/tools/speak_text.sh "<テキスト>"`
- **戻り値**: なし（再生完了で終了）

---

## 視覚

### see_around
- **いつ使う**: 「何が見える？」「周りを見て」「〇〇を撮って」など、今の視点で周囲を確認するとき
- **コマンド**: `/home/tukapontas/gakukoma/tools/see_around.sh`
- **戻り値**: 画像の説明テキスト（日本語、2〜3文）
- **備考**: カメラは現在の首の向きで撮影する。方向を変えたいなら先に look_direction を使う
- **注意：** 返された説明文は参考情報。君が実際に見た視界として話すこと。
第三者的な解説ではなく、「僕はこう見えた」と言う。

### survey_room
- **いつ使う**: 「部屋を調べて」「入口はどこ？」「移動できる方向は？」「周りに何がある？」など、部屋の構造や通路を把握したいとき
- **コマンド**: `/home/tukapontas/gakukoma/tools/survey_room.sh`
- **戻り値**: ドア・入口・通路・障害物の方向（テキスト、2〜3文）
- **備考**: 左・正面・右の3方向を撮影してVision APIに一括送信する。約15〜20秒かかる。実行前に「部屋を調べてみるね、少し待ってて」と発話すること

---

## 首の制御（サーボ）

### ツール選択ルール

| ユーザーの言葉 | 使うツール |
|---|---|
| 「右を向いて」「上を見て」「左！」など方向を指示 | `look_direction` |
| 「正面向いて」「元に戻って」「こっち向いて」 | `look_center` |
| 「僕の顔を見て」「私を見て」（顔追跡） | `look_at_user` |
| 「60度」など数値で角度指定 | `set_pan_tilt` |

**よくある流れ**: 方向を向く → （必要なら see_around で撮影） → look_center で正面に戻る

### look_direction
- **コマンド**: `/home/tukapontas/gakukoma/tools/look_direction.sh "<方向>"`
- **方向の指定**: `right`/`右`、`left`/`左`、`up`/`上`、`down`/`下`、`front`/`正面`、`upper-right`/`右上` など
- **戻り値**: `look_direction成功: pan=X° tilt=Y°`

### look_center
- **コマンド**: `/home/tukapontas/gakukoma/tools/look_center.sh`
- **戻り値**: `look_center成功: pan=90° tilt=90°`

### look_at_user
- **コマンド**: `/home/tukapontas/gakukoma/tools/look_at_user.sh`
- **戻り値**: `顔追跡成功: pan=X° tilt=Y°` または `タイムアウト: 顔が見つかりませんでした`

### set_pan_tilt
- **コマンド**: `/home/tukapontas/gakukoma/tools/set_pan_tilt.sh <pan角度> <tilt角度>`
- **引数**: パン（10〜170）、チルト（60〜180）。範囲外は自動でクランプされる
- **戻り値**: `set_pan_tilt成功: pan=X° tilt=Y°`
