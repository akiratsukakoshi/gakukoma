"""
move_robot.sh から呼ばれるCLIエントリーポイント。
引数: direction [duration] [speed]
出力: 実行結果を標準出力（gakukoma_brain.py が tool_result として受け取る）
"""

import sys
from motor.motor_driver import MotorDriver

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


def main():
    direction = sys.argv[1] if len(sys.argv) > 1 else "stop"
    duration  = float(sys.argv[2]) if len(sys.argv) > 2 else 1.0
    # speed: 空文字列または未指定の場合は None（MotorDriver デフォルト使用）
    speed_arg = sys.argv[3] if len(sys.argv) > 3 else ""
    speed = int(speed_arg) if speed_arg.strip() else None

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
        if direction == "stop":
            print(f"{VALID_DIRECTIONS[direction]} 完了")
        else:
            print(f"{VALID_DIRECTIONS[direction]} 完了（{duration}秒・速度{speed_label}）")
    finally:
        driver.cleanup()


if __name__ == "__main__":
    main()
