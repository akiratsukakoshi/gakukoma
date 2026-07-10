#!/usr/bin/env python3
"""
GAKUKOMA 物理ボタンモニター（GPIO23）

押下時間でモードを切り替える:
  - 短押し（< 2秒）: 自律モード gakukoma.service をトグル起動/停止（従来動作）
  - 長押し（>= 2秒）: 操縦モード gakukoma-pilot.service をトグル起動/停止

両モードは相互排他。あるモードを「起動」するとき、もう一方が active なら
先に stop してから起動する。判定はボタンを「離した時点」の押下時間で行い、
チャタリング対策のデバウンス（0.3秒）は現行どおり維持する。

gakukoma-button.service から root で起動される。
"""
import subprocess
import time
from gpiozero import Button

BUTTON_GPIO = 23
DEBOUNCE_SEC = 0.3     # デバウンス時間（秒）: 直近のトグル後この時間は次の押下開始を無視
POLL_INTERVAL = 0.05   # ポーリング間隔（秒）
LONG_PRESS_SEC = 2.0   # この時間以上の押下を「長押し」と判定（操縦モード）

GAKUKOMA_SERVICE = "gakukoma"            # 自律モード
PILOT_SERVICE = "gakukoma-pilot"         # 操縦モード


def _is_active(service: str) -> bool:
    result = subprocess.run(
        ["systemctl", "is-active", service],
        capture_output=True, text=True
    )
    return result.stdout.strip() == "active"


def _start(service: str):
    subprocess.run(["systemctl", "start", service])


def _stop(service: str):
    subprocess.run(["systemctl", "stop", service])


def _toggle_service(target: str, other: str, label: str):
    """target をトグル。起動時は排他のため other が active なら先に停止する。"""
    if _is_active(target):
        print(f"ボタン: {label}を停止します...", flush=True)
        _stop(target)
        print(f"ボタン: {label} 停止完了", flush=True)
    else:
        if _is_active(other):
            print(f"ボタン: 排他のため他モードを停止します...", flush=True)
            _stop(other)
        print(f"ボタン: {label}を起動します...", flush=True)
        _start(target)
        print(f"ボタン: {label} 起動完了", flush=True)


def toggle_gakukoma():
    """自律モード(gakukoma)をトグル。起動時は操縦モードを停止する。"""
    _toggle_service(GAKUKOMA_SERVICE, PILOT_SERVICE, "自律モード（がくこま）")


def toggle_pilot():
    """操縦モード(gakukoma-pilot)をトグル。起動時は自律モードを停止する。"""
    _toggle_service(PILOT_SERVICE, GAKUKOMA_SERVICE, "操縦モード")


class ButtonMonitor:
    """ポーリングでボタン押下時間を測り、離した時点でモードをトグルする。

    実機依存を避けるため button / clock / sleep を注入可能にしてある
    （テストはフェイクを渡して poll_once を直接駆動する）。
    """

    def __init__(self, button, clock=time.monotonic, sleep=time.sleep):
        self.button = button
        self.clock = clock
        self.sleep = sleep
        self._last_state = False        # False = 未押下
        self._press_start = None        # 立ち上がり時刻（未押下中は None）
        self._last_toggle = float("-inf")

    def poll_once(self):
        pressed = self.button.is_pressed
        now = self.clock()

        # 立ち上がりエッジ（未押下→押下）かつ直近トグルからデバウンス期間外
        if pressed and not self._last_state and (now - self._last_toggle) > DEBOUNCE_SEC:
            self._press_start = now

        # 立ち下がりエッジ（押下→未押下）: 離した時点の押下時間で判定
        elif (not pressed) and self._last_state and self._press_start is not None:
            held = now - self._press_start
            if held >= LONG_PRESS_SEC:
                toggle_pilot()
            else:
                toggle_gakukoma()
            self._last_toggle = now
            self._press_start = None

        self._last_state = pressed

    def run(self):
        while True:
            self.poll_once()
            self.sleep(POLL_INTERVAL)


def main():
    btn = Button(BUTTON_GPIO, pull_up=True, bounce_time=None)
    print(f"ボタンモニター起動 (GPIO{BUTTON_GPIO})", flush=True)
    ButtonMonitor(btn).run()


if __name__ == "__main__":
    main()
