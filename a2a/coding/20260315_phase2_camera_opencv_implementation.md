# 指示書：Phase 2 カメラ・OpenCV環境構築 + `see_around()` 実装

作成日: 2026-03-15
作成者: ClaudeCode（司令塔）
担当: Antigravity
完了報告ファイル名: `20260315_phase2_camera_opencv_completed.md`

---

## 前提条件

- Phase 1 が完了していること（voice_loop.py・STT/TTS・OpenClaw統合が動作済み）
- **このタスクはパン・チルト台座・PCA9685の完了を待たずに着手してよい**
- 完了後は `look_at_user()` 実装タスクの着手を司令塔に報告すること

---

## 作業概要

1. USBカメラ認識・OpenCV環境構築
2. `capture.py`（カメラキャプチャ基本クラス）実装
3. `face_detect.py`（顔検出モジュール）実装
4. `see_around.py`（周囲解析ツール）実装
5. OpenClaw統合（シェルラッパー + TOOLS.md更新）
6. 単体テスト

---

## 環境情報

- マシン: Raspberry Pi 5 Model B (16GB RAM, aarch64)
- OS: Debian GNU/Linux 13 (trixie)
- Python: 3.13.5（`python3`）
- pip: `pip3`
- 既存設定ファイル: `~/gakukoma/voice_loop/config.yaml`（Phase 1で作成済み）
- OpenClaw workspace: `~/.openclaw/workspace/`

---

## タスク 1：USBカメラ認識・OpenCV環境構築

### 1-1. パッケージインストール

```bash
apt install -y python3-opencv v4l-utils
pip3 install anthropic
```

`python3-opencv` を apt 優先とする。もし apt 版が動作しない場合のみ、pip3 で `opencv-python-headless` を試すこと。

### 1-2. カメラ接続確認

```bash
# デバイスの確認
v4l2-ctl --list-devices
ls /dev/video*
```

カメラが複数認識される場合がある（例: `/dev/video0` と `/dev/video1`）。`v4l2-ctl --list-devices` でどれが実際のカメラかを確認し、後述の `config.yaml` に正しいデバイス番号を記録すること。

### 1-3. OpenCV動作確認

```bash
python3 -c "
import cv2
cap = cv2.VideoCapture(0)
print('カメラオープン:', cap.isOpened())
ret, frame = cap.read()
print('フレーム取得:', ret, 'サイズ:', frame.shape if ret else 'N/A')
cap.release()
"
```

デバイス番号 `0` で開けない場合は `1` や `2` も試すこと。

### 1-4. config.yaml に camera セクションを追記

**既存ファイル**: `~/gakukoma/voice_loop/config.yaml`

以下を末尾に**追記**する（既存内容は変更しない）:

```yaml
# カメラ設定（Phase 2追加）
camera:
  device: 0               # /dev/video0（認識確認後に修正）
  width: 640
  height: 480
  capture_file: "/tmp/gakukoma_capture.jpg"

# Anthropic API設定（Phase 2追加）
anthropic:
  model: "claude-haiku-4-5-20251001"
  # APIキーはOPENAI_API_KEY環境変数ではなく ~/.openclaw/agents/main/agent/auth-profiles.json から取得
```

---

## タスク 2：ディレクトリ作成

```bash
mkdir -p /home/tukapontas/gakukoma/camera
```

---

## タスク 3：`capture.py` 実装

**ファイルパス**: `/home/tukapontas/gakukoma/camera/capture.py`

**機能**:
- `CameraCapture` クラスとして実装
- `config.yaml` からデバイス番号・解像度・保存パスを読み込む
- `capture_frame()` メソッド: 1フレームを取得して JPEG ファイルに保存し、ファイルパスを返す
- `release()` メソッド: カメラリソースの解放

**実装要件**:
```python
import cv2
import yaml

class CameraCapture:
    def __init__(self, config_path="~/gakukoma/voice_loop/config.yaml"):
        # configを読み込み、VideoCapture を初期化
        # device, width, height, capture_file を設定

    def capture_frame(self) -> str:
        # 1フレーム取得 → JPEG保存 → ファイルパスを返す
        # 失敗時は RuntimeError を raise

    def release(self):
        # cap.release() を呼ぶ
```

---

## タスク 4：`face_detect.py` 実装

**ファイルパス**: `/home/tukapontas/gakukoma/camera/face_detect.py`

**機能**:
- OpenCV の Haar Cascades（`haarcascade_frontalface_default.xml`）を使用
- 画像ファイルパスを受け取り、顔の矩形リストを返す
- コマンドライン引数でも動作する（単体テスト用）

**Haar Cascade ファイルのパス**:
```python
# OpenCV インストール先を自動検索
import cv2
cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
```

**実装要件**:
```python
def detect_faces(image_path: str) -> list[dict]:
    """
    戻り値: [{"x": int, "y": int, "w": int, "h": int, "cx": int, "cy": int}, ...]
    cx, cy は矩形の中心座標
    顔が見つからない場合は空リスト []
    """

# コマンドライン実行時:
# python3 face_detect.py <画像パス>
# → 検出件数と各矩形の中心座標を標準出力
```

