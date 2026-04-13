import yaml
import os
import threading
import fcntl
from servo.pca9685_ctrl import PCA9685Controller

class CrossProcessLock:
    """プロセスを跨いで利用可能なファイルベースのロック（threading.Lock互換インターフェース）"""
    def __init__(self, lock_file):
        self.lock_file_path = lock_file
        self._lock_file = None
        self._locked = False

    def acquire(self, blocking=True):
        if self._lock_file is None:
            # ロック用ファイルを開く（存在しなければ作成）
            self._lock_file = open(self.lock_file_path, "w")
        
        try:
            flags = fcntl.LOCK_EX
            if not blocking:
                flags |= fcntl.LOCK_NB
            fcntl.flock(self._lock_file, flags)
            self._locked = True
            return True
        except IOError:
            return False

    def release(self):
        if self._locked and self._lock_file:
            fcntl.flock(self._lock_file, fcntl.LOCK_UN)
            self._locked = False

class PanTiltController:
    """パン・チルト台座の2軸制御クラス"""

    def __init__(self, config_path="~/gakukoma/voice_loop/config.yaml"):
        config_path = os.path.expanduser(config_path)
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
        
        self.servo_cfg = config.get('servo', {})
        self.pan_channel = self.servo_cfg.get('pan_channel', 0)
        self.tilt_channel = self.servo_cfg.get('tilt_channel', 1)
        self.pan_min = self.servo_cfg.get('pan_min', 10)
        self.pan_max = self.servo_cfg.get('pan_max', 170)
        self.pan_offset = self.servo_cfg.get('pan_offset', 0)
        self.tilt_min = self.servo_cfg.get('tilt_min', 60)
        self.tilt_max = self.servo_cfg.get('tilt_max', 120)
        self.tilt_invert = self.servo_cfg.get('tilt_invert', False)
        
        self._ctrl = None
        self.current_pan = 90
        self.current_tilt = 90
        # T-12要件（プロセス間競合防止）のためファイルロックを使用
        self._lock = CrossProcessLock("/tmp/gakukoma_servo.lock")

    @property
    def ctrl(self):
        if self._ctrl is None:
            self._ctrl = PCA9685Controller()
        return self._ctrl

    def set_pan(self, angle: int):
        try:
            # 物理オフセット補正
            adjusted_angle = angle + self.pan_offset
            # 許容範囲内にクランプ
            clamped_angle = max(self.pan_min, min(self.pan_max, adjusted_angle))
            self.ctrl.set_angle(self.pan_channel, clamped_angle)
            self.current_pan = clamped_angle
        except OSError as e:
            return f"サーボ制御エラー: I2C通信失敗 ({e}). i2cdetect -y 1 で配線を確認してください。"

    def set_tilt(self, angle: int):
        try:
            clamped_angle = max(self.tilt_min, min(self.tilt_max, angle))
            if self.tilt_invert:
                physical_angle = self.tilt_min + self.tilt_max - clamped_angle
            else:
                physical_angle = clamped_angle
            self.ctrl.set_angle(self.tilt_channel, physical_angle)
            self.current_tilt = clamped_angle
        except OSError as e:
            return f"サーボ制御エラー: I2C通信失敗 ({e}). i2cdetect -y 1 で配線を確認してください。"

    def center(self):
        self.set_pan(90)
        self.set_tilt(90)

    def release(self):
        if self._ctrl:
            self._ctrl.release()

    def look_direction(self, direction: str) -> str:
        if not self._lock.acquire(blocking=False):
            return "look_direction失敗: 他の操作が実行中です"
        try:
            direction_map = {
                "front": (90, 90), "center": (90, 90), "正面": (90, 90), "中央": (90, 90),
                "right": (45, 90), "右": (45, 90),
                "left": (self.pan_max, 90), "左": (self.pan_max, 90),
                "up": (90, self.tilt_min), "上": (90, self.tilt_min),
                "down": (90, self.tilt_max), "下": (90, self.tilt_max),
                "upper-right": (45, self.tilt_min), "右上": (45, self.tilt_min),
                "upper-left": (self.pan_max, self.tilt_min), "左上": (self.pan_max, self.tilt_min),
                "lower-right": (45, self.tilt_max), "右下": (45, self.tilt_max),
                "lower-left": (self.pan_max, self.tilt_max), "左下": (self.pan_max, self.tilt_max),
            }
            key = direction.lower().strip()
            if key not in direction_map and direction.strip() not in direction_map:
                return f"look_direction失敗: 未知の方向 '{direction}'"
            pan, tilt = direction_map.get(key) or direction_map.get(direction.strip())
            res1 = self.set_pan(pan)
            if isinstance(res1, str): return res1
            res2 = self.set_tilt(tilt)
            if isinstance(res2, str): return res2
            return f"look_direction成功: pan={self.current_pan}° tilt={self.current_tilt}°"
        finally:
            self._lock.release()
    def look_center(self) -> str:
        if not self._lock.acquire(blocking=False):
            return "look_center失敗: 他の操作が実行中です"
        try:
            self.set_pan(90)
            self.set_tilt(90)
            # self.release() は最新の指示(20260319)に従い、脱力防止のため呼ばない
            return "look_center成功: pan=90° tilt=90°"
        finally:
            self._lock.release()

    def set_pan_tilt(self, pan: float, tilt: float) -> str:
        if not self._lock.acquire(blocking=False):
            return "set_pan_tilt失敗: 他の操作が実行中です"
        try:
            res1 = self.set_pan(int(pan))
            if isinstance(res1, str): return res1
            res2 = self.set_tilt(int(tilt))
            if isinstance(res2, str): return res2
            return f"set_pan_tilt成功: pan={self.current_pan}° tilt={self.current_tilt}°"
        finally:
            self._lock.release()
