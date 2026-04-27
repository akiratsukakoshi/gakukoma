# Phase 5.3 Task B〜F：場所記憶 + エンコーダー活用 実装指示書

**作成日**: 2026-04-23
**担当**: コーディング担当AI（Antigravity等）
**依存**:
- Task B（オドメトリ）: Task A（エンコーダー配線）完了後に実施
- Task C〜E: Task A と並行して先に実装可能（エンコーダー不要）
- Task F: Task A〜E 全て完了後

---

## 概要・目的

「ここ来たことある」と言えるがくこまを実現する。

1. `remember_place` ツール: 脳（gakukoma_brain.py）が任意のタイミングで場所を記録できる
2. オドメトリ: エンコーダーパルスから移動距離・方向を推定し場所ノード間のエッジとして記録
3. SQLiteトポロジカルマップ: 場所ノードと遷移エッジを管理
4. OFFLINE更新: memory_processor.py が places wiki を自動更新
5. 再訪時の参照: ONLINE時に wiki から「前回ここで〇〇だった」を参照できる

---

## ファイル構成（新規作成・変更対象）

```
/home/tukapontas/gakukoma/
├── motor/
│   ├── encoder.py                   ★ 新規（Task B: エンコーダーカウンター）
│   └── odometry.py                  ★ 新規（Task B: オドメトリ計算）
├── brain/
│   ├── gakukoma_brain.py            ★ 変更（Task C: remember_place/recall_place ツール追加）
│   ├── memory_processor.py          ★ 変更（Task E: 場所wiki更新処理追加）
│   └── place_recorder.py            ★ 新規（Task C: 場所記述・SQLite保存）
└── memory/
    ├── wiki/
    │   └── places/                  （既存・自動更新）
    └── places.db                    ★ 新規（Task D: SQLiteトポロジカルマップ）
```

---

## Task C: 場所記述スクリプト（先行実施可・エンコーダー不要）

### C-1: `place_recorder.py` 新規作成

`/home/tukapontas/gakukoma/brain/place_recorder.py`

```python
"""
場所記録モジュール。
- see_around() で撮影した画像をHaikuで場所描写テキストに変換
- SQLiteのplacesテーブルに保存
- wiki/places/[name].md を更新
"""
```

**実装要件:**

```python
import sqlite3
import subprocess
import json
import anthropic
from pathlib import Path
from datetime import datetime

MEMORY_DIR = Path("/home/tukapontas/gakukoma/memory")
DB_PATH = MEMORY_DIR / "places.db"
WIKI_PLACES_DIR = MEMORY_DIR / "wiki/places"
SEE_AROUND_SCRIPT = "/home/tukapontas/gakukoma/tools/see_around.sh"
OPENCLAW_CONFIG = "/home/tukapontas/.openclaw/openclaw.json"

class PlaceRecorder:
    def __init__(self):
        self._init_db()

    def record_current_place(self, place_name: str) -> str:
        """
        1. see_around.py を呼び出して現在地の写真を撮影
        2. Haiku に「この場所を200文字で描写してください」と依頼
        3. SQLite の nodes テーブルに保存（初回は INSERT、再訪は visited_count+1・last_visited更新）
        4. wiki/places/[place_name].md を更新
        5. 結果テキストを返す（Brain が speak_text できるように）
        """
        ...

    def recall_place(self, place_name: str) -> str:
        """
        wiki/places/[place_name].md を読んで内容を返す。
        ファイルが存在しない場合は「まだ行ったことがない場所」と返す。
        """
        ...

    def get_all_known_places(self) -> list[dict]:
        """
        SQLiteから全場所ノードを取得して返す（name, visited_count, last_visited）
        """
        ...
```

### C-2: SQLiteスキーマ（Task D兼用）

`places.db` に以下2テーブルを作成:

