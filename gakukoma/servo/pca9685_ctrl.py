import board
import busio
import adafruit_pca9685

class PCA9685Controller:
    """PCA9685 サーボドライバの制御クラス"""

    SERVO_FREQ = 50          # SG90は50Hz PWM
    PULSE_MIN_US = 1000      # 0° = 1000μs
    PULSE_MAX_US = 2000      # 180° = 2000μs
    PERIOD_US = 20000        # 1/50Hz = 20000μs

    def __init__(self):
        try:
            i2c = busio.I2C(board.SCL, board.SDA)
            self.pca = adafruit_pca9685.PCA9685(i2c)
            self.pca.frequency = self.SERVO_FREQ
        except Exception as e:
            print(f"サーボドライバの初期化に失敗しました: {e}")
            raise

    def set_angle(self, channel: int, angle: int):
        """
        指定チャンネルのサーボを angle 度に設定する
        angle: 0〜180 の整数
        """
        # 角度 → パルス幅(μs) → duty cycle(16bit) の変換
        angle = max(0, min(180, angle))  # クランプ
        pulse_us = self.PULSE_MIN_US + (angle / 180.0) * (self.PULSE_MAX_US - self.PULSE_MIN_US)
        duty = int(pulse_us / self.PERIOD_US * 65535)
        self.pca.channels[channel].duty_cycle = duty

    def release(self):
        """PWMを停止してサーボを脱力（I2Cバスは維持）"""
        try:
            for ch in range(16):
                self.pca.channels[ch].duty_cycle = 0
        except:
            pass
