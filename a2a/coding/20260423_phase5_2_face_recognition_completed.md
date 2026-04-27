# Phase 5.2：顔認識 + person-wiki 実装 完了報告書

**作成日**: 2026-04-23
**担当**: コーディング担当AI（ClaudeCode サブエージェント）
**ステータス**: 実装完了・構文確認済み・実機テスト要

---

## 採用ライブラリ

**OpenCV LBPH（cv2.face.LBPHFaceRecognizer）**

`dlib` の pip3 インストールを試みたが、ビルド依存パッケージのダウンロード中にネットワーク切断エラー（Connection reset by peer）が発生し、ビルドが完了しなかった。

OpenCV LBPH は `python3 -c "import cv2; cv2.face.LBPHFaceRecognizer_create(); print('OK')"` で動作確認済み。指示書 Task A-3 代替Bの方針に従い LBPH で実装。

**トレードオフ**: face_recognition（dlib）の128次元ベクトルより精度が落ちる可能性があるが、Pi5 aarch64 で確実に動作する。

---

## 作成・変更したファイルの一覧

| ファイル | 種別 | 変更内容 |
|---|---|---|
| `/home/tukapontas/gakukoma/camera/face_recognizer.py` | **新規作成** | FaceRecognizer クラス（LBPH実装）|
| `/home/tukapontas/gakukoma/camera/face_data/` | **新規作成** | 顔データ保存ディレクトリ（FaceRecognizer init時に自動作成）|
| `/home/tukapontas/gakukoma/look_at_user.py` | **変更** | FaceRecognizer統合・JSON出力対応 |
| `/home/tukapontas/gakukoma/brain/gakukoma_brain.py` | **変更** | register_faceツール追加・look_at_user JSON解析・FaceRecognizer初期化 |
| `/home/tukapontas/gakukoma/brain/memory_processor.py` | **変更** | `_update_person_wiki()` 追加・`analyze_and_update_wiki()` から呼び出し |

---

## 実装上の判断事項

### 1. face_data のデータ形式変更（指示書との差分）

指示書では `{name}.npy`（128次元float64ベクトル）を保存する設計だったが、LBPH採用のためデータ形式を変更：

- `camera/face_data/_model.yml` — LBPHモデルファイル（全登録者を1ファイルで管理）
- `camera/face_data/_labels.txt` — `label_int \t 人物名` のマッピング（タブ区切りテキスト）

1ファイルに統合することで、LBPHの `update()` API（追加学習）を利用できる。

### 2. delete() の仕様

LBPHはモデルから特定ラベルのみ削除する標準APIがない。`delete()` を呼ぶと `_model.yml` を削除し、残りの登録者が失われる。delete後は全員を再登録する必要があることをログに出力する（削除は破壊的操作）。

実用上は delete よりも上書き登録（同名で再登録）を推奨。

### 3. look_at_user.py のFaceRecognizer利用

指示書では「gakukoma_brain.py の `__init__` で1回だけ初期化して共有」と指定されているが、`look_at_user.py` はサブプロセスとして別プロセスで起動されるため、Brain側のFaceRecognizerインスタンスと共有できない。

`look_at_user.py` ではサーボ収束後に1回 `FaceRecognizer()` をインスタンス化して識別を行う。モデルファイルからの読み込みのため毎回の初期化コストは最小限。

Brain側の `self._face_recognizer` は `register_face` ツールの実行時のみ使用。

### 4. memory_processor.py の `import re` 配置

`_update_person_wiki()` 内で `import re` をローカルインポートにした（既存ファイルのトップレベルに `re` のインポートがなかったため、関数スコープで取り込み）。

### 5. PRIMING_EXAMPLESの末尾の `\n\n` を修正

既存の末尾 `\n\n` が削除されていたため、新規追加の例文の後に `\n\n` を付けて後方互換を維持した。

---

## 統合テスト T-1〜T-7 確認結果

