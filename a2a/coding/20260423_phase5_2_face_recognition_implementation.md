# Phase 5.2：顔認識 + person-wiki 実装指示書

**作成日**: 2026-04-23
**担当**: コーディング担当AI（Antigravity等）
**依存**: Phase 5.1完了（✅ 済み）
**ハードウェア追加**: なし（ソフトウェアのみ）

---

## 概要・目的

「誰が来たかを知っている」がくこまを実現する。

現在の `face_detect.py` は Haar Cascade で顔の**位置だけ**検出する。これを顔の**識別**（誰か）に昇格させ、呼びかけ・person-wiki更新まで自動化する。

---

## 現在の実装（変更ベース）

| ファイル | 現状 |
|---|---|
| `camera/face_detect.py` | Haar Cascade で顔の座標を返すだけ |
| `look_at_user.py` | 顔座標を使ってサーボ追跡するだけ（識別なし） |
| `memory/wiki/people/` | 学長・そのさん・ソータ等のページ存在（手動作成） |
| `brain/memory_processor.py` | OFFLINE処理でwiki更新する仕組みが存在 |

---

## ファイル構成（新規作成・変更対象）

```
/home/tukapontas/gakukoma/
├── camera/
│   ├── face_detect.py          （変更なし・そのまま使用）
│   ├── face_recognizer.py      ★ 新規（識別・登録クラス）
│   └── face_data/              ★ 新規ディレクトリ
│       └── {人物名}.npy        # 128次元顔ベクトル（face_recognitionライブラリ）
├── look_at_user.py             ★ 変更（識別結果を返すように）
├── brain/
│   ├── gakukoma_brain.py       ★ 変更（register_face ツール追加・look_at_user結果拡張）
│   └── memory_processor.py     ★ 変更（person-wiki「最後に会った日」等の自動更新）
└── memory/
    └── wiki/people/            （既存・OFFLINE処理で自動更新）
```

---

## Task A: face_recognition ライブラリのインストール確認

### A-1: インストール手順

```bash
# ビルド依存パッケージ（aarch64で dlib のビルドに必要）
sudo apt install -y cmake python3-dev libopenblas-dev liblapack-dev

# dlib（Pi5 aarch64でソースビルド。10〜30分かかる場合あり）
pip3 install dlib

# face_recognition（dlibのラッパー）
pip3 install face_recognition
```

### A-2: 動作確認

```bash
python3 -c "import face_recognition; print('face_recognition OK')"
```

### A-3: インストール失敗時の代替方針

`dlib` のビルドが失敗する場合：

**代替A**: pip3 の `--extra-index-url` でprebuilt wheelを試みる
```bash
pip3 install dlib --extra-index-url https://pypi.ngc.nvidia.com
```

**代替B**: OpenCV の LBPH 顔認識（精度は落ちるが Pi5 で確実に動く）
```python
# face_recognizer.py の内部実装を LBPH ベースにする
recognizer = cv2.face.LBPHFaceRecognizer_create()
```

`dlib` が動いた場合は `face_recognition` ライブラリ、動かない場合は OpenCV LBPH を使うこと。**どちらを採用したかを完了報告書に記載**。

以降の指示は `face_recognition` ライブラリ前提で記述するが、LBPH で実装した場合も同じインターフェイス（後述）を維持すること。

---

## Task B: 顔認識クラス実装

### B-1: `camera/face_recognizer.py` 新規作成

```python
"""
顔認識クラス。顔の登録・識別・データ管理を行う。

- ライブラリ: face_recognition（dlib利用）
  - LBPH代替の場合は内部実装を差し替えるが、公開インターフェイスは変えないこと
- データ保存: camera/face_data/{name}.npy（128次元float64ベクトル）
- 識別閾値: tolerance=0.55（デフォルト0.6より厳しめ）
"""

FACE_DATA_DIR = Path("/home/tukapontas/gakukoma/camera/face_data")

class FaceRecognizer:
    def __init__(self):
        """FACE_DATA_DIRを作成し、既存の顔データを全ロードする。"""
        ...

    def register(self, image_frame, name: str) -> bool:
        """
        image_frame（numpy array）から顔エンコーディングを取得して保存する。
        成功: True / 顔が検出できなかった or 複数顔ある: False
        保存先: FACE_DATA_DIR / f"{name}.npy"
        登録後はメモリ内のデータも更新すること。
        """
        ...

    def identify(self, image_frame) -> str | None:
        """
        image_frame（numpy array）から顔を識別して名前を返す。
        一致: 人物名（str） / 不明: "unknown" / 顔なし: None
        複数人いる場合は最大面積の顔を優先。
        """
        ...

    def list_registered(self) -> list[str]:
        """登録済みの人物名リストを返す。"""
        ...

    def delete(self, name: str) -> bool:
        """指定した人物のデータを削除する。"""
        ...
```

