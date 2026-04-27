# 指示書: sing_song ツール実装

**日付**: 2026-04-24
**担当**: gakukoma-coder（Claudeサブエージェント）
**優先度**: 中（Phase 5 並行タスク）

---

## 概要

GAKUKOMAが歌を歌えるようにする。LLMが音符列をその場で生成して `sing_song` ツールを呼び出す設計により、事前に曲をハードコードする必要はない。演奏中は首を自動的に左右に振る。

---

## 変更ファイル一覧

| ファイル | 操作 |
|---|---|
| `gakukoma/tools/sing_song.py` | 新規作成 |
| `gakukoma/tools/sing_song.sh` | 新規作成 |
| `gakukoma/brain/gakukoma_brain.py` | 更新（TOOLS / _execute_tool / SYSTEM_PROMPT / PRIMING） |

---

## Task 1: `gakukoma/tools/sing_song.py` 新規作成

### 仕様

- 引数1: JSON文字列（音符リスト、後述フォーマット）
- 引数2: tempo倍率（float、省略時=1.0。例: 1.5=1.5倍速）
- numpy + sounddevice でsin波を生成して再生（追加インストール不要）
- 演奏と並行して、別スレッドで首を左右に振る
- 演奏終了後に首を正面に戻す

### 音符フォーマット（JSON）

```json
[
  {"freq": 261.6, "duration": 0.5},
  {"freq": 293.7, "duration": 0.5},
  {"freq": 0,     "duration": 0.25},
  ...
]
```

- `freq`: 周波数Hz（0または省略 = 休符）
- `duration`: 拍の長さ（秒）。tempo倍率で割る。

### sin波生成の仕様

```python
sample_rate = 44100
t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)
wave = 0.5 * np.sin(2 * np.pi * freq * t)
# エンベロープ（クリックノイズ防止）: 先頭・末尾5msをフェードイン/アウト
```

- 各音符を順番に `sounddevice.play()` + `sounddevice.wait()` で再生
- 休符（freq=0）は無音 `np.zeros()` を再生（duration分の間隔）

### 首振り仕様（別スレッド）

- `threading.Thread` で並行実行
- `PanTiltController` を直接インポートして使う（shスクリプト経由しない）
- パターン: **1.0秒周期で left → front → right → front を繰り返す**
  - pan値: left=130, front=90, right=50（config.yamlのpan_min/max/offsetに依存しないハードコード値）
  - tiltは変えない（現在の角度を維持）
- 演奏終了後にスレッドを停止し `look_center()` で正面に戻す

### エラーハンドリング

- sounddevice / numpy が import できない場合: "sounddeviceまたはnumpyが利用できない" を標準出力に出力して終了
- PanTiltController が使えない場合: 首振りなしで音だけ再生（エラーにしない）
- JSON パースエラー: "notes JSONが不正" を出力して終了

### 出力（標準出力）

```
演奏完了（N音符, X.X秒）
```

---

## Task 2: `gakukoma/tools/sing_song.sh` 新規作成

```bash
#!/bin/bash
# 使用方法: sing_song.sh '<notes_json>' [tempo]
# 例: sing_song.sh '[{"freq":261.6,"duration":0.5}]' 1.0

NOTES="${1:-[]}"
TEMPO="${2:-1.0}"
python3 /home/tukapontas/gakukoma/tools/sing_song.py "$NOTES" "$TEMPO"
```

- 実行権限: `chmod +x`

---

## Task 3: `gakukoma/brain/gakukoma_brain.py` 更新

### 3-1. TOOLS リストに追加

```python
{
    "name": "sing_song",
    "description": "音符列を受け取って歌を演奏する。演奏中は首を左右に振る。"
                   "notesにはfreq（Hz）とduration（秒）のリストを渡す。"
                   "freq=0は休符。公共ドメインの曲は自分で音符を生成して渡す。"
                   "自作メロディも可。",
    "input_schema": {
        "type": "object",
        "properties": {
            "notes": {
                "type": "array",
                "description": "音符リスト。例: [{\"freq\": 261.6, \"duration\": 0.5}, ...]",
                "items": {
                    "type": "object",
                    "properties": {
                        "freq":     {"type": "number", "description": "周波数Hz（0=休符）"},
                        "duration": {"type": "number", "description": "長さ（秒）"}
                    },
                    "required": ["freq", "duration"]
                }
            },
            "tempo": {
                "type": "number",
                "description": "テンポ倍率（1.0=標準、1.5=1.5倍速。省略時=1.0）"
            }
        },
        "required": ["notes"]
    }
},
```

