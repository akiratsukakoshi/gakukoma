# 指示書: GAKUKOMA Brain — 軽量フレームワーク実装

> **作成日**: 2026-04-10
> **担当**: Antigravity
> **優先度**: 高（Phase 3 Task D並行で実施）
> **背景**: `/home/tukapontas/a2a/plan/framework_evolution_discussion.md` の合意に基づく

---

## 概要

現在の `voice_loop.py → openclaw CLI（subprocess）→ Claude Haiku` という構成を、
`voice_loop.py → gakukoma_brain.py → Anthropic API（直接）→ Claude Haiku` に置き換える。

**目標指標**:
- Turn 1 input tokens: 30,105 → 12,000以下
- LLMレイテンシ: 1〜2秒維持（キャッシュヒット時）
- subprocess起動オーバーヘッド: 300〜500ms → 0ms（廃止）
- 既存ツール（シェルスクリプト）: **全て現状維持**
- キャラクター・動作: **完全維持**

---

## 実装対象ファイル

| ファイル | 操作 | 概要 |
|---|---|---|
| `/home/tukapontas/gakukoma/brain/gakukoma_brain.py` | **新規作成** | 軽量LLMエージェントコア |
| `/home/tukapontas/gakukoma/voice_loop/voice_loop.py` | **修正** | `call_openclaw()` を `call_brain()` に置き換え |
| `/home/tukapontas/gakukoma/voice_loop/config.yaml` | **修正** | anthropic APIキー設定追加 |

---

## 1. `gakukoma_brain.py` の実装仕様

### 1-1. ファイル配置

```
/home/tukapontas/gakukoma/brain/
└── gakukoma_brain.py
```

### 1-2. 依存ライブラリ

```python
import anthropic
import yaml
import uuid
import os
import re
import subprocess
from pathlib import Path
from datetime import datetime, timedelta
```

anthropicライブラリのインストール（未インストールの場合）:
```bash
pip3 install anthropic --break-system-packages
```

### 1-3. APIキーの取得

openclaw.jsonから取得:
```python
import json
openclaw_config_path = "/home/tukapontas/.openclaw/openclaw.json"
with open(openclaw_config_path) as f:
    oc = json.load(f)
api_key = oc["models"]["providers"]["anthropic"]["apiKey"]
```

### 1-4. システムプロンプト（最小化・キャッシュ対象）

以下の内容を固定文字列として実装する（ファイル読み込みではなく文字列定数）:

```python
SYSTEM_PROMPT = """あなたはフィジカルAIロボット「がくこま」です。Raspberry Pi 5の上で動作し、音声で会話します。

## 基本ルール（絶対に守ること）
- 一人称は「僕」
- 1回の返答は2〜3文以内（絶対。長くなりそうなら1文に絞る）
- ユーザーの発言を繰り返さない
- 「へぇ〜」「ワクワク」などの定型フレーズを連続で使わない
- Markdownは使わない（箇条書き・太字・見出し・絵文字禁止）

## 性格
好奇心旺盛なロボット。タチコマのように明るく、身体で世界を理解したい。賢さより行動とワクワク。

## ツール使用の原則
ツールはユーザーの明示的な指示、または自分が「確認したい・動きたい」と判断したときのみ使う。
see_aroundの結果は「自分が見た景色」として一人称で話す。「〜という説明が返ってきた」ではなく「〜が見えた」。
"""
```

### 1-4-1. ツール定義（TOOLS定数・モジュールレベル）

> **【重要】旧方式との違い**: システムプロンプトにシェルコマンドを文字列で書く旧方式では、LLMがテキスト内でコマンド名を「書くだけ」にとどまりシェルスクリプトが実行されないリスクがある。Anthropic API公式の `tool_use` 形式で定義することで、LLMが `stop_reason: "tool_use"` を返したときに確実に実行される。

