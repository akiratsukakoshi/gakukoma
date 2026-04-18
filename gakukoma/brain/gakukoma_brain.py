import anthropic
import yaml
import uuid
import json
import os
import re
import subprocess
from pathlib import Path
from datetime import datetime, timedelta


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
    },
    {
        "name": "move_robot",
        "description": "ロボットを走行させる。前進・後退・左右旋回・スピン・停止が可能。",
        "input_schema": {
            "type": "object",
            "properties": {
                "direction": {
                    "type": "string",
                    "enum": ["forward", "backward", "left", "right", "spin_left", "spin_right", "stop"],
                    "description": "走行方向。forward=前進, backward=後退, left=左旋回, right=右旋回, spin_left=左スピン, spin_right=右スピン, stop=停止"
                },
                "duration": {
                    "type": "number",
                    "description": "走行秒数（デフォルト: 1.0）"
                },
                "speed": {
                    "type": "integer",
                    "description": "速度 0〜100%（省略時はデフォルト速度60%）"
                }
            },
            "required": ["direction"]
        }
    },
]

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


class GAKUKOMABrain:
    def __init__(self, config: dict):
        # openclaw.jsonからAPIキー取得
        openclaw_config_path = "/home/tukapontas/.openclaw/openclaw.json"
        with open(openclaw_config_path) as f:
            oc = json.load(f)
        api_key = oc["models"]["providers"]["anthropic"]["apiKey"]
        self.client = anthropic.Anthropic(api_key=api_key)
        self.config = config
        self.session_id = None
        self.local_history = []
        self.is_first_turn = True

    def new_session(self):
        self.session_id = str(uuid.uuid4())
        self.local_history = []
        self.is_first_turn = True

    def invoke(self, user_text: str) -> str:
        message = self._build_message(user_text)
        response = self._call_api(message)
        self.local_history.append((user_text, response))
        return response

    def end_session(self):
        if not self.local_history:
            return
        today = datetime.now().strftime("%Y-%m-%d")
        memory_dir = Path("/home/tukapontas/.openclaw/workspace/memory")
        memory_dir.mkdir(parents=True, exist_ok=True)
        memory_path = memory_dir / f"{today}.md"
        lines = [f"\n## セッション（{datetime.now().strftime('%H:%M')}）\n"]
        for user_text, response in self.local_history:
            lines.append(f"- ユーザー: {user_text[:50]}")
        with open(memory_path, "a", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        print(f"セッションサマリーを {memory_path} に追記しました")

    def _build_message(self, user_text: str) -> str:
        parts = []

        # Layer 4: 日次メモ（最近3日分）- 全ターンで付加
        daily_notes = self._load_daily_notes(days=3)
        if daily_notes:
            parts.append(f"【最近の記憶】\n{daily_notes}")

        # Layer 2: few-shot priming（初回ターンのみ）
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

    def _execute_tool(self, name: str, inp: dict) -> str:
        tools_dir = Path("/home/tukapontas/gakukoma/tools")
        dispatch = {
            "speak_text":    [str(tools_dir / "speak_text.sh"), inp.get("text", "")],
            "see_around":    [str(tools_dir / "see_around.sh")],
            "look_direction":[str(tools_dir / "look_direction.sh"), inp.get("direction", "front")],
            "look_center":   [str(tools_dir / "look_center.sh")],
            "look_at_user":  [str(tools_dir / "look_at_user.sh")],
            "set_pan_tilt":  [str(tools_dir / "set_pan_tilt.sh"),
                              str(inp.get("pan", 90)), str(inp.get("tilt", 90))],
            "move_robot": [
                str(tools_dir / "move_robot.sh"),
                inp.get("direction", "stop"),
                str(inp.get("duration", 1.0)),
                str(inp.get("speed", "")),
            ],
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
        messages = [{"role": "user", "content": message}]

        while True:
            response = self.client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=200,
                system=[{
                    "type": "text",
                    "text": SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"}
                }],
                tools=TOOLS,
                messages=messages
            )

            usage = response.usage
            print(f"Tokens: input={usage.input_tokens}, "
                  f"cache_create={getattr(usage, 'cache_creation_input_tokens', 0)}, "
                  f"cache_read={getattr(usage, 'cache_read_input_tokens', 0)}, "
                  f"output={usage.output_tokens}")

            if response.stop_reason == "tool_use":
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
