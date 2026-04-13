# 指示書：Phase 2.1 首振り方向指示ツール実装

作成日: 2026-03-17
作成者: ClaudeCode（司令塔）
担当: Antigravity
完了報告先: `/home/tukapontas/a2a/coding/20260317_phase2_1_look_direction_completed.md`

---

## 概要

がくこまが「右を向く」「上を見る」などの方向指示で首を動かせるようにする。
`look_at_user()`（顔追跡）とは独立したツールとして2つ追加する。

| ツール | 機能 |
|---|---|
| `look_direction(direction)` | 方向名（front/right/left/up/down等）でサーボを動かす |
| `set_pan_tilt(pan, tilt)` | 絶対角度（パン0〜180°、チルト60〜120°）でサーボを動かす |

---

## 環境情報

- 既存サーボファイル: `/home/tukapontas/gakukoma/servo/pan_tilt.py`（**これを拡張する**）
- ツールディレクトリ: `/home/tukapontas/gakukoma/tools/`
- 設定ファイル: `/home/tukapontas/gakukoma/voice_loop/config.yaml`
- OpenClaw TOOLS.md: `~/.openclaw/workspace/TOOLS.md`
- OpenClaw SOUL.md: `~/.openclaw/workspace/SOUL.md`
- サーボ角度制限（config.yaml参照）: パン 0〜180°、チルト 60〜120°

---

## タスク1：`pan_tilt.py` への2メソッド追加

`/home/tukapontas/gakukoma/servo/pan_tilt.py` の `PanTiltController` クラスに以下を追記する。

### `look_direction(direction: str)` メソッド

```python
def look_direction(self, direction: str) -> str:
    """方向名でパン・チルトを動かす

    対応する direction 文字列:
      front / center / 正面 / 中央 → pan=90, tilt=90
      right / 右                   → pan=45, tilt=90
      left / 左                    → pan=135, tilt=90
      up / 上                      → pan=90,  tilt=60
      down / 下                    → pan=90,  tilt=120
      upper-right / 右上           → pan=45,  tilt=60
      upper-left / 左上            → pan=135, tilt=60
      lower-right / 右下           → pan=45,  tilt=120
      lower-left / 左下            → pan=135, tilt=120

    戻り値: "look_direction成功: pan=X° tilt=Y°" または "look_direction失敗: 未知の方向 '<direction>'"
    """
    direction_map = {
        "front": (90, 90), "center": (90, 90), "正面": (90, 90), "中央": (90, 90),
        "right": (45, 90), "右": (45, 90),
        "left": (135, 90), "左": (135, 90),
        "up": (90, 60), "上": (90, 60),
        "down": (90, 120), "下": (90, 120),
        "upper-right": (45, 60), "右上": (45, 60),
        "upper-left": (135, 60), "左上": (135, 60),
        "lower-right": (45, 120), "右下": (45, 120),
        "lower-left": (135, 120), "左下": (135, 120),
    }
    key = direction.lower().strip()
    if key not in direction_map and direction.strip() not in direction_map:
        return f"look_direction失敗: 未知の方向 '{direction}'"
    pan, tilt = direction_map.get(key) or direction_map.get(direction.strip())
    self.set_pan(pan)
    self.set_tilt(tilt)
    self.release()
    return f"look_direction成功: pan={pan}° tilt={tilt}°"
```

### `set_pan_tilt(pan: float, tilt: float)` メソッド

```python
def set_pan_tilt(self, pan: float, tilt: float) -> str:
    """絶対角度でパン・チルトを指定する

    pan: 0〜180°（範囲外はクランプ）
    tilt: 60〜120°（範囲外はクランプ）

    戻り値: "set_pan_tilt成功: pan=X° tilt=Y°"
    """
    self.set_pan(int(pan))
    self.set_tilt(int(tilt))
    self.release()
    return f"set_pan_tilt成功: pan={self.current_pan}° tilt={self.current_tilt}°"
```

**注意**: `set_pan()` / `set_tilt()` は既存のクランプ処理を通るので、範囲外の値は自動的に制限される。

---

## タスク2：`look_at_user()` との競合防止

`pan_tilt.py` に排他ロックを追加する。

```python
import threading

class PanTiltController:
    def __init__(self, ...):
        ...
        self._lock = threading.Lock()

    def look_direction(self, direction: str) -> str:
        if not self._lock.acquire(blocking=False):
            return "look_direction失敗: 他の操作が実行中です"
        try:
            # ... 既存の処理 ...
        finally:
            self._lock.release()

    def set_pan_tilt(self, pan: float, tilt: float) -> str:
        if not self._lock.acquire(blocking=False):
            return "set_pan_tilt失敗: 他の操作が実行中です"
        try:
            # ... 既存の処理 ...
        finally:
            self._lock.release()
```

