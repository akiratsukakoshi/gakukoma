"""
TB6612FNG 制御クラス
- gpiozero + lgpio を使用（pigpiod は Debian では非対応のため lgpio を使用）
- __del__ を実装しないこと（スクリプト終了時の予期せぬ停止を防ぐ）
- 終了処理は cleanup() を明示的に呼ぶ設計にすること
"""

import yaml
import os
import gpiozero
from gpiozero import OutputDevice, PWMOutputDevice
from gpiozero.pins.lgpio import LGPIOFactory

# lgpio ファクトリを使用（Pi5 対応。pigpiod は Debian trixie では未パッケージ）
gpiozero.Device.pin_factory = LGPIOFactory()

DEFAULT_CONFIG_PATH = "/home/tukapontas/gakukoma/voice_loop/config.yaml"


class TB6612FNG:
    def __init__(self, config_path=None):
        """
        config_path が None の場合は
        /home/tukapontas/gakukoma/voice_loop/config.yaml を読む。
        motor セクションを読み込んで各ピン番号・設定を初期化。
        STBY を HIGH にしてドライバを有効化。
        motor_b_invert フラグを読み込んで self.motor_b_invert に保持。
        """
        if config_path is None:
            config_path = DEFAULT_CONFIG_PATH
        with open(config_path, encoding="utf-8") as f:
            config = yaml.safe_load(f)
        motor_cfg = config["motor"]

        pwm_freq = motor_cfg.get("pwm_frequency", 1000)

        # 左モーター（A）
        self.ain1 = OutputDevice(motor_cfg["ain1"])
        self.ain2 = OutputDevice(motor_cfg["ain2"])
        self.pwm_a = PWMOutputDevice(motor_cfg["pwm_a"], frequency=pwm_freq)

        # 右モーター（B）
        self.bin1 = OutputDevice(motor_cfg["bin1"])
        self.bin2 = OutputDevice(motor_cfg["bin2"])
        self.pwm_b = PWMOutputDevice(motor_cfg["pwm_b"], frequency=pwm_freq)

        # スタンバイピン
        self.stby = OutputDevice(motor_cfg["stby"])

        # モーター極性反転フラグ
        self.motor_a_invert = motor_cfg.get("motor_a_invert", False)
        self.motor_b_invert = motor_cfg.get("motor_b_invert", False)

        # 左モーター速度補正（個体差・履帯テンション差の調整用）
        self.motor_a_speed_offset = motor_cfg.get("motor_a_speed_offset", 0)

        # ドライバを有効化
        self.stby.on()

    def set_motor_a(self, speed: float):
        """
        左モーター制御。speed: -100(後退)〜0(停止)〜100(前進)
        speed > 0: AIN1=H / AIN2=L / PWMA=speed/100
        speed < 0: AIN1=L / AIN2=H / PWMA=abs(speed)/100
        speed == 0: AIN1=L / AIN2=L / PWMA=0（コースト停止）
        """
        speed = max(-100.0, min(100.0, float(speed)))
        if speed != 0 and self.motor_a_speed_offset != 0:
            speed = speed + (self.motor_a_speed_offset if speed > 0 else -self.motor_a_speed_offset)
            speed = max(-100.0, min(100.0, speed))
        if self.motor_a_invert:
            speed = -speed
        if speed > 0:
            self.ain1.on()
            self.ain2.off()
            self.pwm_a.value = speed / 100.0
        elif speed < 0:
            self.ain1.off()
            self.ain2.on()
            self.pwm_a.value = abs(speed) / 100.0
        else:
            self.ain1.off()
            self.ain2.off()
            self.pwm_a.value = 0

    def set_motor_b(self, speed: float):
        """
        右モーター制御。speed: -100(後退)〜0(停止)〜100(前進)
        motor_b_invert=True の場合は speed の符号を反転してから set_motor_a と同様の制御を行う。
        """
        speed = max(-100.0, min(100.0, float(speed)))
        if self.motor_b_invert:
            speed = -speed

        if speed > 0:
            self.bin1.on()
            self.bin2.off()
            self.pwm_b.value = speed / 100.0
        elif speed < 0:
            self.bin1.off()
            self.bin2.on()
            self.pwm_b.value = abs(speed) / 100.0
        else:
            self.bin1.off()
            self.bin2.off()
            self.pwm_b.value = 0

    def stop(self):
        """両モーターをコースト停止（set_motor_a(0), set_motor_b(0)）"""
        self.set_motor_a(0)
        self.set_motor_b(0)

    def brake(self):
        """両モーターをブレーキ停止（AIN1=H/AIN2=H, BIN1=H/BIN2=H）"""
        self.ain1.on()
        self.ain2.on()
        self.pwm_a.value = 1
        self.bin1.on()
        self.bin2.on()
        self.pwm_b.value = 1

    def cleanup(self):
        """STBY を LOW にしてドライバをスタンバイ状態にする"""
        self.stop()
        self.stby.off()
