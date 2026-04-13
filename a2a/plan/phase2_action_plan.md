# Phase 2 アクションプラン：視覚と表情（Eyes & Neck）

作成日: 2026-03-15
作成者: ClaudeCode（司令塔）
対象フェーズ: Phase 2

---

## 1. フェーズ目標

「目が動く・見える」ロボットの実現。

- Webカメラによる視覚入力（静止画取得・顔検出）
- PCA9685 + SG90 ×2 によるパン・チルト首振り
- 顔を認識し自動追跡する `look_at_user()` ツール
- 周囲の様子を解析して報告する `see_around()` ツール
- 上記ツールのOpenClaw統合（TOOLS.md更新）

---

## 2. ハードウェア構成（手配済み）

| パーツ | 仕様 | 役割 |
|---|---|---|
| USB Webカメラ | 1080p広角 / USBバスパワー | 視覚入力（映像ストリーム） |
| パン・チルト台座 | SG90用 ブラケットセット（SG90×2付属） | カメラの向き制御 |
| PCA9685 | I2C接続 16chサーボドライバ | サーボPWM生成 |
| SG90 ×2 | 5V駆動 180°サーボ | パン軸・チルト軸 |

### PCA9685配線仕様

| PCA9685端子 | Raspberry Pi 5 | 備考 |
|---|---|---|
| SDA | GPIO2（Pin 3） | I2Cデータ |
| SCL | GPIO3（Pin 5） | I2Cクロック |
| VCC | 3.3V（Pin 1） | ロジック電源 |
| GND | GND（Pin 6） | 共通GND |
| V+ | 5V（Pin 4） | サーボ駆動電源 |

**注意**: V+（サーボ電源）はRPi 5の5V端子から供給可能だが、SG90×2同時動作で電流が増えるため、外部5V電源（BEC or USBアダプタ）を推奨。Phase 3で電源系統を整備するまでの暫定として、RPi 5Vから取得する形でよい。

### サーボチャンネル割り当て

| PCA9685チャンネル | 役割 | 角度範囲 | 中央（正面） |
|---|---|---|---|
| ch0 | パン（水平・左右） | 0°〜180° | 90° |
| ch1 | チルト（垂直・上下） | 60°〜120° | 90° |

**チルト制限**: SG90の可動域は180°だが、カメラ台座の機構的制約でチルトは60°〜120°に制限する（落下・ケーブル断線防止）。

---

## 3. タスク分解と依存関係

```
[Gemini] パン・チルト台座組み立て ─┐
[Gemini] PCA9685配線              ─┤→ [Antigravity] look_at_user()実装
[Antigravity] カメラ/OpenCV環境   ─┘        ↓
                                    [統合テスト]（Antigravity + Gemini協力）
```

### 並行着手可能タスク（先行開始）

| タスク | 担当 | 前提条件 |
|---|---|---|
| カメラ・OpenCV環境構築 + `see_around()`実装 | Antigravity | Phase 1完了のみ |
| パン・チルト台座組み立て | Gemini | Phase 1完了のみ |
| PCA9685配線 | Gemini | 台座組み立て完了後 |

### 順次タスク（先行完了後）

| タスク | 担当 | 前提条件 |
|---|---|---|
| `look_at_user()` 実装 | Antigravity | カメラ/OpenCV完了 + PCA9685配線完了 |
| 統合テスト・チューニング | Antigravity | 全タスク完了後 |

---

## 4. 各タスク詳細

---

### Task A：カメラ・OpenCV環境構築 + `see_around()` 実装（Antigravity）

**概要**: USBカメラをOpenCVで扱えるようにし、顔検出と画像解析機能を構築する。

**ディレクトリ構成**:
```
~/gakukoma/
  camera/
    capture.py      # カメラキャプチャ基本クラス
    face_detect.py  # 顔検出モジュール（Haar Cascades）
    see_around.py   # see_around()ツール本体
```

**ライブラリ**:
```bash
apt install -y python3-opencv v4l-utils
pip3 install anthropic  # see_around()でClaude Vision APIを使用
```

**カメラ検出確認コマンド**:
```bash
v4l2-ctl --list-devices
ls /dev/video*
```

**capture.py の機能**:
- `VideoCapture` でカメラを開く（デバイス番号は `config.yaml` で管理）
- フレーム取得・JPEGとして保存（`/tmp/gakukoma_capture.jpg`）
- 解像度設定: 640×480（処理速度優先）

**face_detect.py の機能**:
- OpenCV Haar Cascades（`haarcascade_frontalface_default.xml`）による顔検出
- 入力: 画像ファイルパス or フレーム
- 出力: 顔矩形リスト `[(x, y, w, h), ...]`（検出なし時は空リスト）

**see_around.py の機能**:
- カメラで1フレーム撮影
- 画像をbase64エンコードしてClaude Vision API（`claude-haiku-4-5-20251001`）に送信
- プロンプト: 「この画像に何が写っていますか？日本語で簡潔に説明してください。」
- 結果テキストを標準出力に返す
- `config.yaml` の `anthropic.api_key` 参照（または環境変数 `ANTHROPIC_API_KEY` からも取得）

