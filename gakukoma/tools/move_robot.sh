#!/bin/bash
# 使用例: move_robot.sh forward 1.0 60
# 引数: direction [duration] [speed]
cd /home/tukapontas/gakukoma
python3 -m motor.move_robot_cmd "$@"
