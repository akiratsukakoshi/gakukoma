"""
顔認識クラス。顔の登録・識別・データ管理を行う。

- 認識: SFace（cv2.FaceRecognizerSF / ONNX埋め込み 128次元 + cosine類似度）
  モデル: models/face_recognition_sface_2021dec.onnx
  取得元: https://github.com/opencv/opencv_zoo/raw/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx
  sha256: 0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79 (38,696,353 bytes)
- 顔検出: YuNet（DNN・landmark付き）を優先。モデル未配置時は Haar Cascade に
  フォールバックし、bboxから標準5点landmarkを推定して alignCrop に渡す。
- データ保存: camera/face_data/_sface_index.json（名前→埋め込みファイルの台帳）
              camera/face_data/sface_<hash>.npz（人物ごとの埋め込み。key="embeddings"）
- 旧LBPHデータ（_model.yml / _labels.txt）は削除せず face_data/lbph_backup/ へ
  自動退避する（非破壊）。LBPH→SFaceのデータ変換は不可能なため、移行後は再登録が必要。
- 識別閾値: cosine類似度 >= SFACE_COSINE_THRESHOLD で一致
  （opencv_zoo公式推奨値 0.363。SFaceは高いほど一致度高い＝LBPHと逆向き）

公開インターフェイスは LBPH版と同一:
    register(image_frame, name: str, extra_frames: list = None) -> bool
    identify(image_frame) -> str | None
    list_registered() -> list[str]
    delete(name: str) -> bool

注意: __del__ は実装しない（プロジェクト共通ルール）
"""

import json
import hashlib
import shutil
import sys
import time
import cv2
import numpy as np
from pathlib import Path

# 実機ではホームdir自体がgitクローンのため __file__ 基準で解決する
# （実機: /home/tukapontas/gakukoma/camera/... ローカル: <repo>/gakukoma/camera/...）
_CAMERA_DIR = Path(__file__).resolve().parent

FACE_DATA_DIR = _CAMERA_DIR / "face_data"

# SFace認識モデル（opencv_zoo公式。取得元URL/sha256はファイル先頭docstring参照）
SFACE_MODEL_PATH = _CAMERA_DIR / "models" / "face_recognition_sface_2021dec.onnx"

# YuNet検出モデル（face_detect.py と同一モデルを流用。こちらはlandmark付き生出力を使う）
YUNET_MODEL_PATH = _CAMERA_DIR / "models" / "face_detection_yunet_2023mar.onnx"

# SFaceの識別閾値（cosine類似度 >= THRESHOLD で一致とみなす）
# opencv_zoo公式ベンチマークの推奨値 0.363（LFWでチューニングされた値）。
# 誤識別（他人を本人と言う）が多い場合は上げる（例: 0.45）、
# 未識別（本人をunknownと言う）が多い場合は下げる（例: 0.30）
SFACE_COSINE_THRESHOLD = 0.363

# 顔サイズが小さすぎる場合は識別をスキップ
MIN_FACE_WIDTH = 40

# 1人あたり保持する埋め込みの上限（identifyの計算量と保存サイズを抑える。新しいものを優先）
MAX_EMBEDDINGS_PER_PERSON = 20

# Haarフォールバック時にbboxから5点landmarkを推定するための相対位置
# （ArcFace系の112x112標準テンプレートをbbox比率に換算した値。
#   順序はYuNet準拠: 右目, 左目, 鼻先, 口右端, 口左端）
_BBOX_LANDMARK_FRACTIONS = (
    (0.342, 0.462),
    (0.657, 0.460),
    (0.500, 0.641),
    (0.371, 0.825),
    (0.632, 0.823),
)


