"""
顔認識クラス。顔の登録・識別・データ管理を行う。

- ライブラリ: OpenCV LBPH（dlib/face_recognitionのビルドが失敗したため代替採用）
- データ保存: camera/face_data/{name}.yml（LBPHモデルファイル）
              camera/face_data/{name}_label.txt（ラベル→名前マッピング）
- 識別閾値: confidence < 70（LBPHの信頼度は低いほど一致度高い）

公開インターフェイスは face_recognition ライブラリ版と同一:
    register(image_frame, name: str) -> bool
    identify(image_frame) -> str | None
    list_registered() -> list[str]
    delete(name: str) -> bool

注意: __del__ は実装しない（プロジェクト共通ルール）
"""

import os
import sys
import cv2
import numpy as np
from pathlib import Path

FACE_DATA_DIR = Path("/home/tukapontas/gakukoma/camera/face_data")

# LBPHの識別閾値（confidence < THRESHOLD で一致とみなす）
# LBPHは低い値ほど類似度が高い。
# 1〜数枚サンプルの実環境では 80〜130 程度の値が出る。
# 誤識別が多い場合は下げる（例: 80）、未識別が多い場合は上げる（例: 130）
LBPH_THRESHOLD = 165.0

# 顔サイズが小さすぎる場合は識別をスキップ
MIN_FACE_WIDTH = 40


def _get_cascade():
    """Haar Cascadeファイルを取得する。"""
    possible_paths = [
        os.path.join(cv2.data.haarcascades, "haarcascade_frontalface_default.xml")
        if hasattr(cv2, 'data') else None,
        "/usr/share/opencv4/haarcascades/haarcascade_frontalface_default.xml",
        "/usr/share/opencv/haarcascades/haarcascade_frontalface_default.xml",
    ]
    for path in possible_paths:
        if path and os.path.exists(path):
            return cv2.CascadeClassifier(path)
    raise RuntimeError("Haar Cascade file not found")


