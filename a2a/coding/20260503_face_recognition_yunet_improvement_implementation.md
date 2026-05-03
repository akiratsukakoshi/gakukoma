# 顔認識改善：Haar Cascade → YuNet換装 + 多フレーム登録 実装指示書

**作成日**: 2026-05-03
**担当**: コーディング担当AI（gakukoma-coder）
**依存**: Phase 5.2完了（✅ 済み）
**ハードウェア追加**: なし（ソフトウェアのみ）

---

## 背景・目的

現在の顔認識が不安定な原因を分析した結果、以下2点が主因と判明した：

1. **Haar Cascade（顔検出）の限界**: 正面以外・距離が少しあるだけで顔を検出できない。YuNetはDNNベースのため横顔・距離変化に強く、検出安定性が大幅に改善される。

2. **LBPHの学習サンプル不足**: 現在は1フレーム×輝度変化9バリエで登録している。複数フレーム（10〜20枚）をまとめて使って学習することで精度が向上する。

**目標**: 登録済みの人物を安定して認識できるようにする。既存インターフェイスは変えない。

---

## 変更対象ファイル

| ファイル | 種別 | 変更内容 |
|---|---|---|
| `camera/face_detect.py` | **変更** | Haar Cascade → YuNet |
| `camera/face_recognizer.py` | **変更** | 内部検出をYuNet化 + 多フレーム登録対応 |
| `brain/gakukoma_brain.py` | **変更** | `register_face` で複数フレーム取得 |

---

## Task A: YuNetモデルファイルの配置

YuNetはOpenCVに同梱のONNXモデルを使用する。

### A-1: モデルファイルの確認・ダウンロード

```bash
# まず同梱ファイルを探す
find /usr -name "face_detection_yunet*.onnx" 2>/dev/null
python3 -c "import cv2; print(cv2.__version__)"
```

見つからない場合はダウンロード：

```bash
mkdir -p /home/tukapontas/gakukoma/camera/models
cd /home/tukapontas/gakukoma/camera/models
wget -q "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx"
```

### A-2: cv2.FaceDetectorYN の動作確認

```bash
python3 - <<'EOF'
import cv2
print("OpenCV version:", cv2.__version__)
# YuNetが使えるか確認
try:
    det = cv2.FaceDetectorYN.create(
        "/home/tukapontas/gakukoma/camera/models/face_detection_yunet_2023mar.onnx",
        "", (320, 240)
    )
    print("YuNet OK")
except Exception as e:
    print("YuNet NG:", e)
EOF
```

---

## Task B: `camera/face_detect.py` の書き換え（Haar → YuNet）

**公開インターフェイスは変えない。** `detect_faces()` の戻り値フォーマット `[{"x", "y", "w", "h", "cx", "cy"}]` を維持すること。

### B-1: 実装方針

- `cv2.FaceDetectorYN.create()` でモデルをロード
- 入力サイズを `setInputSize()` でフレームサイズに合わせる
- 戻り値の各行は `[x1, y1, w, h, ...]` 形式なので、既存フォーマットに変換
- モデルファイルが存在しない場合は Haar Cascade にフォールバック（後方互換）

### B-2: 実装

