"""
move_robot.sh から呼ばれるCLIエントリーポイント。
引数: direction [duration] [speed]
出力: 実行結果を標準出力（gakukoma_brain.py が tool_result として受け取る）

安全設計(WP3):
- duration は MAX_MOVE_DURATION 秒で上限クランプ（LLMが長秒を渡しても走りっぱなしにしない）。
- SIGTERM/SIGINT を受けたら SystemExit を送出し、finally の cleanup() を必ず通す
  （systemd停止・kill でもモーターを止める）。
- 引数パースの失敗は生トレースバックを出さず、LLMが読める1行エラー+exit 1 で返す。
"""

import sys
import signal
from motor.motor_driver import MotorDriver

# 走行時間の上限（秒）。これを超える duration はこの値にクランプする。
MAX_MOVE_DURATION = 10.0

VALID_DIRECTIONS = {
    "forward":    "前進",
    "backward":   "後退",
    "left":       "左旋回",
    "right":      "右旋回",
    "spin_left":  "左スピン",
    "spin_right": "右スピン",
    "stop":       "停止",
}

# direction → MotorDriver メソッドのマッピング
DIRECTION_MAP = {
    "forward":    "forward",
    "backward":   "backward",
    "left":       "turn_left",
    "right":      "turn_right",
    "spin_left":  "spin_left",
    "spin_right": "spin_right",
    "stop":       "stop",
}


def _handle_termination(signum, frame):
    """SIGTERM/SIGINT 受信時に SystemExit を送出する。

    time.sleep(duration) 中に kill/systemd停止が来ても、SystemExit なら
    main() の try/finally を通って driver.cleanup() が走り、モーターが止まる。
    """
    raise SystemExit(f"シグナル{signum}受信により停止")


def parse_args(argv):
    """argv(sys.argv相当)を (direction, duration, speed, clamped) にパースする。

    - duration は 0.0〜MAX_MOVE_DURATION にクランプする。
    - clamped はクランプが発動したか（出力メッセージ用）。
    - duration/speed が非数値なら ValueError を送出する（呼び出し側で友好的に処理）。
    """
    direction = argv[1] if len(argv) > 1 else "stop"
    duration  = float(argv[2]) if len(argv) > 2 else 1.0
    # speed: 空文字列または未指定の場合は None（MotorDriver デフォルト使用）
    speed_arg = argv[3] if len(argv) > 3 else ""
    speed = int(speed_arg) if speed_arg.strip() else None

    clamped_duration = max(0.0, min(duration, MAX_MOVE_DURATION))
    clamped = (clamped_duration != duration)
    return direction, clamped_duration, speed, clamped


def main(argv=None):
    if argv is None:
        argv = sys.argv

    # SIGTERM/SIGINT でも finally の cleanup を通す
    signal.signal(signal.SIGTERM, _handle_termination)
    signal.signal(signal.SIGINT, _handle_termination)

    try:
        direction, duration, speed, clamped = parse_args(argv)
    except ValueError:
        # 生トレースバックを避け、LLMが読める1行で返す
        print("走行パラメータが不正（durationとspeedは数値で指定して）")
        sys.exit(1)

    if direction not in VALID_DIRECTIONS:
        print(f"不明な方向: {direction}")
        sys.exit(1)

    driver = MotorDriver()
    try:
        method_name = DIRECTION_MAP[direction]
        method = getattr(driver, method_name)
        kwargs = {}
        if direction != "stop":
            kwargs["duration"] = duration
            if speed is not None:
                kwargs["speed"] = speed
        method(**kwargs)
        speed_label = f"{speed}%" if speed is not None else "デフォルト"
        clamp_note = "（上限10秒に制限）" if clamped else ""
        if direction == "stop":
            print(f"{VALID_DIRECTIONS[direction]} 完了")
        else:
            print(f"{VALID_DIRECTIONS[direction]} 完了（{duration}秒・速度{speed_label}）{clamp_note}")
    finally:
        driver.cleanup()


if __name__ == "__main__":
    main()