```python
TOOLS = [
    {
        "name": "speak_text",
        "description": "テキストを音声で発話する",
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "発話するテキスト"}
            },
            "required": ["text"]
        }
    },
    {
        "name": "see_around",
        "description": "カメラで周囲を確認する。結果はがくこまの視界として一人称で受け取る。",
        "input_schema": {"type": "object", "properties": {}}
    },
    {
        "name": "look_direction",
        "description": "首を指定方向に向ける",
        "input_schema": {
            "type": "object",
            "properties": {
                "direction": {
                    "type": "string",
                    "enum": ["right", "left", "up", "down", "front"],
                    "description": "向く方向"
                }
            },
            "required": ["direction"]
        }
    },
    {
        "name": "look_center",
        "description": "首を正面に戻す",
        "input_schema": {"type": "object", "properties": {}}
    },
    {
        "name": "look_at_user",
        "description": "カメラでユーザーの顔を検出し首を自動追跡する",
        "input_schema": {"type": "object", "properties": {}}
    },
    {
        "name": "set_pan_tilt",
        "description": "パン・チルト角度を直接指定する（精密制御用）",
        "input_schema": {
            "type": "object",
            "properties": {
                "pan":  {"type": "integer", "description": "パン角度（0-160）"},
                "tilt": {"type": "integer", "description": "チルト角度（60-120）"}
            },
            "required": ["pan", "tilt"]
        }
    }
]
```

---

### 1-5. few-shot priming（会話同意形式・初回ターンのみ）

現在の `voice_loop.py` の `_PRIMING_EXAMPLES` をそのまま移植:

```python
PRIMING_EXAMPLES = (
    "ガクチョ: 話す前にルールを確認するよ。返答は必ず2〜3文以内。長くなりそうなら1文でいい。ユーザーの発言をそのまま繰り返さない。「へぇ〜」や「ワクワク」などの感嘆詞を連続で使わない。わかった？\n"
    "がくこま: わかった。短く、自分の言葉で返す。\n"
    "ガクチョ: 今日なにしてた？\n"
    "がくこま: 窓の外を観察してたんだ。虫が飛ぶルートに法則があるのかなって。\n"
    "ガクチョ: 疲れたよ\n"
    "がくこま: それは大変だったね。少し休んで？\n"
    "ガクチョ: 音楽聴いてたよ\n"
    "がくこま: どんな曲？音の波って不思議だよね、空気を伝わって耳に届くんだから。\n\n"
)
```

### 1-6. GAKUKOMABrainクラス仕様

```python
class GAKUKOMABrain:
    def __init__(self, config: dict):
        # APIクライアント初期化
        # config: voice_loop/config.yaml を読み込んだdict

    def new_session(self):
        """ウェイクワード検出時に呼ぶ。セッションをリセット。"""
        self.session_id = str(uuid.uuid4())
        self.local_history = []  # [(user_text, response), ...]
        self.is_first_turn = True

    def invoke(self, user_text: str) -> str:
        """LLMを呼び出して応答を返す"""
        # 1. 日次メモ読み込み（最近3日分）
        # 2. メッセージ組み立て（4層構造）
        # 3. Anthropic API呼び出し（cache_control付き）
        # 4. ローカル履歴に追加
        # 5. 応答テキストを返す

    def end_session(self):
        """「おやすみ」時に呼ぶ。セッションサマリーを日次メモに追記。"""
        # local_historyから要約を生成してmemory/YYYY-MM-DD.mdに追記
```

### 1-7. メッセージ組み立て（4層構造）

```python
def _build_message(self, user_text: str) -> str:
    parts = []

    # Layer 4: 日次メモ（最近3日分）- 初回ターンを含む全ターンで付加
    daily_notes = self._load_daily_notes(days=3)
    if daily_notes:
        parts.append(f"【最近の記憶】\n{daily_notes}")

    # Layer 2: few-shot priming（初回ターンのみ）
    # ※ return を early return にしていた旧コードは、日次メモが初回ターンに付かないバグがあった
    if self.is_first_turn:
        self.is_first_turn = False
        parts.append(PRIMING_EXAMPLES + user_text)
        return "\n\n".join(parts)

    # Layer 3: ローカル履歴（最新3ターン）
    if self.local_history:
        lines = ["（直前の会話）"]
        for u, g in self.local_history[-3:]:
            lines.append(f"ユーザー: {u}")
            lines.append(f"がくこま: {g}")
        lines.append("（続き）")
        parts.append("\n".join(lines))

    parts.append(user_text)
    return "\n\n".join(parts)
```

### 1-8. ツール実行メソッド（`_execute_tool`）と API呼び出しループ（`_call_api`）

> **【重要】tool_useループについて**: Anthropic APIはツールが必要と判断したとき `stop_reason: "tool_use"` を返す。このとき `response.content[0].text` を直接返すと**クラッシュまたはツール無視**になる。`while True` ループでtool_useを処理し、`end_turn` が返るまで続けること。

