#!/usr/bin/env python3
"""
GAKUKOMA 物理ボタンモニター
GPIO23 のボタン押下で gakukoma.service をトグル起動/停止する。
gakukoma-button.service から root で起動される。
"""
import subprocess
import time
from gpiozero import Button

BUTTON_GPIO = 23
DEBOUNCE_SEC = 0.3   # デバウンス時間（秒）
POLL_INTERVAL = 0.05 # ポーリング間隔（秒）


def is_gakukoma_running() -> bool:
    result = subprocess.run(
        ["systemctl", "is-active", "gakukoma"],
        capture_output=True, text=True
    )
    return result.stdout.strip() == "active"


def toggle_gakukoma():
    if is_gakukoma_running():
        print("ボタン: がくこまを停止します...", flush=True)
        subprocess.run(["systemctl", "stop", "gakukoma"])
        print("ボタン: 停止完了", flush=True)
    else:
        print("ボタン: がくこまを起動します...", flush=True)
        subprocess.run(["systemctl", "start", "gakukoma"])
        print("ボタン: 起動完了", flush=True)


def main():
    btn = Button(BUTTON_GPIO, pull_up=True, bounce_time=None)
    print(f"ボタンモニター起動 (GPIO{BUTTON_GPIO})", flush=True)

    last_state = False  # False = 未押下
    last_toggle_time = 0.0

    while True:
        pressed = btn.is_pressed
        now = time.monotonic()

        # 立ち上がりエッジ検出（未押下→押下）かつデバウンス期間外
        if pressed and not last_state and (now - last_toggle_time) > DEBOUNCE_SEC:
            toggle_gakukoma()
            last_toggle_time = now

        last_state = pressed
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