### T-1: ライブラリ動作確認

```
python3 -c "import cv2; r=cv2.face.LBPHFaceRecognizer_create(); print('LBPH OK')"
→ LBPH OK ✅
```

### T-2: 顔登録テスト（「がくこま、これが学長だよ」）

**実機テスト要**（カメラデバイス必須）

構文確認: `register_face` ツールの定義・ハンドラ・Brainへのツール定義追加を確認済み ✅

### T-3: 顔識別テスト（登録済み）

**実機テスト要**（登録データが必要）

JSON出力フォーマット確認:
```python
result = {"success": True, "pan": 90, "tilt": 90, "identified": "学長"}
json.dumps(result, ensure_ascii=False)
# → '{"success": true, "pan": 90, "tilt": 90, "identified": "学長"}' ✅
```

### T-4: 未登録人物のテスト

**実機テスト要**

LBPH threshold 70.0 での識別: `confidence >= 70.0` の場合 "unknown" を返す実装確認済み ✅

### T-5: 複数セッションを経た自動更新テスト

**実機テスト要**（RAWログが必要）

`_update_person_wiki()` の関数定義・`analyze_and_update_wiki()` からの呼び出し（Step 6として追加）を確認済み ✅

### T-6: 再起動後の識別継続テスト

**実機テスト要**

モデルファイル（`_model.yml`、`_labels.txt`）はディスクに永続化。`FaceRecognizer.__init__()` で自動ロードする実装を確認済み ✅

### T-7: look_at_user 後の呼びかけテスト

**実機テスト要**（カメラ・サーボ必須）

`_execute_tool` の look_at_user 結果パース処理確認済み:
- `identified = "学長"` → `"学長を認識した"` を返す ✅
- `identified = "unknown"` → `"知らない人がいる（未登録）"` を返す ✅
- `identified = None` → `"顔が見つからなかった"` を返す ✅

---

## 申し送り事項（実機テストで確認すべき点）

### 1. LBPH識別閾値の調整（重要）

実装では `LBPH_THRESHOLD = 70.0` を採用しているが、これは経験的な初期値。実機で実際に登録・識別を繰り返して調整が必要。

- 誤識別が多い（知らない人を既知と判定）→ 閾値を下げる（例: 50.0）
- 未識別が多い（登録済みの人を unknown と判定）→ 閾値を上げる（例: 85.0）

`/home/tukapontas/gakukoma/camera/face_recognizer.py` の `LBPH_THRESHOLD` を変更。

### 2. 登録サンプル数の増加

LBPHは1枚の画像で学習するが、複数角度・表情で `register()` を複数回呼ぶと精度が上がる（同じ名前で複数回登録すると `update()` で追加学習される）。

### 3. delete() 後の再登録フロー

前述の通り、`delete()` を呼ぶとモデルが失われる。実運用では delete を使わず、上書き登録（同名で再登録）で対応することを推奨。

### 4. look_at_user.py のFaceRecognizer初期化コスト

現在は `look_at_user.py` 実行のたびに `FaceRecognizer()` をインスタンス化してディスクからモデルをロードする。登録者が増えると若干の遅延が生じる可能性がある。実機で許容範囲か確認すること。

### 5. PRIMING_EXAMPLES の動作確認

顔認識の対話例（register_face / look_at_user → 名前呼びかけ）をPRIMINGに追加した。Haikuが適切にツールを使うかどうか、実機会話で確認すること。

### 6. person-wiki 自動更新（_update_person_wiki）の重複問題

既存の `analyze_and_update_wiki()` の Step 3 でも `people_mentioned` を基に `people/` ページを更新している。新規追加の `_update_person_wiki()` は「最後に会った日」と「最近の話題」の簡易更新に特化しているため、両者が同一ページを更新することになる。

実機テストで重複・矛盾が発生しないか確認すること。問題があれば Step 3 の更新と統合を検討。