**`config.yaml` 追記内容**:
```yaml
camera:
  device: 0           # /dev/video0（変更があれば要更新）
  width: 640
  height: 480
  capture_file: "/tmp/gakukoma_capture.jpg"

anthropic:
  api_key: ""         # ANTHROPIC_API_KEY環境変数から取得（空欄でよい）
  model: "claude-haiku-4-5-20251001"
```

**OpenClaw統合**:
```bash
~/gakukoma/tools/see_around.sh  # python3 see_around.py を呼ぶラッパー
```

`TOOLS.md` に `see_around` ツール定義を追記。

**単体テスト**:
- カメラ認識: `python3 -c "import cv2; cap=cv2.VideoCapture(0); print(cap.isOpened())"`
- 顔検出: テスト画像で `face_detect.py` を実行
- `see_around.py` 単体実行で画像解析テキストが返ること

---

### Task B：パン・チルト台座組み立て（Gemini）

**概要**: SG90×2をブラケットに取り付け、Webカメラを台座に固定する。

**手順概要**:
1. ブラケットにSG90を2個取り付け（パン用・チルト用）
2. チルト用SG90のホーンにカメラブラケットを固定
3. パン用SG90のホーンにチルトユニット全体を固定
4. WebカメラをM3ネジまたは両面テープで台座最上部に取り付け
5. SG90のコネクタをラベリング（「パン ch0」「チルト ch1」）

**確認事項**:
- 台座を手動で動かしたとき、パン・チルト各軸がスムーズに回転すること
- ケーブルが干渉していないこと
- カメラが正面向きに固定されていること

**完了報告で記録**:
- 台座の外観写真（またはスケッチ）
- SG90の接続向き（パン: どちら向きか、チルト: どちら向きか）
- ケーブル長の余裕・取り回し状況

---

### Task C：PCA9685配線（Gemini）

**概要**: PCA9685をRPi 5にI2C接続し、SG90×2をPCA9685に接続する。

**手順概要**:
1. I2C有効化確認（`raspi-config` → Interface Options → I2C）
2. PCA9685とRPi 5をジャンパーワイヤで配線（上記の配線仕様参照）
3. SG90コネクタをPCA9685の ch0（パン）・ch1（チルト）に接続
4. I2C疎通確認:
   ```bash
   apt install -y i2c-tools
   i2cdetect -y 1
   # → 0x40 が表示されればOK
   ```
5. Pythonからの疎通確認:
   ```bash
   pip3 install adafruit-circuitpython-pca9685 adafruit-circuitpython-motor
   python3 -c "import board, busio, adafruit_pca9685; i2c=busio.I2C(board.SCL,board.SDA); pca=adafruit_pca9685.PCA9685(i2c); print('PCA9685 OK')"
   ```

**完了報告で記録**:
- `i2cdetect -y 1` の出力（0x40確認）
- `python3` からの疎通確認結果
- 電源構成（5V: RPi本体 or 外部？）
- SG90の簡易動作確認（手動コマンドで動いたか）

---

### Task D：`look_at_user()` 実装（Antigravity）

**前提**: Task A（カメラ/OpenCV）と Task C（PCA9685配線）が両方完了していること。

**概要**: 顔認識結果をもとにパン・チルトサーボを制御し、カメラをユーザーの顔に向け続ける。

**ディレクトリ構成**:
```
~/gakukoma/
  servo/
    pca9685_ctrl.py   # PCA9685制御クラス
    pan_tilt.py       # パン・チルト制御クラス
  look_at_user.py     # look_at_user()統合スクリプト
  tools/
    look_at_user.sh   # OpenClaw用ラッパー
```

**pca9685_ctrl.py の実装**:
```python
# adafruit-circuitpython-pca9685 を使用
# SG90の角度(0〜180°) → PWMデューティサイクル変換
# SG90仕様: 50Hz, パルス幅 1000μs(0°) 〜 2000μs(180°)
# 中央(90°) = 1500μs
```

**pan_tilt.py の実装**:
```python
# PCA9685Ctrlを使用してパン・チルト角度を設定するクラス
# 角度制限の適用（パン: 0〜180°, チルト: 60〜120°）
# set_pan(angle), set_tilt(angle), center() メソッド
# center(): パン=90°, チルト=90° に戻す
```

**look_at_user.py の動作フロー**:
```
1. カメラ・サーボ初期化
2. サーボをセンター（正面）に向ける
3. ループ開始（最大試行回数または収束まで）:
   a. フレーム取得
   b. 顔検出（face_detect.py使用）
   c. 顔が見つからない場合: 少し待ってリトライ（最大3回）
   d. 顔の中心座標(cx, cy)を算出
   e. 画面中心(320, 240)とのオフセット(dx, dy)を算出
   f. オフセット → 角度変換（比例ゲイン: 1px = 0.1°程度から調整）
   g. 現在角度 ± 補正量でサーボ更新
   h. 顔が画面中央±30px以内なら「収束」とみなして終了
4. 最終的なパン・チルト角度と「顔追跡成功 or タイムアウト」を標準出力
```