**検出パラメータ**:
```python
faces = face_cascade.detectMultiScale(
    gray,
    scaleFactor=1.1,
    minNeighbors=5,
    minSize=(30, 30)
)
```

---

## タスク 5：`see_around.py` 実装

**ファイルパス**: `/home/tukapontas/gakukoma/camera/see_around.py`

**機能**:
- カメラで1フレーム撮影
- 撮影した画像を base64 エンコードして Claude Vision API に送信
- 「この画像に何が写っていますか？日本語で2〜3文で簡潔に説明してください。」とプロンプト
- レスポンステキストを標準出力に出力

**APIキーの取得方法**:
```python
import os, json

def get_api_key() -> str:
    # 1. 環境変数 ANTHROPIC_API_KEY を優先
    key = os.environ.get("ANTHROPIC_API_KEY")
    if key:
        return key
    # 2. OpenClawの auth-profiles.json からフォールバック
    auth_path = os.path.expanduser(
        "~/.openclaw/agents/main/agent/auth-profiles.json"
    )
    with open(auth_path) as f:
        profiles = json.load(f)
    # anthropic プロバイダーのキーを探す
    # ファイル構造は実際のファイルを確認して合わせること
    ...
```

**Claude Vision API 呼び出し**:
```python
import anthropic, base64

client = anthropic.Anthropic(api_key=api_key)
with open(image_path, "rb") as f:
    image_data = base64.standard_b64encode(f.read()).decode("utf-8")

message = client.messages.create(
    model="claude-haiku-4-5-20251001",
    max_tokens=300,
    messages=[{
        "role": "user",
        "content": [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/jpeg",
                    "data": image_data,
                },
            },
            {
                "type": "text",
                "text": "この画像に何が写っていますか？日本語で2〜3文で簡潔に説明してください。"
            }
        ],
    }]
)
print(message.content[0].text)
```

**エラーハンドリング**:
- カメラが開けない場合: 「カメラが見つかりません」と標準出力して終了
- API呼び出し失敗の場合: 「画像の解析に失敗しました: {エラー内容}」と標準出力して終了

---

## タスク 6：OpenClaw統合

### 6-1. シェルラッパー作成

**ファイルパス**: `/home/tukapontas/gakukoma/tools/see_around.sh`

```bash
#!/bin/bash
python3 /home/tukapontas/gakukoma/camera/see_around.py
```

```bash
chmod +x /home/tukapontas/gakukoma/tools/see_around.sh
```

### 6-2. TOOLS.md 更新

`~/.openclaw/workspace/TOOLS.md` の末尾に以下を追記する：

```markdown
---

## GAKUKOMA Vision Tools（Phase 2追加）

フィジカルAIロボット「がくこま」の視覚ツール。

### see_around
- コマンド: `/home/tukapontas/gakukoma/tools/see_around.sh`
- 機能: Webカメラで周囲を撮影し、Claude Vision APIで画像内容を日本語で説明する
- 引数: なし
- 戻り値: 画像の説明テキスト（日本語、2〜3文）
- 備考: カメラデバイス /dev/video0 を使用
```

### 6-3. SOUL.md 更新

`~/.openclaw/workspace/SOUL.md` の「能力（将来: Phase 2以降）」の記述を「能力（現在: Phase 2）」に更新し、以下を反映する：

```markdown
### 能力（現在: Phase 2）
- 音声で会話する（listen_voice / speak_text ツール）
- 質問に答える、雑談する
- 周囲を見て説明する（see_around ツール）
- ユーザーの顔にカメラを向ける（look_at_user ツール）※サーボ手配後に有効化
```

---

## タスク 7：単体テスト

以下を全て確認し、完了報告書に結果を記録する。

| # | テスト | 合格条件 |
|---|---|---|
| T-1 | カメラ認識 | `VideoCapture(device).isOpened()` が True |
| T-2 | フレーム取得 | `/tmp/gakukoma_capture.jpg` が生成される |
| T-3 | 顔検出（正面顔あり） | 少なくとも1件の矩形が返る |
| T-4 | 顔検出（顔なし） | 空リスト `[]` が返る（エラーにならない） |
| T-5 | `see_around.py` 単体 | 日本語の説明文が標準出力に表示される |
| T-6 | `see_around.sh` 経由 | シェルラッパーから同様に動作する |

---

## 完了報告書の作成

全タスク完了後、`/home/tukapontas/a2a/coding/20260315_phase2_camera_opencv_completed.md` を作成し、以下を記載すること：

- 各タスクの完了状況
- カメラのデバイス番号（`/dev/video` 何番か）と解像度
- インストールしたパッケージとバージョン（`python3-opencv` or `opencv-python-headless`）
- 顔検出の精度感想（良好 / 精度不足 / 要調整）
- `see_around()` の動作確認結果（レイテンシ概算含む）
- 問題点・申し送り事項（あれば）
