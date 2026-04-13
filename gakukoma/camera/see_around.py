import os
import json
import base64
import anthropic
from capture import CameraCapture

def get_api_key() -> str:
    # 1. 環境変数 ANTHROPIC_API_KEY を優先
    key = os.environ.get("ANTHROPIC_API_KEY")
    if key:
        return key
    
    # 2. OpenClawの auth-profiles.json からフォールバック
    auth_path = os.path.expanduser("~/.openclaw/agents/main/agent/auth-profiles.json")
    if os.path.exists(auth_path):
        try:
            with open(auth_path, "r") as f:
                profiles_data = json.load(f)
                # anthropic プロバイダーのキーを探す
                profiles = profiles_data.get("profiles", {})
                for profile_name, profile_info in profiles.items():
                    if profile_info.get("provider") == "anthropic":
                        return profile_info.get("key")
        except Exception as e:
            print(f"Error reading auth-profiles.json: {e}")
            
    return None

def see_around():
    api_key = get_api_key()
    if not api_key:
        print("APIキーが見つかりません。ANTHROPIC_API_KEY 環境変数を設定するか、OpenClawの設定を確認してください。")
        return

    try:
        cam = CameraCapture()
        image_path = cam.capture_frame()
        cam.release()
    except Exception as e:
        print(f"カメラが見つかりません: {e}")
        return

    client = anthropic.Anthropic(api_key=api_key)
    
    try:
        with open(image_path, "rb") as f:
            image_data = base64.standard_b64encode(f.read()).decode("utf-8")

        message = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=300,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/jpeg",
                            "data": image_data,
                        },
                    },
                    {
                        "type": "text",
                        "text": "この画像はあなた自身（がくこま）の前面カメラが今この瞬間に捉えた、あなたの視野です。\n第三者として写真を解説するのではなく、「僕が今見ているもの」として日本語2〜3文で説明してください。\n「画像には」「写真では」「撮影されている」などの表現は使わないでください。"
                    }
                ],
            }]
        )
        print(message.content[0].text)
    except Exception as e:
        print(f"画像の解析に失敗しました: {e}")

if __name__ == "__main__":
    see_around()
