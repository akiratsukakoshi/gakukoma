import cv2
import sys
import os
from pathlib import Path

YUNET_MODEL_PATH = Path("/home/tukapontas/gakukoma/camera/models/face_detection_yunet_2023mar.onnx")
_detector = None  # モジュールレベルでキャッシュ（毎回ロードしない）


def _get_yunet_detector(width: int, height: int):
    """YuNet検出器を取得（モデルファイルが存在しない場合はNone）"""
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
    cx, cy は矩形の中心座標
    顔が見つからない場合は空リスト []
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


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 face_detect.py <image_path>")
        sys.exit(1)

    image_path = sys.argv[1]
    results = detect_faces(image_path)

    print(f"検出件数: {len(results)}")
    for i, face in enumerate(results):
        print(f"Face {i+1}: Center({face['cx']}, {face['cy']}), Rect({face['x']}, {face['y']}, {face['w']}, {face['h']})")