class FaceRecognizer:
    def __init__(self):
        """FACE_DATA_DIRを作成し、既存の顔データを全ロードする。"""
        FACE_DATA_DIR.mkdir(parents=True, exist_ok=True)
        self._cascade = _get_cascade()
        # {name: label_int} マッピング
        self._name_to_label: dict[str, int] = {}
        # {label_int: name} マッピング
        self._label_to_name: dict[int, str] = {}
        # LBPHRecognizer（登録済みデータが1件以上の場合のみ有効）
        self._recognizer = None
        self._load_all()

    def _label_file(self) -> Path:
        return FACE_DATA_DIR / "_labels.txt"

    def _model_file(self) -> Path:
        return FACE_DATA_DIR / "_model.yml"

    def _load_all(self):
        """保存済みラベルとモデルを読み込む。"""
        label_file = self._label_file()
        model_file = self._model_file()

        if label_file.exists():
            with open(label_file, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    parts = line.split("\t", 1)
                    if len(parts) == 2:
                        label_int = int(parts[0])
                        name = parts[1]
                        self._name_to_label[name] = label_int
                        self._label_to_name[label_int] = name

        if model_file.exists() and self._name_to_label:
            self._recognizer = cv2.face.LBPHFaceRecognizer_create()
            self._recognizer.read(str(model_file))

    def _save_labels(self):
        """ラベルマッピングをファイルに保存する。"""
        label_file = self._label_file()
        lines = []
        for name, label_int in self._name_to_label.items():
            lines.append(f"{label_int}\t{name}")
        with open(label_file, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")

    def _detect_faces(self, frame):
        """フレームから顔ROI（グレースケール）のリストを返す。
        戻り値: [(gray_roi, x, y, w, h), ...]
        """
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = self._cascade.detectMultiScale(
            gray,
            scaleFactor=1.1,
            minNeighbors=3,
            minSize=(30, 30),
        )
        result = []
        if len(faces) == 0:
            return result
        for (x, y, w, h) in faces:
            roi = cv2.resize(gray[y:y+h, x:x+w], (100, 100))
            result.append((roi, int(x), int(y), int(w), int(h)))
        return result

    def register(self, image_frame, name: str) -> bool:
        """
        image_frame（numpy array）から顔エンコーディングを取得して保存する。
        成功: True / 顔が検出できなかった or 複数顔ある: False
        登録後はメモリ内のデータも更新する。

        LBPHの精度向上のため、渡された1フレームを輝度変化・軽微なシフトで
        10バリエーションに水増しして学習する。
        """
        detected = self._detect_faces(image_frame)

        if len(detected) == 0:
            print(f"[FaceRecognizer] 顔が検出できませんでした（{name}）")
            return False
        if len(detected) > 1:
            print(f"[FaceRecognizer] 複数の顔が検出されました（{name}）。1人だけ映るようにしてください。")
            return False

        roi, x, y, w, h = detected[0]

        # ラベルを割り当て（既存名の上書き登録も可）
        if name in self._name_to_label:
            label_int = self._name_to_label[name]
        else:
            label_int = len(self._name_to_label)
            self._name_to_label[name] = label_int
            self._label_to_name[label_int] = name

        # データ水増し: 輝度変化・コントラスト調整で10バリエーション生成
        augmented = [roi]
        for alpha in [0.8, 0.9, 1.1, 1.2]:
            augmented.append(np.clip(roi.astype(np.float32) * alpha, 0, 255).astype(np.uint8))
        for beta in [-15, -8, 8, 15, 20]:
            augmented.append(np.clip(roi.astype(np.int16) + beta, 0, 255).astype(np.uint8))

        labels = np.array([label_int] * len(augmented))

        if self._recognizer is None:
            self._recognizer = cv2.face.LBPHFaceRecognizer_create()
            self._recognizer.train(augmented, labels)
        else:
            self._recognizer.update(augmented, labels)

        self._recognizer.save(str(self._model_file()))
        self._save_labels()

        print(f"[FaceRecognizer] {name} を登録しました（label={label_int}, サンプル数={len(augmented)}）")
        return True

    def identify(self, image_frame) -> str | None:
        """
        image_frame（numpy array）から顔を識別して名前を返す。
        一致: 人物名（str） / 不明: "unknown" / 顔なし: None
        複数人いる場合は最大面積の顔を優先。
        """
        if self._recognizer is None or not self._name_to_label:
            return None

        detected = self._detect_faces(image_frame)

        if len(detected) == 0:
            return None

        # 最大面積の顔を選択
        best = max(detected, key=lambda t: t[3] * t[4])  # w * h
        roi, x, y, w, h = best

        # 顔サイズが小さすぎる場合はスキップ
        if w < MIN_FACE_WIDTH:
            print(f"[FaceRecognizer] 顔が小さすぎるためスキップ（w={w}px < {MIN_FACE_WIDTH}px）")
            return None

        label_pred, confidence = self._recognizer.predict(roi)
        print(f"[FaceRecognizer] 識別結果: label={label_pred}, confidence={confidence:.1f}", file=sys.stderr)

        if confidence < LBPH_THRESHOLD:
            name = self._label_to_name.get(label_pred, "unknown")
            return name
        else:
            return "unknown"

    def list_registered(self) -> list[str]:
        """登録済みの人物名リストを返す。"""
        return list(self._name_to_label.keys())

    def delete(self, name: str) -> bool:
        """指定した人物のデータを削除する。
        注意: LBPHはモデルから特定ラベルを削除する標準APIがないため、
        全データを削除してモデルを再構築する。
        """
        if name not in self._name_to_label:
            return False

        del_label = self._name_to_label.pop(name)
        del self._label_to_name[del_label]

        # モデルファイルとラベルファイルを再生成
        model_file = self._model_file()
        if model_file.exists():
            model_file.unlink()

        self._save_labels()
        self._recognizer = None

        print(f"[FaceRecognizer] {name} のデータを削除しました。残り: {list(self._name_to_label.keys())}")
        print("[FaceRecognizer] 注意: 削除後は他の登録済み人物も再登録が必要です（LBPHモデル再構築のため）")
        return True