class FaceRecognizer:
    def __init__(self):
        """FACE_DATA_DIRを作成し、旧LBPHデータを退避し、既存の埋め込みを全ロードする。"""
        FACE_DATA_DIR.mkdir(parents=True, exist_ok=True)

        if not SFACE_MODEL_PATH.exists():
            raise FileNotFoundError(
                f"SFaceモデルが見つかりません: {SFACE_MODEL_PATH}\n"
                "opencv_zoo公式から face_recognition_sface_2021dec.onnx を "
                "camera/models/ に配置してください（ファイル先頭docstringのURL参照）"
            )
        self._sface = cv2.FaceRecognizerSF.create(str(SFACE_MODEL_PATH), "")

        # YuNet検出器（landmark付き生出力用。モデル未配置ならNoneのままHaarフォールバック）
        self._yunet = None

        # {name: 埋め込み行列 (N, 128) float32}
        self._embeddings: dict[str, np.ndarray] = {}

        self._backup_lbph_files()
        self._load_all()

    # ------------------------------------------------------------------
    # データ管理
    # ------------------------------------------------------------------
    def _index_file(self) -> Path:
        return FACE_DATA_DIR / "_sface_index.json"

    def _embedding_file(self, name: str) -> Path:
        digest = hashlib.sha1(name.encode("utf-8")).hexdigest()[:12]
        return FACE_DATA_DIR / f"sface_{digest}.npz"

    def _backup_lbph_files(self):
        """旧LBPHデータ（_model.yml / _labels.txt）を face_data/lbph_backup/ へ退避する（非破壊）。
        LBPH→SFaceのデータ変換は不可能なため、退避後は各人物の再登録が必要。
        """
        legacy = [FACE_DATA_DIR / "_model.yml", FACE_DATA_DIR / "_labels.txt"]
        existing = [p for p in legacy if p.exists()]
        if not existing:
            return
        backup_dir = FACE_DATA_DIR / "lbph_backup"
        backup_dir.mkdir(parents=True, exist_ok=True)
        for src in existing:
            dst = backup_dir / src.name
            if dst.exists():
                # 既存バックアップは上書きしない（タイムスタンプ付きで別名保存）
                dst = backup_dir / f"{src.name}.{int(time.time())}"
            shutil.move(str(src), str(dst))
            print(f"[FaceRecognizer] 旧LBPHデータを退避: {src.name} -> {dst}", file=sys.stderr)
        print(
            "[FaceRecognizer] LBPH→SFace移行: 旧データは変換できないため、各人物の再登録が必要です",
            file=sys.stderr,
        )

    def _load_all(self):
        """台帳と埋め込みファイルを読み込む。"""
        index_file = self._index_file()
        if not index_file.exists():
            return
        try:
            with open(index_file, encoding="utf-8") as f:
                index = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            print(f"[FaceRecognizer] 台帳の読み込みに失敗: {e}", file=sys.stderr)
            return

        for name, filename in index.get("people", {}).items():
            path = FACE_DATA_DIR / filename
            if not path.exists():
                print(f"[FaceRecognizer] 埋め込みファイル欠損のためスキップ: {name} ({filename})",
                      file=sys.stderr)
                continue
            try:
                with np.load(path) as data:
                    emb = np.asarray(data["embeddings"], dtype=np.float32)
                if emb.ndim == 2 and emb.shape[0] > 0:
                    self._embeddings[name] = emb
            except (OSError, KeyError, ValueError) as e:
                print(f"[FaceRecognizer] 埋め込みの読み込みに失敗: {name}: {e}", file=sys.stderr)

    def _save_index(self):
        """名前→埋め込みファイル名の台帳を保存する。"""
        index = {
            "version": 1,
            "people": {name: self._embedding_file(name).name for name in self._embeddings},
        }
        with open(self._index_file(), "w", encoding="utf-8") as f:
            json.dump(index, f, ensure_ascii=False, indent=2)

    # ------------------------------------------------------------------
    # 検出（YuNet生出力=landmark付き。face_detect.pyと同一モデルを流用）
    # ------------------------------------------------------------------
    def _get_yunet(self, width: int, height: int):
        if not YUNET_MODEL_PATH.exists():
            return None
        if self._yunet is None:
            self._yunet = cv2.FaceDetectorYN.create(
                str(YUNET_MODEL_PATH), "", (width, height),
                score_threshold=0.6, nms_threshold=0.3, top_k=100
            )
        else:
            self._yunet.setInputSize((width, height))
        return self._yunet

    @staticmethod
    def _face_row_from_bbox(x: float, y: float, w: float, h: float) -> np.ndarray:
        """bboxのみ（Haar検出）からYuNet形式の顔行を合成する。
        landmarkは標準テンプレート比率で推定（正面顔想定）。
        形式: [x, y, w, h, l0x, l0y, ..., l4x, l4y, score] の15要素
        """
        row = [x, y, w, h]
        for fx, fy in _BBOX_LANDMARK_FRACTIONS:
            row.extend([x + fx * w, y + fy * h])
        row.append(0.9)
        return np.array(row, dtype=np.float32)

    def _detect_face_rows(self, frame) -> list[np.ndarray]:
        """フレームから顔を検出し、YuNet形式の顔行（15要素: bbox+5landmark+score）のリストを返す。
        YuNetモデル未配置時は face_detect のHaarフォールバックを使い、landmarkをbboxから推定する。
        """
        h, w = frame.shape[:2]
        detector = self._get_yunet(w, h)
        if detector is not None:
            _, faces = detector.detect(frame)
            if faces is None:
                return []
            return [np.asarray(row, dtype=np.float32) for row in faces]

        # フォールバック: face_detect.detect_faces（Haar）+ landmark推定
        from camera.face_detect import detect_faces
        print("[FaceRecognizer] YuNetモデル未配置: Haar検出+landmark推定で代替", file=sys.stderr)
        return [
            self._face_row_from_bbox(d["x"], d["y"], d["w"], d["h"])
            for d in detect_faces(frame)
        ]

    # ------------------------------------------------------------------
    # 埋め込み
    # ------------------------------------------------------------------
    def _embed(self, frame, face_row: np.ndarray) -> np.ndarray:
        """検出済み顔行（bbox+landmark）からSFace埋め込み（128次元 float32）を計算する。"""
        aligned = self._sface.alignCrop(frame, face_row)
        feature = self._sface.feature(aligned)
        return np.asarray(feature, dtype=np.float32).reshape(-1)  # (128,)

    @staticmethod
    def _cosine(a: np.ndarray, b: np.ndarray) -> float:
        denom = float(np.linalg.norm(a) * np.linalg.norm(b))
        if denom == 0.0:
            return 0.0
        return float(np.dot(a, b) / denom)

    @staticmethod
    def _largest_face(rows: list[np.ndarray]) -> np.ndarray:
        return max(rows, key=lambda r: float(r[2]) * float(r[3]))

    # ------------------------------------------------------------------
    # 公開API（LBPH版と同一シグネチャ）
    # ------------------------------------------------------------------
    def register(self, image_frame, name: str, extra_frames: list = None) -> bool:
        """
        image_frame（numpy array）から顔埋め込みを計算して保存する。
        成功: True / 顔が検出できなかった: False
        登録後はメモリ内のデータも更新する。

        extra_frames: 追加フレームのリスト（optional）。
            渡すと全フレームから埋め込みを計算してまとめて保存。
            メインフレームから顔が検出できなくても、extra_framesから検出できれば登録成功。
        既存名への再登録は追記（複数フレームぶんの埋め込みを蓄積。上限あり・新しいものを優先）。
        """
        all_frames = [image_frame]
        if extra_frames:
            all_frames.extend(extra_frames)

        new_embeddings = []
        for frame in all_frames:
            rows = self._detect_face_rows(frame)
            if not rows:
                continue
            # 各フレームにつき、最大面積の顔のみ採用（複数人いる場合は無視）
            row = self._largest_face(rows)
            new_embeddings.append(self._embed(frame, row))

        if not new_embeddings:
            print(f"[FaceRecognizer] 顔が検出できませんでした（{name}）")
            return False

        new_mat = np.stack(new_embeddings).astype(np.float32)
        if name in self._embeddings:
            new_mat = np.concatenate([self._embeddings[name], new_mat], axis=0)
        # 上限超過分は古いものから捨てる
        if new_mat.shape[0] > MAX_EMBEDDINGS_PER_PERSON:
            new_mat = new_mat[-MAX_EMBEDDINGS_PER_PERSON:]
        self._embeddings[name] = new_mat

        np.savez_compressed(self._embedding_file(name), embeddings=new_mat)
        self._save_index()

        print(f"[FaceRecognizer] {name} を登録しました"
              f"（新規埋め込み={len(new_embeddings)}, 保持数={new_mat.shape[0]}）")
        return True

    def identify(self, image_frame) -> str | None:
        """
        image_frame（numpy array）から顔を識別して名前を返す。
        一致: 人物名（str） / 不明: "unknown" / 顔なし・未登録: None
        複数人いる場合は最大面積の顔を優先。判定は登録埋め込みとの最良一致（最大cosine）。
        """
        if not self._embeddings:
            return None

        rows = self._detect_face_rows(image_frame)
        if not rows:
            return None

        row = self._largest_face(rows)
        w = float(row[2])
        if w < MIN_FACE_WIDTH:
            print(f"[FaceRecognizer] 顔が小さすぎるためスキップ（w={w:.0f}px < {MIN_FACE_WIDTH}px）")
            return None

        query = self._embed(image_frame, row)

        best_name = None
        best_score = -1.0
        for name, emb in self._embeddings.items():
            score = max(self._cosine(query, e) for e in emb)
            if score > best_score:
                best_score = score
                best_name = name

        print(f"[FaceRecognizer] 識別結果: best={best_name}, cosine={best_score:.3f} "
              f"(threshold={SFACE_COSINE_THRESHOLD})", file=sys.stderr)

        if best_score >= SFACE_COSINE_THRESHOLD:
            return best_name
        return "unknown"

    def list_registered(self) -> list[str]:
        """登録済みの人物名リストを返す。"""
        return list(self._embeddings.keys())

    def delete(self, name: str) -> bool:
        """指定した人物のデータを削除する。
        SFaceは人物ごとに埋め込みファイルが独立しているため、
        該当ファイルの削除だけで完結する（他の登録者への影響なし）。
        """
        if name not in self._embeddings:
            return False

        del self._embeddings[name]
        emb_file = self._embedding_file(name)
        if emb_file.exists():
            emb_file.unlink()
        self._save_index()

        print(f"[FaceRecognizer] {name} のデータを削除しました。残り: {list(self._embeddings.keys())}")
        return True