**比例制御パラメータ（調整対象）**:
```yaml
# config.yaml に追記
servo:
  pan_channel: 0
  tilt_channel: 1
  pan_gain: 0.1        # 1pxあたりの補正角度（要チューニング）
  tilt_gain: 0.1
  convergence_px: 30   # 収束判定の許容誤差（ピクセル）
  max_iterations: 20   # 最大追跡ループ回数
  loop_interval: 0.1   # ループ間隔（秒）
```

**OpenClaw統合**:
- `tools/look_at_user.sh` を作成（`python3 look_at_user.py` のラッパー）
- `TOOLS.md` に `look_at_user` ツール定義を追記
- `SOUL.md` のPhase 2能力欄を「視覚による顔追跡が可能」に更新

---

### Task E：統合テスト（Antigravity 主体）

**前提**: 全タスク完了後

**テストシナリオ**:

| # | テスト | 合格条件 |
|---|---|---|
| T-1 | カメラ認識 | `/dev/video0` が存在し、OpenCVで開けること |
| T-2 | 顔検出単体 | 正面を向いた顔を少なくとも1件検出できること |
| T-3 | see_around()単体 | 画像内容の日本語説明文が返ること |
| T-4 | サーボ単体（パン） | ch0が 0°/90°/180° に動くこと |
| T-5 | サーボ単体（チルト） | ch1が 60°/90°/120° に動くこと |
| T-6 | look_at_user()単体 | 人物の顔がある場合にカメラが向き直ること |
| T-7 | OpenClaw統合 | 「周りを見て」と言うとsee_around()が起動し結果を発話すること |
| T-8 | OpenClaw統合 | 「こっちを見て」と言うとlook_at_user()が起動しサーボが動くこと |
| T-9 | エラー耐性 | 顔が見つからない場合に正常なエラーメッセージを返すこと |

---

## 5. 指示書ファイル計画

プラン確認後、以下の指示書を作成する（ファイル名はWorkflowルールに従う）:

| ファイル名 | 格納先 | 担当 |
|---|---|---|
| `20260315_phase2_camera_opencv_implementation.md` | `coding/` | Antigravity |
| `20260315_phase2_pantilt_assembly_implementation.md` | `hardware/` | Gemini |
| `20260315_phase2_pca9685_wiring_implementation.md` | `hardware/` | Gemini |
| `20260315_phase2_look_at_user_implementation.md` | `coding/` | Antigravity（Task C完了後） |

統合テストは別指示書を立てず、`look_at_user_implementation.md` 内のタスクに含める。

---

## 6. リスクと対策

| リスク | 対策 |
|---|---|
| SG90のトルク不足でカメラを支えられない | カメラは軽量モデルのため問題ない見込み。台座の重心バランスを調整 |
| PCA9685のI2Cアドレス競合 | 現在I2Cデバイスはなし。`i2cdetect` で0x40のみ確認して進める |
| SG90×2の電流でRPi 5Vがドロップ | Phase 2は暫定RPi 5Vから供給。問題があれば外部BEC（5V/2A）を使用 |
| see_around()のAPI呼び出しコスト | Haiku使用で低コスト。ツール呼び出し頻度はLLMが判断するため過剰呼び出しリスク低 |
| OpenCVのインストール失敗（aarch64依存） | `python3-opencv`（aptパッケージ）優先。pip版は最終手段 |
| 顔認識精度不足（Haar Cascades） | まずHaar Cascadesで実装。精度不足の場合はMediaPipeに移行（依存追加の覚悟必要）|

---

## 7. Phase 2 完了条件

- [ ] Webカメラが `/dev/video0` で認識され、OpenCVから取得できる
- [ ] 顔検出が動作する（Haar Cascades）
- [ ] `see_around()` がOpenClaw経由で呼び出せる
- [ ] パン・チルト台座が組み立てられ、SG90が動作する
- [ ] PCA9685がI2Cで認識され（0x40）、Pythonから制御できる
- [ ] `look_at_user()` がOpenClaw経由で呼び出せる
- [ ] T-1〜T-9の全テストに合格する
- [ ] SOUL.mdがPhase 2能力を反映している
- [ ] 各担当者が完了報告書を提出済み

---

## 8. 申し送り事項（Phase 1からの引き継ぎ）

- デバイス設定は `~/gakukoma/voice_loop/config.yaml` に集約されている。Phase 2の `camera:` と `servo:` セクションを同ファイルに追記すること
- Anthropic APIキーは `~/.openclaw/agents/main/agent/auth-profiles.json` に登録済み。環境変数 `ANTHROPIC_API_KEY` は未設定の可能性あり → `see_around.py` では `auth-profiles.json` から読む、または `ANTHROPIC_API_KEY` 環境変数に頼らず `openclawのanthropic`ライブラリ経由を検討
- OpenClaw TOOLS.mdは `~/.openclaw/workspace/TOOLS.md`、SOUL.mdは `~/.openclaw/workspace/SOUL.md`
- `voice_loop.py` は常駐型（PTTループ）。Phase 2ではサーボ制御はコマンド呼び出し型（都度起動）のため、voice_loop.pyへの組み込みは不要