```python
import cv2
import sys
import os
from pathlib import Path

YUNET_MODEL_PATH = Path("/home/tukapontas/gakukoma/camera/models/face_detection_yunet_2023mar.onnx")
_detector = None  # モジュールレベルでキャッシュ（毎回ロードしない）

def _get_yunet_detector(width: int, height: int):
    """YuNet検出器を取得（存在しない場合はNone）"""
    global _detector
    if not YUNET_MODEL_PATH.exists():
        return None
    if _detector is None:
        _detector = cv2.FaceDetectorYN.create(
            str(YUNET_MODEL_PATH), "", (width, height),
            score_threshold=0.6, nms_threshold=0.3, top_k=100
        )
    else:
        _detector.setInputSize((width, height))
    return _detector

def _detect_with_yunet(image) -> list[dict]:
    h, w = image.shape[:2]
    detector = _get_yunet_detector(w, h)
    if detector is None:
        return None  # フォールバックを示す
    _, faces = detector.detect(image)
    if faces is None:
        return []
    results = []
    for face in faces:
        x, y, fw, fh = int(face[0]), int(face[1]), int(face[2]), int(face[3])
        # 画像境界内にクランプ
        x = max(0, x)
        y = max(0, y)
        fw = min(fw, w - x)
        fh = min(fh, h - y)
        if fw < 20 or fh < 20:
            continue
        results.append({
            "x": x, "y": y, "w": fw, "h": fh,
            "cx": x + fw // 2, "cy": y + fh // 2
        })
    return results

def _detect_with_haar(image) -> list[dict]:
    """Haar Cascade フォールバック（YuNetモデル未配置時）"""
    possible_paths = [
        os.path.join(cv2.data.haarcascades, "haarcascade_frontalface_default.xml")
        if hasattr(cv2, 'data') else None,
        "/usr/share/opencv4/haarcascades/haarcascade_frontalface_default.xml",
        "/usr/share/opencv/haarcascades/haarcascade_frontalface_default.xml",
    ]
    cascade_path = next((p for p in possible_paths if p and os.path.exists(p)), None)
    if not cascade_path:
        return []
    face_cascade = cv2.CascadeClassifier(cascade_path)
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=3, minSize=(30, 30))
    results = []
    for (x, y, w, h) in faces:
        results.append({"x": int(x), "y": int(y), "w": int(w), "h": int(h),
                        "cx": int(x + w // 2), "cy": int(y + h // 2)})
    return results

def detect_faces(input_data) -> list[dict]:
    """
    input_data: image_path (str) OR image_frame (numpy array)
    戻り値: [{"x": int, "y": int, "w": int, "h": int, "cx": int, "cy": int}, ...]
    """
    image = None
    if isinstance(input_data, str):
        if not os.path.exists(input_data):
            return []
        image = cv2.imread(input_data)
    else:
        image = input_data
    if image is None:
        return []

    result = _detect_with_yunet(image)
    if result is None:
        # YuNetモデル未配置: Haar Cascadeで代替
        print("[face_detect] YuNetモデル未配置: Haar Cascadeで代替", file=sys.stderr)
        result = _detect_with_haar(image)
    return result
```

---

## Task C: `camera/face_recognizer.py` の修正

### C-1: 内部検出をYuNet化

`_detect_faces()` メソッドを Haar Cascade から YuNet に切り替える。
`face_detect.py` の `detect_faces()` を呼び出す形にすることで実装を共有できる。

```python
def _detect_faces(self, frame):
    """face_detect.detect_faces() を使って顔ROIを返す"""
    from camera.face_detect import detect_faces
    detected = detect_faces(frame)
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    result = []
    for d in detected:
        x, y, w, h = d["x"], d["y"], d["w"], d["h"]
        roi = cv2.resize(gray[y:y+h, x:x+w], (100, 100))
        result.append((roi, x, y, w, h))
    return result
```

### C-2: 多フレーム登録対応

`register()` メソッドは現在1フレームのみ受け取る設計だが、**呼び出し側（gakukoma_brain.py）が複数フレームを渡せるよう** `frames` パラメータを追加する。

```python
def register(self, image_frame, name: str, extra_frames: list = None) -> bool:
    """
    image_frame: メインフレーム（必須）
    extra_frames: 追加フレームのリスト（optional）。渡すと全フレームから顔ROIを抽出して学習。
    """
```

**処理の変更点:**
- `extra_frames` が渡された場合、全フレームから顔ROIを抽出してまとめて学習
- メインフレームから顔が検出できなくても、extra_framesから検出できれば登録成功
- 輝度変化による水増しは維持（1ROIにつき9バリエ）
- 実質的なサンプル数: フレーム数 × 9バリエ

### C-3: 閾値の調整

YuNet換装により検出の質が上がるため、LBPHの閾値を適切な値に戻す。

```python
LBPH_THRESHOLD = 110.0
```

（現在の165.0は検出器の不安定さをカバーするために上げられた値。YuNet換装後は過検出を防ぐため適切な値に戻す）

---

## Task D: `brain/gakukoma_brain.py` の修正

`register_face` ツールのハンドラで、**複数フレームを取得してから登録**する。

### D-1: 変更箇所