---

## Task C: `look_at_user.py` への識別統合

### C-1: 変更概要

現在の `look_at_user.py` はサーボ追跡が完了したら `"顔追跡成功"` を print して終了する。

これを変更して：
- 追跡成功後に `FaceRecognizer.identify()` を呼ぶ
- 結果を JSON で stdout に出力する（Brain がパースして使う）

### C-2: 出力フォーマット変更

```python
# 変更前（末尾）
if success:
    print(f"顔追跡成功: pan={final_pan}° tilt={final_tilt}°")
else:
    print("タイムアウト: 顔が見つかりませんでした")

# 変更後
import json

if success:
    # 最後のフレームで識別
    recognizer = FaceRecognizer()
    person_name = recognizer.identify(last_frame)  # last_frame を保持しておくこと
    result = {
        "success": True,
        "pan": final_pan,
        "tilt": final_tilt,
        "identified": person_name  # "学長" / "unknown" / None
    }
else:
    result = {
        "success": False,
        "identified": None
    }

print(json.dumps(result, ensure_ascii=False))
```

**注意**: `last_frame` を保持するため、サーボ収束時のフレームを変数に保存しておくこと。

### C-3: gakukoma_brain.py の `look_at_user` 結果処理を更新

`/home/tukapontas/gakukoma/brain/gakukoma_brain.py` の `look_at_user` ツール実行部分で、stdout をパースして識別結果を Brain に渡す：

```python
# look_at_user ツール実行後
output = subprocess.run([...], capture_output=True, text=True).stdout.strip()
try:
    result = json.loads(output)
    if result.get("success"):
        identified = result.get("identified")
        if identified and identified != "unknown":
            tool_result = f"{identified}を認識した"
        elif identified == "unknown":
            tool_result = "知らない人がいる（未登録）"
        else:
            tool_result = "顔が見つからなかった"
    else:
        tool_result = "顔が見つからなかった"
except (json.JSONDecodeError, KeyError):
    tool_result = output  # フォールバック: 旧形式
```

---

## Task B-2: 顔登録ツール追加

### `register_face` ツールを gakukoma_brain.py に追加

**ツール定義:**

```python
{
    "name": "register_face",
    "description": "目の前にいる人の顔を登録する。「がくこま、これが〇〇だよ」のように人物名を指示された時に呼ぶ。カメラで撮影→顔ベクトル保存→以降look_at_userで名前認識できるようになる。",
    "input_schema": {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "登録する人物の名前（例: 学長、そのさん）"
            }
        },
        "required": ["name"]
    }
}
```

**ツール実行ハンドラ（`_execute_tool()` 内）:**

```python
elif tool_name == "register_face":
    name = tool_input.get("name", "")
    if not name:
        tool_result = "名前が指定されていない"
    else:
        # カメラでキャプチャ
        from camera.capture import CameraCapture
        from camera.face_recognizer import FaceRecognizer
        cam = CameraCapture(device_id=0)
        frame = cam.capture()
        cam.release()
        if frame is None:
            tool_result = "カメラから画像を取得できなかった"
        else:
            recognizer = FaceRecognizer()
            ok = recognizer.register(frame, name)
            if ok:
                tool_result = f"{name}の顔を登録した"
            else:
                tool_result = "顔が検出できなかった（正面を向いて）"
```

**PRIMING_EXAMPLES への追加:**

```
学長: がくこま、これが学長だよ。
がくこま: （register_face: 学長）わかった！学長の顔を覚えたよ。次から名前で呼べるようになる。

学長: 誰かいる？
がくこま: （look_at_user）学長がいるね！
```

**SOUL.md への追記（ツール使用方針）:**

```markdown
- 「これが〇〇だよ」と人物紹介されたら `register_face` を呼んで顔を登録する
- `look_at_user` を呼んだとき、識別できた相手には名前で呼びかける
```

---

## Task D: person-wiki の自動更新（memory_processor.py 変更）

### D-1: 変更概要

`memory_processor.py` の OFFLINE処理に、RAWログから人物言及を検出して `wiki/people/{name}.md` を更新する処理を追加する。

**既存フロー（変更なし）**: RAWログ → Haiku分析 → wiki/index.md更新 + wiki/places/更新 + core_memories.md更新