`look_at_user.py` の追跡ループ中もこのロックを取得するよう修正すること（`look_at_user.py` を確認・必要であれば修正）。

---

## タスク3：OpenClaw用シェルスクリプトの作成

### `/home/tukapontas/gakukoma/tools/look_direction.sh`

```bash
#!/bin/bash
# 使用方法: look_direction.sh <direction>
# 例: look_direction.sh right

DIRECTION="${1:-front}"
cd /home/tukapontas/gakukoma
python3 -c "
import sys
sys.path.insert(0, '/home/tukapontas/gakukoma')
from servo.pan_tilt import PanTiltController
ctrl = PanTiltController()
result = ctrl.look_direction('${DIRECTION}')
print(result)
"
```

### `/home/tukapontas/gakukoma/tools/set_pan_tilt.sh`

```bash
#!/bin/bash
# 使用方法: set_pan_tilt.sh <pan_angle> <tilt_angle>
# 例: set_pan_tilt.sh 45 90

PAN="${1:-90}"
TILT="${2:-90}"
cd /home/tukapontas/gakukoma
python3 -c "
import sys
sys.path.insert(0, '/home/tukapontas/gakukoma')
from servo.pan_tilt import PanTiltController
ctrl = PanTiltController()
result = ctrl.set_pan_tilt(${PAN}, ${TILT})
print(result)
"
```

両ファイルに実行権限を付与:
```bash
chmod +x /home/tukapontas/gakukoma/tools/look_direction.sh
chmod +x /home/tukapontas/gakukoma/tools/set_pan_tilt.sh
```

---

## タスク4：OpenClaw TOOLS.md への追記

`~/.openclaw/workspace/TOOLS.md` の末尾に以下を追記する:

```markdown
---

## GAKUKOMA Servo Direction Tools（Phase 2.1追加）

### look_direction
- コマンド: `/home/tukapontas/gakukoma/tools/look_direction.sh "<方向>"`
- 機能: 指定した方向にカメラ（首）を向ける
- 引数: 方向文字列（下記いずれか）
  - `front` または `center`（正面・中央）
  - `right`（右）、`left`（左）
  - `up`（上）、`down`（下）
  - `upper-right`（右上）、`upper-left`（左上）
  - `lower-right`（右下）、`lower-left`（左下）
  - 日本語でも可: `右`、`左`、`上`、`下`、`正面`、`右上`、`左上` 等
- 戻り値: `look_direction成功: pan=X° tilt=Y°` または エラーメッセージ
- 備考: `look_at_user` 実行中は競合を避けるためブロックされる

### set_pan_tilt
- コマンド: `/home/tukapontas/gakukoma/tools/set_pan_tilt.sh <pan角度> <tilt角度>`
- 機能: パン・チルトを絶対角度で指定する（精密制御用）
- 引数: パン角度（0〜180）、チルト角度（60〜120）
- 戻り値: `set_pan_tilt成功: pan=X° tilt=Y°`
- 備考: 範囲外の値は自動でクランプされる
```

---

## タスク5：OpenClaw SOUL.md への追記

`~/.openclaw/workspace/SOUL.md` の能力・できることを記述している箇所に以下を追記:

```markdown
- 自発的な視線移動が可能（look_direction で右・左・上・下・正面等を向ける）
- 精密な首の向き制御が可能（set_pan_tilt で角度直接指定）
```

---

## テスト項目

完了報告書に全テスト結果を記載すること。

| # | テスト | 合格条件 |
|---|---|---|
| T-7 | look_direction 単体（全方向） | front/right/left/up/down の各方向でサーボが正しく動くこと |
| T-8 | set_pan_tilt 単体 | 指定角度にサーボが移動すること（クランプ確認含む） |
| T-9 | 日本語方向名 | `右`・`左`・`上`・`下` 等でも動作すること |
| T-10 | OpenClaw統合 | 「右を向いて」の発話で look_direction が呼ばれサーボが動くこと |
| T-11 | 範囲外クランプ | pan=200, tilt=200 を指定しても安全に動作すること |
| T-12 | 競合防止 | ロック取得中に別呼び出しをするとエラーメッセージが返ること |

---

## 完了報告書に含めること

- T-7〜T-12 の全テスト結果
- `look_at_user.py` にロック対応を追加したかどうか（したなら変更内容）
- TOOLS.md / SOUL.md の更新内容（追記した文章）
- 問題点・工夫した点

---

## 申し送り

- `pan_tilt.py` の既存の `set_pan()` / `set_tilt()` はクランプ済みなので、追加メソッドはそれを呼び出すだけでよい
- `release()` は各操作の末尾に呼ぶ（サーボのトルクを抜いて発熱・電流節約）
- `look_at_user.py` の場所: `/home/tukapontas/gakukoma/look_at_user.py`