### 3-2. `_execute_tool` の dispatch に追加

```python
"sing_song": [
    str(tools_dir / "sing_song.sh"),
    json.dumps(inp.get("notes", []), ensure_ascii=False),
    str(inp.get("tempo", 1.0)),
],
```

`subprocess.run` の `timeout` は演奏時間に対して余裕を持たせる必要がある。現状の `timeout=30` では長い曲が途中で切れる可能性があるため、`sing_song` のみ `timeout=120` にする。

dispatch dict を使った単純な `subprocess.run` ではtimeoutを個別指定できないため、`_execute_tool` 内でif分岐を追加する：

```python
if name == "sing_song":
    cmd = dispatch[name]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    return result.stdout.strip() or "完了"
```

（dispatch dictから取り出したあと、通常の実行ブロックに入る前にこのif分岐を挿入する）

### 3-3. SYSTEM_PROMPT に追加

「探索・巡回・見回しなどの開放的な指示」の段落の後に追加：

```
歌を歌う指示（「うたって」「歌って」「ハッピーバースデーうたって」など）は、sing_songツールを使う。
公共ドメインの曲（ハッピーバースデー、きらきら星、チューリップ、かえるのうた等）は自分で音符を生成して渡す。
「なんか歌って」「悲しい曲うたって」など曲名指定なしの場合は自作メロディを生成して渡す。
歌の前後にspeak_textで一言添えてよい（「歌うよ」「はいどうぞ」など短く）。
```

### 3-4. PRIMING_EXAMPLES に追加

`PRIMING_EXAMPLES` の末尾（最後の改行の前）に追加：

```python
"ガクチョ: ハッピーバースデーうたって。\n"
"がくこま: （sing_song: [{\"freq\":261.6,\"duration\":0.25},{\"freq\":261.6,\"duration\":0.25},{\"freq\":293.7,\"duration\":0.5},{\"freq\":261.6,\"duration\":0.5},{\"freq\":349.2,\"duration\":0.5},{\"freq\":329.6,\"duration\":1.0},...] tempo:1.0）歌ったよ！\n"
"ガクチョ: なんか歌って。\n"
"がくこま: （sing_song: 自作メロディの音符列）作ってみたよ。こんな感じ。\n"
```

---

## テスト手順

以下をユーザーが口頭でがくこまに伝えて確認する：

| # | テスト内容 | 期待結果 |
|---|---|---|
| T-1 | 「ハッピーバースデーうたって」 | ハッピーバースデーのメロディが流れ、演奏中に首が左右に振れる |
| T-2 | 「きらきら星うたって」 | きらきら星のメロディが流れる |
| T-3 | 「なんか歌って」 | 自作メロディが流れる |
| T-4 | 「速めで歌って」 | tempo > 1.0 で演奏が速くなる |
| T-5 | 演奏終了後 | 首が正面に戻る |
| T-6 | 「悲しい感じの曲うたって」 | 短調系のメロディが流れる |

---

## 注意事項

- `sounddevice` はVADで既使用のため追加インストール不要。ただし `numpy` の確認を `import numpy` で先に行うこと
- PanTiltController の `release()` を演奏中に呼ばないこと（サーボが脱力する。過去の不具合事例あり）
- `__del__` を PanTiltController に追加しないこと（I2Cバスが切断される。過去の不具合事例あり）
- sing_song.py の首振りスレッドは `daemon=True` にすること（プロセス終了時に確実に停止させる）
- サーボの `look_direction` や `set_pan_tilt` は既存のfcntlロック（`/tmp/gakukoma_servo.lock`）を使うため、sing_song.py内で直接PanTiltControllerを使う場合もロックを考慮すること。ただし首振りはsin_song.py内部で完結するのでロック競合はほぼ発生しない（演奏中に別ツールからサーボが呼ばれる状況はない）