```sql
-- 場所ノード
CREATE TABLE IF NOT EXISTS nodes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,         -- 場所名（日本語OK）
    description TEXT,                  -- Haikuが生成した200文字描写
    created_at TEXT NOT NULL,          -- ISO8601
    last_visited TEXT NOT NULL,        -- ISO8601
    visited_count INTEGER DEFAULT 1
);

-- 遷移エッジ（オドメトリ）
CREATE TABLE IF NOT EXISTS edges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    from_node TEXT NOT NULL,
    to_node TEXT NOT NULL,
    direction TEXT,                    -- 'forward'/'left'/'right'/'backward'
    distance_pulses INTEGER DEFAULT 0, -- エンコーダーパルス数（Task B実装後に使用）
    recorded_at TEXT NOT NULL          -- ISO8601
);
```

### C-3: wiki/places/[name].md のフォーマット

```markdown
# [place_name]

- 最初に訪れた日: YYYY-MM-DD
- 最後に訪れた日: YYYY-MM-DD（自動更新）
- 訪問回数: N回
- 場所の描写:
  [Haikuが生成した200文字描写]
- 関連する出来事:
  - YYYY-MM-DD: [出来事メモ（OFFLINE処理で追記）]
```

---

## Task B: エンコーダーオドメトリ（Task A完了後に実施）

**※ Task A完了報告書で確定したGPIOアサインを使うこと**

### B-1: `encoder.py` 新規作成

`/home/tukapontas/gakukoma/motor/encoder.py`

```python
"""
エンコーダーパルスカウンター。
gpiozero の Button を使いエッジ検出でカウントする。
Pi5 対応: LGPIOFactory を使用（pigpiod は不要）。
スレッドセーフなカウンター実装。
"""
import threading
from gpiozero import Button
from gpiozero.pins.lgpio import LGPIOFactory
import gpiozero

gpiozero.Device.pin_factory = LGPIOFactory()

class EncoderCounter:
    """
    左右モーターのエンコーダーパルスをカウントする。

    - left_gpio, right_gpio: Task A完了報告書で確定したGPIO番号（int）
    - pull_up: Task A完了報告書の仕様に従う（True/False）
    - reset(): カウンターを0にリセット
    - get_counts() -> (left: int, right: int): 現在のカウント値を返す
    """
    ...
```

### B-2: `odometry.py` 新規作成

`/home/tukapontas/gakukoma/motor/odometry.py`

```python
"""
オドメトリ計算。エンコーダーパルスから移動距離を推定する。

設定値（config.yaml の odometry セクションに追加）:
  pulses_per_rotation: 20     # 1回転あたりのパルス数（Task A実測値）
  wheel_circumference_mm: 200 # タイヤ周長mm（実測値を入れること）
"""

class Odometry:
    def estimate_distance_mm(self, pulses: int) -> float:
        """パルス数→移動距離mm"""
        ...

    def record_move(self, direction: str, left_pulses: int, right_pulses: int):
        """
        move_robot()の1回分の移動を記録。
        PlaceRecorder.record_edge() で edges テーブルに保存する。
        """
        ...
```

### B-3: config.yaml へのオドメトリ設定追加

`/home/tukapontas/gakukoma/voice_loop/config.yaml` に追加:

```yaml
# オドメトリ設定（Phase 5.3追加）
odometry:
  left_encoder_gpio: 5          # Task A完了報告書の値に変更すること
  right_encoder_gpio: 11        # Task A完了報告書の値に変更すること
  encoder_pull_up: true         # Task A完了報告書の値に変更すること
  pulses_per_rotation: 20       # Task A実測値に変更すること
  wheel_circumference_mm: 200   # 実測値（タイヤ1周の長さ）
```

### B-4: `motor_driver.py` へのオドメトリ統合

`/home/tukapontas/gakukoma/motor/motor_driver.py` を変更し、移動中にエンコーダーをカウント:

- move_robot() 開始前に `encoder.reset()`
- 移動完了後に `encoder.get_counts()` を取得
- オドメトリデータを返す（または `place_recorder.record_edge()` に渡す）