**追加処理**: Haiku分析結果から人物別の「最近の話題」「最後に会った日」を抽出 → `wiki/people/{name}.md` に追記

### D-2: person-wiki ページのフォーマット

`/home/tukapontas/gakukoma/memory/wiki/people/{name}.md` の標準フォーマット:

```markdown
# {name}

- 初めて会った日: YYYY-MM-DD
- 最後に会った日: YYYY-MM-DD（自動更新）
- 関係性: （例: 製作者・養親）
- 最近の話題:
  - YYYY-MM-DD: [話題メモ]
- 行動パターン:
  （Haikuが推論・週次更新）
- がくこまの印象:
  （Haikuが感情スコアを基に更新）
```

### D-3: `_update_person_wiki()` 関数を追加

`memory_processor.py` の `run()` 関数から呼ぶ新関数:

```python
def _update_person_wiki(client: anthropic.Anthropic, wiki_dir: Path, raw_logs: str, date: str):
    """
    RAWログに登場した人物を特定し、wiki/people/各ページを更新する。

    処理手順:
    1. Haikuに「このログに登場した人物と、その人との出来事を抽出してJSON返せ」と依頼
    2. JSON結果を基に wiki/people/{name}.md の「最後に会った日」「最近の話題」を更新
    3. ページが存在しない人物は新規作成（初めて会った日=今日）

    JSONスキーマ（Haikuに返させる形式）:
    {
      "people": [
        {
          "name": "学長",
          "last_seen": "2026-04-23",
          "recent_topic": "リビングを一緒に探索した",
          "impression": "優しく楽しい人"  // optional
        }
      ]
    }
    """
    ...
```

---

## Task E: 統合テスト

### T-1: ライブラリ動作確認

```bash
python3 -c "import face_recognition; print('OK')"
# または OpenCV LBPH の場合
python3 -c "import cv2; r=cv2.face.LBPHFaceRecognizer_create(); print('LBPH OK')"
```

### T-2: 顔登録テスト

```
学長: 「がくこま、これが学長だよ」
期待: register_face を呼び「学長の顔を覚えたよ」と返答
確認: camera/face_data/学長.npy が作成されている
```

### T-3: 顔識別テスト（登録済み）

```
学長: 「誰かいる？」
期待: look_at_user を呼び「学長がいるね！」と名前付きで返答
確認: look_at_user の出力 JSON に "identified": "学長" が含まれている
```

### T-4: 未登録人物のテスト

```
未登録の人物が前に立つ
学長: 「誰かいる？」
期待: 「知らない人がいる」と返答（名前は言わない）
```

### T-5: 複数セッションを経た自動更新テスト

```
1. がくこまと数ターン会話する（RAWログに記録）
2. memory_processor.py を手動実行
3. wiki/people/学長.md に「最後に会った日」と「最近の話題」が更新されている
```

### T-6: 再起動後の識別継続テスト

```
1. がくこまを再起動する
2. 「誰かいる？」と話しかける
3. 再起動後も顔データが維持されており名前で認識できる
```

### T-7: look_at_user 後の呼びかけテスト

```
学長: 「がくこま、誰か来た？」
期待: look_at_user → "学長を認識した" → Brainが「学長、こんにちは！」と呼びかける
```

---

## 実装上の注意事項

1. **識別精度と速度のトレードオフ**: `face_recognition` はHaar Cascadeより重い。識別処理（`identify()`）は `look_at_user` のサーボ収束後に1回だけ実行すること（毎フレームでは実行しない）。

2. **顔が小さい場合**: Pi5のカメラから遠い場合、顔のROIが小さく識別精度が落ちる。`identify()` で顔サイズが小さすぎる場合（例: w < 60px）は識別をスキップして `None` を返す実装にすること。

3. **`__del__` 禁止**: `FaceRecognizer` に `__del__` を実装しないこと。

4. **gakukoma_brain.py の FaceRecognizer インスタンス**: 毎回インスタンス生成は重い。`register_face` と `look_at_user` の識別処理から共有で使えるよう、`gakukoma_brain.py` の `__init__` で1回だけ初期化する。

5. **look_at_user.py の後方互換性**: `look_at_user.py` の出力を JSON に変更するため、旧形式の plain text を期待している箇所がある場合はそちらも更新すること。`try/except json.JSONDecodeError` でフォールバック済みなので問題ない。

6. **face_data ディレクトリのパーミッション**: `/home/tukapontas/gakukoma/camera/face_data/` は `mkdir -p` で作成し、権限は `755` でよい。

---

完了報告書: `coding/20260423_phase5_2_face_recognition_completed.md`