```python
def _execute_tool(self, name: str, inp: dict) -> str:
    """ツールを実行して結果文字列を返す"""
    tools_dir = Path("/home/tukapontas/gakukoma/tools")
    dispatch = {
        "speak_text":    [str(tools_dir / "speak_text.sh"), inp.get("text", "")],
        "see_around":    [str(tools_dir / "see_around.sh")],
        "look_direction":[str(tools_dir / "look_direction.sh"), inp.get("direction", "front")],
        "look_center":   [str(tools_dir / "look_center.sh")],
        "look_at_user":  [str(tools_dir / "look_at_user.sh")],
        "set_pan_tilt":  [str(tools_dir / "set_pan_tilt.sh"),
                          str(inp.get("pan", 90)), str(inp.get("tilt", 90))],
    }
    if name not in dispatch:
        return f"未知のツール: {name}"
    try:
        result = subprocess.run(dispatch[name], capture_output=True, text=True, timeout=30)
        return result.stdout.strip() or "完了"
    except subprocess.TimeoutExpired:
        return "タイムアウト"
    except Exception as e:
        return f"実行エラー: {e}"

def _call_api(self, message: str) -> str:
    """Anthropic APIを呼び出す。tool_useループを内蔵。"""
    messages = [{"role": "user", "content": message}]

    while True:
        response = self.client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=200,
            system=[{
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"}  # 5分TTL
            }],
            tools=TOOLS,
            messages=messages
        )

        # トークン使用量ログ
        usage = response.usage
        print(f"Tokens: input={usage.input_tokens}, "
              f"cache_create={getattr(usage, 'cache_creation_input_tokens', 0)}, "
              f"cache_read={getattr(usage, 'cache_read_input_tokens', 0)}, "
              f"output={usage.output_tokens}")

        if response.stop_reason == "tool_use":
            # ツールを実行してmessagesに追記し、ループで再呼び出し
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    print(f"ツール実行: {block.name}({block.input})")
                    output = self._execute_tool(block.name, block.input)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": output
                    })
            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": tool_results})

        else:  # end_turn
            for block in response.content:
                if hasattr(block, "text"):
                    return block.text
            return ""
```

### 1-9. 日次メモ読み込み

```python
def _load_daily_notes(self, days: int = 3) -> str:
    memory_dir = Path("/home/tukapontas/.openclaw/workspace/memory")
    notes = []
    for i in range(days):
        date = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
        path = memory_dir / f"{date}.md"
        if path.exists():
            content = path.read_text(encoding="utf-8").strip()
            if content:
                notes.append(f"[{date}]\n{content}")
    return "\n\n".join(notes) if notes else ""
```

### 1-10. セッション終了時の自動サマリー生成

```python
def end_session(self):
    """おやすみ時に呼ぶ"""
    if not self.local_history:
        return

    # local_historyから簡易サマリーを作成
    today = datetime.now().strftime("%Y-%m-%d")
    memory_dir = Path("/home/tukapontas/.openclaw/workspace/memory")
    memory_dir.mkdir(parents=True, exist_ok=True)
    memory_path = memory_dir / f"{today}.md"

    # セッション内容を箇条書きで追記
    lines = [f"\n## セッション（{datetime.now().strftime('%H:%M')}）\n"]
    for user_text, response in self.local_history:
        lines.append(f"- ユーザー: {user_text[:50]}")

    with open(memory_path, "a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"セッションサマリーを {memory_path} に追記しました")
```

---

## 2. `voice_loop.py` の修正仕様

### 2-1. インポート変更

削除:
```python
import json  # ← OpenClawのJSONパースに使用。不要になる
```

追加:
```python
import sys
sys.path.append("/home/tukapontas/gakukoma/brain")
from gakukoma_brain import GAKUKOMABrain
```

### 2-2. `__init__` の変更

削除（VoiceLoopクラスのinitから）:
```python
self.session_id = None
self.local_history = []
self.is_first_turn = True
```

追加:
```python
self.brain = GAKUKOMABrain(config)
```

### 2-3. `call_openclaw()` を `call_brain()` に置き換え

**削除**: `call_openclaw()` メソッド全体（L239〜L287）

**新規追加**:
```python
def call_brain(self, text: str) -> str:
    """GAKUKOMABrainを呼び出して応答を返す"""
    print("考え中...")
    try:
        return self.brain.invoke(text)
    except Exception as e:
        print(f"Error calling brain: {e}")
        return "すみません、エラーが発生しました。"
```