**注意**: `motor_driver.py` に `__del__` を追加しないこと。

---

## Task C追加: Brainへのツール登録

`/home/tukapontas/gakukoma/brain/gakukoma_brain.py` を変更:

### 新ツール定義追加（TOOLS リストに追加）

```python
{
    "name": "remember_place",
    "description": "今いる場所を記録する。see_aroundで撮影→LLMで描写→SQLite+wikiに保存する。場所名を引数に取る（日本語OK）。探索後や初めて来た場所で呼ぶとよい。",
    "input_schema": {
        "type": "object",
        "properties": {
            "place_name": {
                "type": "string",
                "description": "記録する場所の名前（例: リビング、廊下、台所）"
            }
        },
        "required": ["place_name"]
    }
},
{
    "name": "recall_place",
    "description": "以前行ったことがある場所の記憶を引き出す。場所名を引数に取る。",
    "input_schema": {
        "type": "object",
        "properties": {
            "place_name": {
                "type": "string",
                "description": "思い出したい場所の名前"
            }
        },
        "required": ["place_name"]
    }
},
{
    "name": "list_known_places",
    "description": "これまでに訪れて記憶している場所の一覧を返す。",
    "input_schema": {
        "type": "object",
        "properties": {}
    }
}
```

### ツール実行ハンドラ追加（`_execute_tool()` メソッド内）

```python
elif tool_name == "remember_place":
    place_name = tool_input.get("place_name", "不明な場所")
    result = self._place_recorder.record_current_place(place_name)
    # result: "〇〇を記録したよ。[描写テキスト]" のような文字列

elif tool_name == "recall_place":
    place_name = tool_input.get("place_name", "")
    result = self._place_recorder.recall_place(place_name)

elif tool_name == "list_known_places":
    places = self._place_recorder.get_all_known_places()
    if places:
        result = "覚えている場所: " + "、".join([p["name"] for p in places])
    else:
        result = "まだどこも記録していない"
```

### PlaceRecorder の初期化（`__init__` に追加）

```python
from .place_recorder import PlaceRecorder
self._place_recorder = PlaceRecorder()
```

### SOUL/PRIMING への追記

`/home/tukapontas/.openclaw/workspace/SOUL.md` の「ツール使用方針」セクションに追記:

```markdown
- 初めて来た場所・探索後は `remember_place` を呼んで記憶に刻む
- 「ここ前にも来たっけ？」と思ったら `recall_place` で確認する
```

PRIMING_EXAMPLES（`gakukoma_brain.py` の `_PRIMING_EXAMPLES`）に追加:

```
学長: 台所まで行ってきて。
がくこま: （move_robot: forward 3秒）（remember_place: 台所）台所に来たよ。シンクと電子レンジが見える場所だ。覚えたよ。
```

---

## Task E: memory_processor.py への場所wiki更新統合

`/home/tukapontas/gakukoma/brain/memory_processor.py` を変更:

### OFFLINE処理にSQLite→wiki同期を追加

既存の `run()` 関数末尾（または既存のwiki更新処理の後）に追加:

```python
def _sync_places_wiki_from_db(wiki_dir: Path):
    """
    places.db の全ノードを走査し、wiki/places/[name].md を最新に保つ。
    RAWログから該当場所への言及があれば「関連する出来事」に追記する。
    """
    db_path = MEMORY_DIR / "places.db"
    if not db_path.exists():
        return

    conn = sqlite3.connect(str(db_path))
    nodes = conn.execute("SELECT name, description, created_at, last_visited, visited_count FROM nodes").fetchall()
    conn.close()

    places_dir = wiki_dir / "places"
    places_dir.mkdir(exist_ok=True)

    for name, description, created_at, last_visited, visited_count in nodes:
        page_path = places_dir / f"{name}.md"
        # 既存ページの「関連する出来事」を保持しつつ更新
        existing_events = []
        if page_path.exists():
            content = page_path.read_text(encoding="utf-8")
            # 既存の出来事行を抽出
            in_events = False
            for line in content.split("\n"):
                if line.startswith("- 関連する出来事"):
                    in_events = True
                elif in_events and line.startswith("  - "):
                    existing_events.append(line)
                elif in_events and line.startswith("- "):
                    in_events = False

        # ページを書き直す
        events_str = "\n".join(existing_events) if existing_events else "  （まだ記録なし）"
        page_content = f"""# {name}

- 最初に訪れた日: {created_at[:10]}
- 最後に訪れた日: {last_visited[:10]}
- 訪問回数: {visited_count}回
- 場所の描写:
  {description or '（まだ描写なし）'}
- 関連する出来事:
{events_str}
"""
        page_path.write_text(page_content, encoding="utf-8")

    print(f"places wiki同期完了: {len(nodes)}件")
```

