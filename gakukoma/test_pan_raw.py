import sys
import time
sys.path.insert(0, '/home/tukapontas/gakukoma')
from servo.pca9685_ctrl import PCA9685Controller

ctrl = PCA9685Controller()
print('ch0を45°に設定...')
ctrl.set_angle(0, 45)
time.sleep(2)
print('ch0を135°に設定...')
ctrl.set_angle(0, 135)
time.sleep(2)
print('完了（release()なし）')
