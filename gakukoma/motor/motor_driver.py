"""
走行コマンド定義。TB6612FNG クラスを使って高レベルな走行操作を提供する。
time.sleep(duration) で走行時間を制御し、終了後は stop() する。
"""

import time
import yaml
from motor.tb6612_ctrl import TB6612FNG

DEFAULT_CONFIG_PATH = "/home/tukapontas/gakukoma/voice_loop/config.yaml"


class MotorDriver:
    def __init__(self):
        self.motor = TB6612FNG()
        # config から default_speed / turn_speed を読んで保持
        with open(DEFAULT_CONFIG_PATH, encoding="utf-8") as f:
            config = yaml.safe_load(f)
        motor_cfg = config["motor"]
        self.default_speed = motor_cfg.get("default_speed", 60)
        self.turn_speed = motor_cfg.get("turn_speed", 50)

    def forward(self, speed: int = None, duration: float = 1.0):
        """前進: 両モーター同速前進 → duration 秒後に停止"""
        s = speed if speed is not None else self.default_speed
        self.motor.set_motor_a(s)
        self.motor.set_motor_b(s)
        time.sleep(duration)
        self.motor.stop()

    def backward(self, speed: int = None, duration: float = 1.0):
        """後退: 両モーター同速後退 → duration 秒後に停止"""
        s = speed if speed is not None else self.default_speed
        self.motor.set_motor_a(-s)
        self.motor.set_motor_b(-s)
        time.sleep(duration)
        self.motor.stop()

    def turn_left(self, speed: int = None, duration: float = 0.5):
        """左旋回: 右モーター前進・左モーター停止"""
        s = speed if speed is not None else self.turn_speed
        self.motor.set_motor_a(0)
        self.motor.set_motor_b(s)
        time.sleep(duration)
        self.motor.stop()

    def turn_right(self, speed: int = None, duration: float = 0.5):
        """右旋回: 左モーター前進・右モーター停止"""
        s = speed if speed is not None else self.turn_speed
        self.motor.set_motor_a(s)
        self.motor.set_motor_b(0)
        time.sleep(duration)
        self.motor.stop()

    def spin_left(self, speed: int = None, duration: float = 0.5):
        """左スピン（超信地旋回）: 左後退・右前進"""
        s = speed if speed is not None else self.turn_speed
        self.motor.set_motor_a(-s)
        self.motor.set_motor_b(s)
        time.sleep(duration)
        self.motor.stop()

    def spin_right(self, speed: int = None, duration: float = 0.5):
        """右スピン（超信地旋回）: 左前進・右後退"""
        s = speed if speed is not None else self.turn_speed
        self.motor.set_motor_a(s)
        self.motor.set_motor_b(-s)
        time.sleep(duration)
        self.motor.stop()

    def stop(self):
        self.motor.stop()

    def cleanup(self):
        self.motor.cleanup()