---

## Task F: 統合テスト

### T-1: 基本的な場所記録

```
学長: 「がくこま、今いる場所を『がくこまの部屋』として覚えて」
期待: remember_place を呼び、見回して描写→「覚えたよ」と返答
確認: memory/places.db に nodes レコードが追加されている
確認: memory/wiki/places/がくこまの部屋.md が更新されている
```

### T-2: 場所の想起

```
学長: 「リビングってどんな場所だっけ？」
期待: recall_place("リビング") を呼び、wikiの内容を基に答える
確認: 以前の描写内容が含まれた返答になっている
```

### T-3: 場所一覧

```
学長: 「これまでどこに行ったっけ？」
期待: list_known_places を呼び、知っている場所を列挙
確認: SQLiteに登録されている場所が全て含まれている
```

### T-4: 移動＋場所記録の連携

```
学長: 「少し前進して、その場所を『廊下』として覚えて」
期待: move_robot → remember_place → 描写・保存 → 報告
確認: 廊下のページがwikiに新規作成されている
```

### T-5: 再訪の認識（オドメトリなし版）

```
学長: 「廊下に戻って、覚えているか確認して」
期待: recall_place("廊下") で以前の描写を参照し「前に来たことあるよ」と応答
```

### T-6: OFFLINE処理との連携

```
手動でmemory_processor.pyを実行
確認: places.dbの内容がwiki/places/に正しく反映されている
確認: index.mdの「知っている場所」セクションが最新になっている
```

### T-7: エンコーダーオドメトリ（Task A完了後）

```
タンクを前進3秒 → encoder.get_counts()でパルス数を確認
期待: edges テーブルに from_node・to_node・distance_pulses が記録される
確認: 距離推定値が実測距離と概ね一致する（目安: 誤差20%以内）
```

---

## 実装上の注意事項

1. **`see_around.py` の呼び出し**: `place_recorder.py` から `see_around.sh` を subprocess で呼ぶのではなく、`see_around.py` を直接 import して使う方がエラーハンドリングしやすい。どちらでもよいが一貫させること。

2. **Haiku での場所描写**: `place_recorder.py` の描写生成は claude-haiku-4-5 を使用してコストを抑える。プロンプト例:
   ```
   「以下の写真はロボット「がくこま」が今いる場所です。
   この場所を200文字以内で描写してください。
   がくこまの視点（一人称）で、見えるものの特徴・雰囲気を具体的に。」
   ```

3. **エラーハンドリング**: `record_current_place()` で撮影失敗時は描写なしでDB登録のみ行い、Brainには「撮影できなかったけど場所を記録したよ」と返す。

4. **`__del__` 禁止**: `EncoderCounter` に `__del__` を実装しないこと（他のモジュールと同じルール）。終了処理は `cleanup()` を明示的に呼ぶ設計にすること。

5. **並行実施可能な範囲**:
   - Task C, D, E は Task A（エンコーダー配線）完了前から実装・テスト可能
   - Task B と T-7 のみ Task A 完了後

---

完了報告書: `coding/20260423_phase5_3_place_memory_completed.md`