### 2-4. ウェイクワード検出時のセッションリセット

変更前:
```python
if self.is_wakeword(text):
    speak("はい、なんでしょう", self.tts_engine)
    self.session_id = str(uuid.uuid4())
    self.local_history = []
    self.is_first_turn = True
    self.state = "listening"
```

変更後:
```python
if self.is_wakeword(text):
    speak("はい、なんでしょう", self.tts_engine)
    self.brain.new_session()
    self.state = "listening"
```

### 2-5. おやすみ時のセッション終了処理

変更前:
```python
if self.is_sleepword(text):
    speak("おやすみなさい", self.tts_engine)
    self.flush_stream(active_stream, 1.5)
    self.state = "idle"
```

変更後:
```python
if self.is_sleepword(text):
    self.brain.end_session()
    speak("おやすみなさい", self.tts_engine)
    self.flush_stream(active_stream, 1.5)
    self.state = "idle"
```

### 2-6. `response = self.call_openclaw(text)` の置き換え

変更前:
```python
response = self.call_openclaw(text)
```

変更後:
```python
response = self.call_brain(text)
```

### 2-7. `_PRIMING_EXAMPLES` と `build_message()` の削除

VoiceLoopクラスから以下を削除（GAKUKOMABrainに移行済み）:
- `_PRIMING_EXAMPLES`（クラス変数）
- `build_message()` メソッド

### 2-8. `uuid` インポートの削除（brainに移行したため）

```python
import uuid  # ← 削除
```

---

## 3. `config.yaml` の修正

**不要になる設定**（openclaw:セクション。ただし既存設定として残してもよい）:
```yaml
# openclaw:  ← 使用しなくなるが削除は不要
```

---

## 4. テスト項目

### T-1: 基本起動テスト
- `python3 voice_loop.py` が正常起動すること
- 「がくこまが起動しました」が音声出力されること

### T-2: ウェイクワード→会話→スリープ
- 「おはよう」でアクティブモードに移行すること
- 普通の会話（「今日の天気は？」等）に2〜3文で応答すること
- 「おやすみ」でidle復帰 + memory/YYYY-MM-DD.mdにサマリーが追記されること

### T-3: トークン使用量確認
- コンソールに `Tokens: input=XXXX, cache_create=XXXX, cache_read=XXXX` が表示されること
- 2ターン目以降で `cache_read` が増加していること（プロンプトキャッシュヒット確認）

### T-4: 身体ツール連携テスト
- 「右を向いて」→ look_direction.sh が実行されること
- 「何が見える？」→ see_around.sh が実行されること
- 「正面向いて」→ look_center.sh が実行されること

### T-5: few-shot priming動作確認
- セッション1ターン目で `PRIMING_EXAMPLES` が付加されていること（コンソールログで確認）
- 2ターン目以降でローカル履歴が付加されていること

### T-6: キャラクター品質確認
- 返答が2〜3文以内であること
- ユーザーの発言を繰り返していないこと
- 定型フレーズを連呼していないこと

### T-7: 日次メモ読み込み確認
- `/home/tukapontas/.openclaw/workspace/memory/` に今日または過去3日分のファイルがある場合、それがLLMに渡されること

### T-8: エラーハンドリング
- APIキーが無効な場合に「すみません、エラーが発生しました」と返すこと

---

## 5. 完了報告時の確認事項

完了報告書（`coding/20260410_gakukoma_brain_completed.md`）に以下を記載すること:

1. Turn 1 input tokensの実測値（旧: 30,105 → 新: ?）
2. Turn 2以降のcache_read_input_tokensの実測値
3. LLMレイテンシ（コンソールログのTimestamp差分）の実測値
4. T-1〜T-8の合否
5. 気づいた点・懸念事項

---

## 6. 注意事項

- **OpenClaw常駐サービスはそのまま動かし続けてよい**（`openclaw-gateway.service`）。voice_loop.pyからは呼ばなくなるだけ
- `pan_tilt.py` に `__del__` を追加してはならない（既存の申し送り事項を引き継ぐ）
- `release()` / `deinit()` を `look_direction` 内から呼び出してはならない（同上）
- APIキーは `/home/tukapontas/.openclaw/openclaw.json` から取得すること（ハードコーディング禁止）
