#!/bin/bash
# survey_room.sh - 左・正面・右の3方向を撮影してVision APIで部屋の構造を解析する

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
GAKUKOMA_DIR="/home/tukapontas/gakukoma"

IMAGE_A="/tmp/gakukoma_survey_left.jpg"
IMAGE_B="/tmp/gakukoma_survey_center.jpg"
IMAGE_C="/tmp/gakukoma_survey_right.jpg"

# ステップ1: 左を向いて撮影
python3 -c "
import sys
sys.path.insert(0, '$GAKUKOMA_DIR')
from servo.pan_tilt import PanTiltController
ctrl = PanTiltController()
result = ctrl.look_direction('left')
print(result, file=sys.stderr)
" 2>&1 >&2

sleep 0.5

python3 -c "
import sys
sys.path.insert(0, '$GAKUKOMA_DIR/camera')
from capture import CameraCapture
import shutil
cam = CameraCapture()
path = cam.capture_frame()
cam.release()
shutil.copy(path, '$IMAGE_A')
"

# ステップ2: 正面を向いて撮影
python3 -c "
import sys
sys.path.insert(0, '$GAKUKOMA_DIR')
from servo.pan_tilt import PanTiltController
ctrl = PanTiltController()
result = ctrl.look_center()
print(result, file=sys.stderr)
" 2>&1 >&2

sleep 0.5

python3 -c "
import sys
sys.path.insert(0, '$GAKUKOMA_DIR/camera')
from capture import CameraCapture
import shutil
cam = CameraCapture()
path = cam.capture_frame()
cam.release()
shutil.copy(path, '$IMAGE_B')
"

# ステップ3: 右を向いて撮影
python3 -c "
import sys
sys.path.insert(0, '$GAKUKOMA_DIR')
from servo.pan_tilt import PanTiltController
ctrl = PanTiltController()
result = ctrl.look_direction('right')
print(result, file=sys.stderr)
" 2>&1 >&2

sleep 0.5

python3 -c "
import sys
sys.path.insert(0, '$GAKUKOMA_DIR/camera')
from capture import CameraCapture
import shutil
cam = CameraCapture()
path = cam.capture_frame()
cam.release()
shutil.copy(path, '$IMAGE_C')
"

# ステップ4: 正面に戻す
python3 -c "
import sys
sys.path.insert(0, '$GAKUKOMA_DIR')
from servo.pan_tilt import PanTiltController
ctrl = PanTiltController()
result = ctrl.look_center()
print(result, file=sys.stderr)
" 2>&1 >&2

# ステップ5: 画像A・B・CをVision APIへ一括送信して解析
python3 - <<'PYEOF'
import os
import json
import base64
import anthropic

def get_api_key() -> str:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if key:
        return key
    auth_path = os.path.expanduser("~/.openclaw/agents/main/agent/auth-profiles.json")
    if os.path.exists(auth_path):
        try:
            with open(auth_path, "r") as f:
                profiles_data = json.load(f)
                profiles = profiles_data.get("profiles", {})
                for profile_name, profile_info in profiles.items():
                    if profile_info.get("provider") == "anthropic":
                        return profile_info.get("key")
        except Exception as e:
            print(f"Error reading auth-profiles.json: {e}")
    return None

api_key = get_api_key()
if not api_key:
    print("APIキーが見つかりません。ANTHROPIC_API_KEY 環境変数を設定するか、OpenClawの設定を確認してください。")
    exit(1)

image_paths = [
    "/tmp/gakukoma_survey_left.jpg",
    "/tmp/gakukoma_survey_center.jpg",
    "/tmp/gakukoma_survey_right.jpg",
]
labels = ["左", "正面", "右"]

content = []
for path, label in zip(image_paths, labels):
    try:
        with open(path, "rb") as f:
            image_data = base64.standard_b64encode(f.read()).decode("utf-8")
        content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/jpeg",
                "data": image_data,
            },
        })
        content.append({
            "type": "text",
            "text": f"（上の画像: {label}方向）"
        })
    except Exception as e:
        print(f"{label}方向の画像読み込みに失敗しました: {e}")
        exit(1)

content.append({
    "type": "text",
    "text": (
        "これはがくこまというロボットが左・正面・右の順番に首を振って撮影した3枚の連続画像です。\n"
        "がくこまの現在地から見えるドア・入口・通路・障害物の位置を、\n"
        "「左に〇〇、正面に〇〇、右に〇〇」の形式で日本語2〜3文で答えてください。"
    )
})

client = anthropic.Anthropic(api_key=api_key)
try:
    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=400,
        messages=[{
            "role": "user",
            "content": content,
        }]
    )
    print(message.content[0].text)
except Exception as e:
    print(f"画像の解析に失敗しました: {e}")
    exit(1)
PYEOF
