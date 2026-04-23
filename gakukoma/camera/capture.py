import cv2
import yaml
import os

class CameraCapture:
    def __init__(self, config_path="~/gakukoma/voice_loop/config.yaml", device_id=None):
        config_path = os.path.expanduser(config_path)
        with open(config_path, "r") as f:
            self.config = yaml.safe_load(f)
        
        camera_conf = self.config.get("camera", {})
        self.device = device_id if device_id is not None else camera_conf.get("device", 0)
        self.width = camera_conf.get("width", 640)
        self.height = camera_conf.get("height", 480)
        self.capture_file = camera_conf.get("capture_file", "/tmp/gakukoma_capture.jpg")
        
        # V4L2バックエンドを明示することでFOURCC指定が確実に反映される
        self.cap = cv2.VideoCapture(self.device, cv2.CAP_V4L2)
        if not self.cap.isOpened():
            raise RuntimeError(f"Could not open camera device {self.device}")

        # MJPEGを先に指定してから解像度を設定（YUYVは640x480までしか対応しないため）
        self.cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc('M', 'J', 'P', 'G'))
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)

    def capture_frame(self) -> str:
        # ウォームアップ（数フレーム読み飛ばすことで明るさを安定させる）
        for _ in range(5):
            self.cap.read()
            
        ret, frame = self.cap.read()
        if not ret:
            raise RuntimeError("Failed to capture frame from camera")
            
        cv2.imwrite(self.capture_file, frame)
        return self.capture_file

    def capture(self):
        """Returns the frame object (BGR)"""
        ret, frame = self.cap.read()
        if not ret:
            return None
        return frame

    def release(self):
        if self.cap.isOpened():
            self.cap.release()

if __name__ == "__main__":
    # 単体テスト
    try:
        cam = CameraCapture()
        path = cam.capture_frame()
        print(f"Captured frame saved to: {path}")
        cam.release()
    except Exception as e:
        print(f"Error: {e}")
