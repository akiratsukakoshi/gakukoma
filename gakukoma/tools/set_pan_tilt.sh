#!/bin/bash
# 使用方法: set_pan_tilt.sh <pan_angle> <tilt_angle>
# 例: set_pan_tilt.sh 45 90

PAN="${1:-90}"
TILT="${2:-90}"
cd /home/tukapontas/gakukoma
python3 -c "
import sys
sys.path.insert(0, '/home/tukapontas/gakukoma')
from servo.pan_tilt import PanTiltController
ctrl = PanTiltController()
result = ctrl.set_pan_tilt(${PAN}, ${TILT})
print(result)
"
