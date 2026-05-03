# 顔認識改善：Haar Cascade → YuNet換装 + 多フレーム登録 完了報告書

**作成日**: 2026-05-03
**担当**: コーディング担当AI（gakukoma-coder）+ ClaudeCode（Bash/テスト）
**ステータス**: 実装完了・全テストPASS

---

## 変更したファイル

| ファイル | 変更内容 |
|---|---|
| `camera/face_detect.py` | Haar Cascade → YuNet（cv2.FaceDetectorYN）に換装。モデル未配置時はHaarフォールバック |
| `camera/face_recognizer.py` | 内部検出をYuNet共有化・`register()`に`extra_frames`追加・LBPH_THRESHOLD 165.0→110.0 |
| `brain/gakukoma_brain.py` | `register_face`ハンドラで15フレーム収集→多フレーム登録 |
| `camera/models/face_detection_yunet_2023mar.onnx` | YuNet ONNXモデル新規配置（228KB） |

---

## 実装の詳細

### face_detect.py（YuNet換装）

- `cv2.FaceDetectorYN.create()` でモデルをロード、モジュールレベル `_detector` でキャッシュ
- `score_threshold=0.6`, `nms_threshold=0.3` で検出
- YuNetモデルファイルが存在しない場合は従来のHaar Cascadeにフォールバック（後方互換）
- 公開インターフェイス `detect_faces()` の戻り値フォーマット `[{"x","y","w","h","cx","cy"}]` は変更なし

### face_recognizer.py

- `_detect_faces()` を `face_detect.detect_faces()` の呼び出しに変更（YuNetを共有利用）
- 不要になった `_get_cascade()` と `self._cascade` を削除
- `register(image_frame, name, extra_frames=None)` にパラメータ追加。`extra_frames` が渡された場合は全フレームから顔ROIを抽出してLBPH学習（サンプル数を増やす）
- `LBPH_THRESHOLD` を 165.0 → **110.0** に変更（YuNet換装により検出品質が向上するため）

### gakukoma_brain.py（register_face）

- ウォームアップ3フレーム → 0.1秒間隔で15フレーム収集 → `register(frames[0], name, extra_frames=frames[1:])`
- 実質サンプル数: 最大15フレーム × 9バリエ = 最大135サンプル（従来: 1フレーム × 9 = 9サンプル）

---

## 統合テスト結果

### T-1: YuNet動作確認

```
モデルパス: /home/tukapontas/gakukoma/camera/models/face_detection_yunet_2023mar.onnx
モデル存在: True
YuNet detector初期化: OK
黒画像での検出数（0が正常）: 0
→ PASS
```

### T-2: FaceRecognizer初期化

```
LBPH_THRESHOLD: 110.0
FaceRecognizer初期化: OK
登録済み: ['学長']
→ PASS
```

### T-3: extra_framesパラメータ

```
register()シグネチャ: (self, image_frame, name: str, extra_frames: list = None) -> bool
extra_frames パラメータ存在: True
→ PASS
```

### T-4: gakukoma_brain.py register_face

```
register_face 多フレーム実装: OK
15フレーム収集ループ: OK
→ PASS
```

### T-5: face_detect.py実装確認

```
YuNet使用: OK
Haarフォールバック: OK
モジュールキャッシュ: OK
インターフェイス維持: OK
→ PASS
```

### T-6（実機テスト要）

カメラ前で `look_at_user.py` を実行し識別が安定することを実機で確認すること。

---

## 申し送り事項

### LBPH_THRESHOLD の実機調整

初期値は110.0に設定したが、実機で調整が必要：
- 既存の「学長」データは旧Haar Cascade + 1フレーム × 9バリエで学習済み
- **再登録推奨**: `register_face` ツールで再度登録すると、YuNet検出 + 15フレーム × 9バリエの良質なサンプルで上書きされ精度が大幅に上がる
- 識別できない場合（confidence高め）→ `LBPH_THRESHOLD` を上げる（例: 130）
- 誤識別が多い場合 → `LBPH_THRESHOLD` を下げる（例: 90）

### 実機テスト手順

```bash
# look_at_user 単体テスト
cd /home/tukapontas/gakukoma
python3 look_at_user.py
# → {"success": true, "pan": ..., "tilt": ..., "identified": "学長" or "unknown"} が出力されればOK
```

---

## 今回未実施の改善案（問題が続く場合の次の手）

今回の YuNet換装 + 多フレーム登録で解決しない場合、以下を順番に検討すること。

### 次の手 1（優先度: 中）: 閾値の実測ベース調整

現在の閾値110.0は経験的な値。実機で実際の confidence 値を計測してから最適値を決める。

```bash
# confidence 値をリアルタイムで確認するデバッグ実行
# face_recognizer.py の identify() 内の stderr 出力を見る
cd /home/tukapontas/gakukoma
python3 look_at_user.py 2>&1 | grep "識別結果"
# → "[FaceRecognizer] 識別結果: label=0, confidence=85.3" のように出力される
```

- 登録済み人物が正面にいる時の confidence 値を記録する
- その値の1.2倍程度を `LBPH_THRESHOLD` に設定するのが目安
- `camera/face_recognizer.py` の `LBPH_THRESHOLD = 110.0` を変更するだけでよい

---

### 次の手 2（優先度: 中）: 累積サンプル保存方式への移行（Dotchy方式）

現在は `update()` で追加学習するが、古いサンプルはモデル内に埋もれる。Dotchy方式は生の画像ファイルをセッションIDごとにディレクトリで管理し、再訓練時に全サンプルを使い直す。

**実装概要:**
- `camera/face_data/{name}/sessions/{timestamp}/*.png` に顔画像を保存
- `register()` 呼び出しのたびに新しいセッションとして保存（上書きしない）
- `retrain()` メソッドを追加: 全セッションの画像を読み込んで `self._recognizer.train()` を実行
- 再登録するほど精度が上がっていく設計

**指示書作成先**: `coding/YYYYMMDD_face_recognition_accumulate_samples_implementation.md`

---

### 次の手 3（優先度: 低）: face_recognition（dlib）への再挑戦

dlib の128次元ベクトルは LBPH より根本的に精度が高い。Pi5 aarch64 向け prebuilt wheel が将来提供された場合は換装を検討する。

```bash
# 現時点での試行（依然ビルドに失敗する可能性が高い）
pip3 install dlib --extra-index-url https://pypi.ngc.nvidia.com
python3 -c "import dlib; print(dlib.__version__)"
```

成功した場合は `face_recognizer.py` の内部実装を差し替えるだけで済む（公開インターフェイスは変えない設計になっている）。