```python
elif tool_name == "register_face":
    name = tool_input.get("name", "")
    if not name:
        tool_result = "名前が指定されていない"
    else:
        from camera.capture import CameraCapture
        from camera.face_recognizer import FaceRecognizer
        cam = CameraCapture(device_id=0)

        # ウォームアップ
        for _ in range(3):
            cam.capture()

        # 複数フレーム取得（1.5秒間、15フレーム相当）
        import time
        frames = []
        for _ in range(15):
            f = cam.capture()
            if f is not None:
                frames.append(f)
            time.sleep(0.1)
        cam.release()

        if not frames:
            tool_result = "カメラから画像を取得できなかった"
        else:
            recognizer = FaceRecognizer()
            # 最初のフレームをメイン、残りをextra_framesとして渡す
            ok = recognizer.register(frames[0], name, extra_frames=frames[1:])
            if ok:
                tool_result = f"{name}の顔を登録した"
            else:
                tool_result = "顔が検出できなかった（正面を向いて）"
```

---

## 統合テスト

### T-1: YuNet動作確認

```bash
cd /home/tukapontas/gakukoma
python3 -c "
from camera.face_detect import detect_faces, YUNET_MODEL_PATH
print('モデルパス:', YUNET_MODEL_PATH)
print('モデル存在:', YUNET_MODEL_PATH.exists())
"
```

期待: `モデル存在: True`

### T-2: カメラ越しのYuNet検出確認

```bash
cd /home/tukapontas/gakukoma
python3 - <<'EOF'
import cv2
from camera.capture import CameraCapture
from camera.face_detect import detect_faces

cam = CameraCapture(device_id=0)
for _ in range(5):
    cam.capture()
frame = cam.capture()
cam.release()

faces = detect_faces(frame)
print(f"検出数: {len(faces)}")
for f in faces:
    print(f"  {f}")
EOF
```

期待: カメラ前に人がいる状態で `検出数: 1` 以上

### T-3: 顔登録テスト（多フレーム）

カメラ前に立ち、Python REPLで実行：

```bash
cd /home/tukapontas/gakukoma
python3 - <<'EOF'
import cv2
from camera.capture import CameraCapture
from camera.face_recognizer import FaceRecognizer

cam = CameraCapture(device_id=0)
for _ in range(3):
    cam.capture()

import time
frames = []
for _ in range(15):
    f = cam.capture()
    if f is not None:
        frames.append(f)
    time.sleep(0.1)
cam.release()

rec = FaceRecognizer()
ok = rec.register(frames[0], "テスト", extra_frames=frames[1:])
print("登録結果:", ok)
print("登録済み:", rec.list_registered())
EOF
```

期待: `登録結果: True`、`登録済み: ['テスト']`

### T-4: 顔識別テスト

```bash
cd /home/tukapontas/gakukoma
python3 - <<'EOF'
import cv2, time
from camera.capture import CameraCapture
from camera.face_recognizer import FaceRecognizer

cam = CameraCapture(device_id=0)
for _ in range(5):
    cam.capture()
frame = cam.capture()
cam.release()

rec = FaceRecognizer()
result = rec.identify(frame)
print("識別結果:", result)
EOF
```

期待: `識別結果: テスト`（T-3で登録した人物が映っている場合）

### T-5: `look_at_user` との統合

```bash
cd /home/tukapontas/gakukoma
python3 look_at_user.py
```

期待: 正常に動作し `{"success": true, "pan": ..., "tilt": ..., "identified": "テスト" or "unknown"}` が出力される

---

## 実装上の注意事項

1. **`__del__` 禁止**: `FaceRecognizer` に `__del__` を実装しないこと（プロジェクト共通ルール）。

2. **`_detector` のグローバルキャッシュ**: `face_detect.py` のモジュールレベル変数 `_detector` はサイズ変更時（`setInputSize`）に更新するが、インスタンスは使い回すこと（毎呼び出しでのモデルロードは重い）。

3. **face_data の互換性**: 既存の `_model.yml` / `_labels.txt` はそのまま使える。フォーマット変更なし。

4. **閾値は実機で調整**: T-4で識別できない場合（confidence が高い）は `LBPH_THRESHOLD` を上げる。誤識別が多い場合は下げる。登録サンプル数が増えるほど閾値は安定する。

5. **extra_frames が空の場合**: `extra_frames=None` または `extra_frames=[]` の場合は従来どおり1フレームのみで登録する（後方互換）。

---

完了報告書: `coding/20260503_face_recognition_yunet_improvement_completed.md`
