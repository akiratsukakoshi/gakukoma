#!/bin/bash
# 使用方法: look_direction.sh <direction>
# 例: look_direction.sh right

DIRECTION="${1:-front}"
cd /home/tukapontas/gakukoma
python3 -c "
import sys
sys.path.insert(0, '/home/tukapontas/gakukoma')
from servo.pan_tilt import PanTiltController
ctrl = PanTiltController()
result = ctrl.look_direction('${DIRECTION}')
print(result)
"
