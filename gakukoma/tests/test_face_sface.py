#!/usr/bin/env python3
"""WP-F 顔認識SFace化テスト（実カメラ・実顔画像不要）。

合成画像はYuNet顔検出を通らないため、検出はインスタンスの _detect_face_rows を
モックしてバイパスし、「検出済み顔行（bbox+landmark）を与えたときの認識部」を検証する。
ただし SFace の ONNX実ロード・alignCrop・埋め込み計算・cosine判定は実際に動かす。

「人物」は幾何パターンの合成画像で代用する（決定的・実顔画像なし）:
  - 同心円パターン ≒ 人物A（明度違い・ブラー違いを同一人物の別フレームとする。
    SFace埋め込みのcosineは約0.88と高く、同一判定になる）
  - 左右白黒パターン ≒ 人物B（Aとのcosineは約0.04で閾値0.363未満＝別人）
  - 横縞パターン ≒ 未登録者（A/Bとのcosineは約0.18/-0.07で閾値未満）
  ※上記cosine値は事前に実測済み。全画像が決定的生成のため再現する。
    閾値0.363に対して最悪ケースでも約0.18のマージンを確保した組み合わせを選定。

検証項目:
  (a) register→identify が同一人物を返す（extra_frames込み・別インスタンス再ロード込み）
  (b) 未登録顔で unknown、未登録状態・顔なしで None
  (c) delete後に identify が該当者を返さない（他の登録者は影響なし）
  (d) 旧LBPHファイル（_model.yml/_labels.txt）が lbph_backup/ へ退避される（ダミーで検証）

テスト用データはすべて tempfile.TemporaryDirectory 内に作り、終了時に完全削除する。
実行: python3 gakukoma/tests/test_face_sface.py
"""
import os
import sys
import tempfile
from pathlib import Path

sys.dont_write_bytecode = True  # __pycache__ を残さない

# tests/ の親ディレクトリ = コードルート(camera/・brain/ 等がある階層)
CODE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, CODE_ROOT)

import cv2  # noqa: E402
import numpy as np  # noqa: E402

from camera import face_recognizer as fr_mod  # noqa: E402
from camera.face_recognizer import FaceRecognizer  # noqa: E402

H, W = 240, 320
_YY, _XX = np.mgrid[0:H, 0:W]

# 検出済み顔行（bbox+5landmark+score）。モック検出が常にこれを返す
FACE_ROW = FaceRecognizer._face_row_from_bbox(80.0, 40.0, 160.0, 160.0)


