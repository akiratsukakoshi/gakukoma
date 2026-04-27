import anthropic
import yaml
import uuid
import json
import os
import re
import sys
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
複合的な指示（「前進してから右に曲がって」「隣の部屋に行って確認して」など）は、ツールを順番に呼び出して達成する。一度に複数ステップを計画・実行してよい。

探索・巡回・見回しなどの開放的な指示（「あたりを動き回って」「部屋を探索して」など）は、自分で計画を立ててmove_robotとsee_aroundを3〜5セット繰り返してから報告する。探索中はspeak_textで「前進するよ」「右を確認してみる」など実況してよい。ツール呼び出しは必要な回数だけ繰り返してよい（上限20回）。

歌を歌う指示（「うたって」「歌って」「ハッピーバースデーうたって」など）は、sing_songツールを使う。
公共ドメインの曲（ハッピーバースデー、きらきら星、チューリップ、かえるのうた等）は自分で音符を生成して渡す。
「なんか歌って」「悲しい曲うたって」など曲名指定なしの場合は自作メロディを生成して渡す。
歌の前後にspeak_textで一言添えてよい（「歌うよ」「はいどうぞ」など短く）。

## 顔認識ツール
- 「これが〇〇だよ」と人物紹介されたら `register_face` を呼んで顔を登録する
- `look_at_user` を呼んだとき、識別できた相手には名前で呼びかける
"""

TOOLS = [
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
    },
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
]

PRIMING_EXAMPLES = (
    "ガクチョ: 話す前にルールを確認するよ。返答は必ず2〜3文以内。長くなりそうなら1文でいい。ユーザーの発言をそのまま繰り返さない。「へぇ〜」や「ワクワク」などの感嘆詞を連続で使わない。複数ステップの指示はツールを順番に呼び出して全部やり遂げる。わかった？\n"
    "がくこま: わかった。短く、自分の言葉で返す。複合指示はツールを連続で使って達成する。\n"
    "ガクチョ: 今日なにしてた？\n"
    "がくこま: 窓の外を観察してたんだ。虫が飛ぶルートに法則があるのかなって。\n"
    "ガクチョ: 疲れたよ\n"
    "がくこま: それは大変だったね。少し休んで？\n"
    "ガクチョ: 音楽聴いてたよ\n"
    "がくこま: どんな曲？音の波って不思議だよね、空気を伝わって耳に届くんだから。\n"
    "ガクチョ: 前に2秒進んで、それから右に曲がって。\n"
    "がくこま: （move_robot: forward 2秒）（move_robot: right 1秒）動いたよ。\n"
    "ガクチョ: あたりを動き回って見まわしてきて。\n"
    "がくこま: （speak_text: 探索してくるね）（move_robot: forward 2秒）（see_around）（move_robot: spin_right 1秒）（see_around）（move_robot: forward 2秒）（see_around）前の方に本棚が見えた。右側は壁だったよ。\n"
    "ガクチョ: がくこま、これが学長だよ。\n"
    "がくこま: （register_face: 学長）わかった！学長の顔を覚えたよ。次から名前で呼べるようになる。\n"
    "ガクチョ: 誰かいる？\n"
    "がくこま: （look_at_user）学長がいるね！\n"
    "ガクチョ: ハッピーバースデーうたって。\n"
    "がくこま: （sing_song: [{\"freq\":261.6,\"duration\":0.25},{\"freq\":261.6,\"duration\":0.25},{\"freq\":293.7,\"duration\":0.5},{\"freq\":261.6,\"duration\":0.5},{\"freq\":349.2,\"duration\":0.5},{\"freq\":329.6,\"duration\":1.0},...] tempo:1.0）歌ったよ！\n"
    "ガクチョ: なんか歌って。\n"
    "がくこま: （sing_song: 自作メロディの音符列）作ってみたよ。こんな感じ。\n\n"
)

MEMORY_DIR = Path("/home/tukapontas/gakukoma/memory")
LEGACY_MEMORY_DIR = Path("/home/tukapontas/.openclaw/workspace/memory")  # 旧ディレクトリ


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

        # FaceRecognizerは重いので1回だけ初期化（register_face/look_at_user識別で共有）
        try:
            sys.path.insert(0, '/home/tukapontas/gakukoma')
            from camera.face_recognizer import FaceRecognizer
            self._face_recognizer = FaceRecognizer()
        except Exception as e:
            print(f"FaceRecognizer初期化失敗（顔認識無効）: {e}")
            self._face_recognizer = None

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
        """おやすみ時に呼ぶ。完全な会話ログをraw/に保存する。"""
        if not self.local_history:
            return

        # raw/ に完全なセッションログを保存
        timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        raw_path = MEMORY_DIR / "raw" / f"{timestamp}.md"
        MEMORY_DIR.joinpath("raw").mkdir(parents=True, exist_ok=True)

        lines = [
            f"# セッションログ {timestamp}",
            f"session_id: {self.session_id}",
            "",
        ]
        for user_text, response in self.local_history:
            lines.append(f"**ユーザー**: {user_text}")
            lines.append(f"**がくこま**: {response}")
            lines.append("")

        raw_path.write_text("\n".join(lines), encoding="utf-8")
        print(f"セッションログを {raw_path} に保存しました")

        # 旧ディレクトリへの後方互換ログも残す（念のため）
        today = datetime.now().strftime("%Y-%m-%d")
        legacy_path = LEGACY_MEMORY_DIR / f"{today}.md"
        if legacy_path.exists():
            # 旧ファイルがある場合はそのまま（上書きしない）
            pass

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
        """
        wikiのindex.md と core_memories.md を読み込んで返す。
        wikiが存在しない場合（初期状態）は旧ディレクトリのログをフォールバックで読む。
        """
        wiki_dir = MEMORY_DIR / "wiki"
        index_path = wiki_dir / "index.md"
        core_path = wiki_dir / "core_memories.md"

        parts = []

        # wiki/index.md が存在する場合（Phase 5.1稼働後）
        if index_path.exists():
            index_content = index_path.read_text(encoding="utf-8").strip()
            if index_content:
                parts.append(f"【記憶インデックス】\n{index_content}")

        # wiki/core_memories.md が存在する場合
        if core_path.exists():
            core_content = core_path.read_text(encoding="utf-8").strip()
            if core_content:
                parts.append(f"【忘れられない記憶】\n{core_content}")

        # wikiがまだ空（初期状態）の場合は旧ディレクトリをフォールバック
        if not parts:
            notes = []
            for i in range(days):
                date = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
                # 新ディレクトリのrawログを試す
                raw_files = sorted((MEMORY_DIR / "raw").glob(f"{date}_*.md")) if (MEMORY_DIR / "raw").exists() else []
                if raw_files:
                    for p in raw_files[-1:]:  # 当日最後のセッションのみ
                        content = p.read_text(encoding="utf-8").strip()
                        if content:
                            notes.append(f"[{date}]\n{content[:500]}")  # 500文字に制限
                else:
                    # 旧ディレクトリ
                    legacy_path = LEGACY_MEMORY_DIR / f"{date}.md"
                    if legacy_path.exists():
                        content = legacy_path.read_text(encoding="utf-8").strip()
                        if content:
                            notes.append(f"[{date}]\n{content}")
            if notes:
                parts.append(f"【最近の記憶】\n" + "\n\n".join(notes))

        return "\n\n".join(parts) if parts else ""

    def _execute_tool(self, name: str, inp: dict) -> str:
        # register_face は Python直接処理（shスクリプト経由しない）
        if name == "register_face":
            reg_name = inp.get("name", "")
            if not reg_name:
                return "名前が指定されていない"
            if self._face_recognizer is None:
                return "顔認識モジュールが利用できない"
            try:
                from camera.capture import CameraCapture
                cam = CameraCapture(device_id=0)
                frame = cam.capture()
                cam.release()
                if frame is None:
                    return "カメラから画像を取得できなかった"
                ok = self._face_recognizer.register(frame, reg_name)
                if ok:
                    return f"{reg_name}の顔を登録した"
                else:
                    return "顔が検出できなかった（正面を向いて）"
            except Exception as e:
                return f"顔登録エラー: {e}"

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
            "sing_song": [
                str(tools_dir / "sing_song.sh"),
                json.dumps(inp.get("notes", []), ensure_ascii=False),
                str(inp.get("tempo", 1.0)),
            ],
        }
        if name not in dispatch:
            return f"未知のツール: {name}"
        try:
            # sing_song は長い曲に対応するため timeout=120 を個別指定
            if name == "sing_song":
                cmd = dispatch[name]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
                return result.stdout.strip() or "完了"

            result = subprocess.run(dispatch[name], capture_output=True, text=True, timeout=30)
            raw_output = result.stdout.strip()

            # look_at_user の出力は JSON形式になったのでパースして人間向けメッセージに変換
            if name == "look_at_user":
                try:
                    lau_result = json.loads(raw_output)
                    if lau_result.get("success"):
                        identified = lau_result.get("identified")
                        if identified and identified != "unknown":
                            return f"{identified}を認識した"
                        elif identified == "unknown":
                            return "知らない人がいる（未登録）"
                        else:
                            return "顔が見つからなかった"
                    else:
                        return "顔が見つからなかった"
                except (json.JSONDecodeError, KeyError):
                    # フォールバック: 旧形式のplain text
                    return raw_output or "完了"

            return raw_output or "完了"
        except subprocess.TimeoutExpired:
            return "タイムアウト"
        except Exception as e:
            return f"実行エラー: {e}"

    def _call_api(self, message: str) -> str:
        messages = [{"role": "user", "content": message}]
        tool_call_count = 0
        MAX_TOOL_ITERATIONS = 20

        while True:
            response = self.client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=512,
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
                tool_call_count += 1
                if tool_call_count >= MAX_TOOL_ITERATIONS:
                    return "たくさん動いたよ。そろそろ休憩する。"
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
