#!/bin/bash
# 使用方法: look_center.sh
# 例: look_center.sh

cd /home/tukapontas/gakukoma
python3 -c "
import sys
sys.path.insert(0, '/home/tukapontas/gakukoma')
from servo.pan_tilt import PanTiltController
ctrl = PanTiltController()
result = ctrl.look_center()
print(result)
"