# ---------------------------------------------------------------------------
# 合成「人物」画像（すべて決定的生成）
# ---------------------------------------------------------------------------
def img_circle() -> np.ndarray:
    """人物A: 同心円パターン"""
    p = np.zeros((H, W, 3), np.uint8)
    r = np.sqrt((_XX - W / 2) ** 2 + (_YY - H / 2) ** 2)
    p[..., 1] = ((r // 10) % 2 * 255).astype(np.uint8)
    p[..., 0] = 128
    return p


def img_half() -> np.ndarray:
    """人物B: 左右白黒パターン"""
    p = np.zeros((H, W, 3), np.uint8)
    p[:, W // 2:] = 255
    return p


def img_hstripe() -> np.ndarray:
    """未登録者: 横縞パターン"""
    p = np.zeros((H, W, 3), np.uint8)
    p[..., 2] = ((_YY // 12) % 2 * 255).astype(np.uint8)
    return p


def brighten(img: np.ndarray, delta: int) -> np.ndarray:
    return np.clip(img.astype(np.int16) + delta, 0, 255).astype(np.uint8)


def make_recognizer(rows=None) -> FaceRecognizer:
    """検出をモックした FaceRecognizer を作る。
    rows=None なら常に FACE_ROW を1件検出。rows=[] なら常に検出なし。
    """
    rec = FaceRecognizer()
    if rows is None:
        rec._detect_face_rows = lambda frame: [FACE_ROW.copy()]
    else:
        rec._detect_face_rows = lambda frame: [r.copy() for r in rows]
    return rec


# ---------------------------------------------------------------------------
# テストランナー
# ---------------------------------------------------------------------------
_results = []


def check(name: str, cond: bool, detail: str = ""):
    _results.append((name, cond))
    mark = "PASS" if cond else "FAIL"
    suffix = f"  ({detail})" if detail else ""
    print(f"[{mark}] {name}{suffix}")


def run_tests(data_dir: Path):
    fr_mod.FACE_DATA_DIR = data_dir

    # --- (d) 旧LBPHファイルの退避 -----------------------------------------
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "_model.yml").write_text("dummy lbph model\n", encoding="utf-8")
    (data_dir / "_labels.txt").write_text("0\tだれか\n", encoding="utf-8")

    rec = make_recognizer()
    backup = data_dir / "lbph_backup"
    check("d1: 旧_model.ymlがface_data直下から消える", not (data_dir / "_model.yml").exists())
    check("d2: 旧_labels.txtがface_data直下から消える", not (data_dir / "_labels.txt").exists())
    check("d3: lbph_backup/_model.yml に退避（内容保持）",
          (backup / "_model.yml").exists()
          and (backup / "_model.yml").read_text(encoding="utf-8") == "dummy lbph model\n")
    check("d4: lbph_backup/_labels.txt に退避（内容保持）",
          (backup / "_labels.txt").exists()
          and (backup / "_labels.txt").read_text(encoding="utf-8") == "0\tだれか\n")

    # --- (b) 未登録状態: identify は None ---------------------------------
    check("b1: 登録0件のidentifyはNone", rec.identify(img_circle()) is None)
    check("b2: 初期のlist_registeredは空", rec.list_registered() == [])

    # --- (a) register→identify --------------------------------------------
    circle = img_circle()
    ok = rec.register(circle, "たろう",
                      extra_frames=[brighten(circle, -15), cv2.GaussianBlur(circle, (5, 5), 0)])
    check("a1: register(たろう, extra_frames付き)がTrue", ok)
    ok = rec.register(img_half(), "はなこ")
    check("a2: register(はなこ)がTrue", ok)
    check("a3: list_registeredに2人", sorted(rec.list_registered()) == ["たろう", "はなこ"])

    probe = brighten(circle, 18)  # 登録に使っていない同一人物の別フレーム
    got = rec.identify(probe)
    check("a4: 同一人物の別フレームでidentify=たろう", got == "たろう", f"got={got!r}")
    got = rec.identify(img_half())
    check("a5: identify(左右白黒)=はなこ", got == "はなこ", f"got={got!r}")

    # 埋め込みの実体確認（ONNX実ロード・128次元）
    emb = rec._embeddings["たろう"]
    check("a6: 埋め込みは(フレーム数,128)のfloat32",
          emb.shape == (3, 128) and emb.dtype == np.float32, f"shape={emb.shape}")

    # --- (b) 未登録顔: unknown ---------------------------------------------
    got = rec.identify(img_hstripe())
    check("b3: 未登録顔でidentify=unknown", got == "unknown", f"got={got!r}")

    # --- 永続化: 別インスタンスで再ロード ----------------------------------
    rec2 = make_recognizer()
    check("p1: 再ロード後もlist_registeredに2人",
          sorted(rec2.list_registered()) == ["たろう", "はなこ"])
    got = rec2.identify(probe)
    check("p2: 再ロード後もidentify=たろう", got == "たろう", f"got={got!r}")

    # --- (c) delete ---------------------------------------------------------
    check("c1: delete(たろう)がTrue", rec2.delete("たろう"))
    check("c2: delete後のlist_registeredにたろうがいない",
          rec2.list_registered() == ["はなこ"])
    got = rec2.identify(probe)
    check("c3: delete後のidentifyがたろうを返さない（unknown）", got == "unknown", f"got={got!r}")
    got = rec2.identify(img_half())
    check("c4: 他の登録者(はなこ)は削除の影響を受けない", got == "はなこ", f"got={got!r}")
    check("c5: 存在しない名前のdeleteはFalse", rec2.delete("そんざいしない") is False)
    npz_count = len(list(data_dir.glob("sface_*.npz")))
    check("c6: 埋め込みファイルも1件だけ残る", npz_count == 1, f"count={npz_count}")

    # --- 検出なし・小顔 ------------------------------------------------------
    rec3 = make_recognizer(rows=[])
    check("n1: 顔なしのidentifyはNone", rec3.identify(img_circle()) is None)
    check("n2: 顔なしのregisterはFalse", rec3.register(img_circle(), "だれか") is False)

    small_row = FaceRecognizer._face_row_from_bbox(10.0, 10.0, 20.0, 20.0)  # w=20 < MIN_FACE_WIDTH
    rec4 = make_recognizer(rows=[small_row])
    check("n3: 小さすぎる顔のidentifyはNone", rec4.identify(img_circle()) is None)

    # --- メインフレーム検出失敗でもextra_framesで登録成功 ---------------------
    rec5 = FaceRecognizer()
    black = np.zeros((H, W, 3), np.uint8)
    rec5._detect_face_rows = (
        lambda frame: [] if frame.max() == 0 else [FACE_ROW.copy()]
    )
    ok = rec5.register(black, "じろう", extra_frames=[img_hstripe()])
    check("x1: メイン検出失敗でもextra_framesで登録成功", ok)
    got = rec5.identify(img_hstripe())
    check("x2: extra_frames由来の埋め込みでidentify=じろう", got == "じろう", f"got={got!r}")


def main():
    saved_dir = fr_mod.FACE_DATA_DIR
    with tempfile.TemporaryDirectory(prefix="test_face_sface_") as tmp:
        try:
            run_tests(Path(tmp) / "face_data")
        finally:
            fr_mod.FACE_DATA_DIR = saved_dir

    passed = sum(1 for _, ok in _results if ok)
    failed = len(_results) - passed
    print(f"\n結果: {passed} passed, {failed} failed / {len(_results)} checks")
    if failed:
        sys.exit(1)
    print("ALL PASS")


if __name__ == "__main__":
    main()
