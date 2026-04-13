import time
import threading

class GestureController:
    """
    パンチルト台座のジェスチャーを管理するクラス。
    PanTiltController を受け取り、バックグラウンドスレッドで動作する。

    重要制約:
    - pan_tilt.release() を呼び出してはならない（脱力する）
    - set_pan_tilt / set_pan / set_tilt は PanTiltController のロックを内部で獲得する
    """

    # (pan, tilt, hold_sec) の3タプル
    _THINKING_SEQUENCE = [
        (115, 72, 2.5),   # 右斜め上（ゆっくり視線を上右へ）
        (65,  72, 2.5),   # 左斜め上（ゆっくり視線を上左へ）
        (115, 108, 2.0),  # 右下（考え込む）
    ]

    # スピーキングジェスチャーのパターン（頷き）
    # 上下に大きく動き、最後に中央へ戻る
    _SPEAKING_PATTERN = [
        (90, 80),   # 上を向く（大きく）
        (90, 90),   # 中央
        (90, 100),  # 下を向く
        (90, 90),   # 中央
        (90, 78),   # 上（やや大きく）
        (90, 90),   # 中央
    ]

    def __init__(self, pan_tilt_controller):
        """
        Args:
            pan_tilt_controller: servo.pan_tilt.PanTiltController のインスタンス
        """
        self._pt = pan_tilt_controller
        self._stop_event = threading.Event()
        self._thread = None

    def _run_thinking(self, stop_event):
        """シンキングジェスチャーのバックグラウンドスレッド（ゆったりした動き）"""
        idx = 0
        while not stop_event.is_set():
            pan, tilt, hold_sec = self._THINKING_SEQUENCE[idx % len(self._THINKING_SEQUENCE)]
            self._pt.set_pan_tilt(pan, tilt)
            idx += 1
            # hold_sec 秒間、0.1秒ごとに stop_event を確認しながら保持
            steps = int(hold_sec / 0.1)
            for _ in range(steps):
                if stop_event.is_set():
                    return
                time.sleep(0.1)

    def _run_speaking(self, stop_event):
        """スピーキングジェスチャーのバックグラウンドスレッド"""
        idx = 0
        while not stop_event.is_set():
            pan, tilt = self._SPEAKING_PATTERN[idx % len(self._SPEAKING_PATTERN)]
            self._pt.set_pan_tilt(pan, tilt)
            idx += 1
            # 0.3秒ごとにstop_eventを確認（thinking より速い動き）
            for _ in range(3):
                if stop_event.is_set():
                    break
                time.sleep(0.1)

    def start_thinking(self):
        """シンキングジェスチャー開始。既存ジェスチャーは停止してから開始する。"""
        self.stop()
        self._stop_event = threading.Event()
        self._thread = threading.Thread(
            target=self._run_thinking,
            args=(self._stop_event,),
            daemon=True,
            name="gesture-thinking"
        )
        self._thread.start()

    def start_speaking(self):
        """スピーキングジェスチャー開始。既存ジェスチャーは停止してから開始する。"""
        self.stop()
        self._stop_event = threading.Event()
        self._thread = threading.Thread(
            target=self._run_speaking,
            args=(self._stop_event,),
            daemon=True,
            name="gesture-speaking"
        )
        self._thread.start()

    def stop(self):
        """現在のジェスチャーを停止してスレッドが終了するのを待つ。"""
        if self._thread and self._thread.is_alive():
            self._stop_event.set()
            self._thread.join(timeout=1.0)
        self._thread = None

    def go_center(self):
        """ジェスチャーを停止し、首をニュートラルポジション（正面）へ戻す。"""
        self.stop()
        self._pt.look_center()