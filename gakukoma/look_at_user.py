import sys
import time
import yaml
import os
import json

# プロジェクトルートをパスに追加
sys.path.append('/home/tukapontas/gakukoma')

from camera.capture import CameraCapture
from camera.face_detect import detect_faces
from camera.face_recognizer import FaceRecognizer
from servo.pan_tilt import PanTiltController

def main():
    CONFIG_PATH = os.path.expanduser("~/gakukoma/voice_loop/config.yaml")
    
    try:
        with open(CONFIG_PATH, 'r') as f:
            config = yaml.safe_load(f)
    except Exception as e:
        print(f"設定ファイルの読み込みに失敗しました: {e}")
        sys.exit(1)

    servo_cfg = config.get('servo', {})
    cam_cfg = config.get('camera', {})
    
    pan_gain = servo_cfg.get('pan_gain', 0.1)
    tilt_gain = servo_cfg.get('tilt_gain', 0.1)
    convergence_px = servo_cfg.get('convergence_px', 30)
    max_iterations = servo_cfg.get('max_iterations', 20)
    loop_interval = servo_cfg.get('loop_interval', 0.1)
    
    width = cam_cfg.get('width', 640)
    height = cam_cfg.get('height', 480)
    center_x = width / 2
    center_y = height / 2

    # 初期化
    try:
        cam = CameraCapture(device_id=cam_cfg.get('device', 0))
    except Exception as e:
        print(f"カメラが見つかりません: {e}")
        sys.exit(1)
        
    # サーボはオプション（PCA9685が未接続・電源OFFでも顔識別は続行）
    pt = None
    servo_lock_acquired = False
    try:
        pt = PanTiltController(CONFIG_PATH)
        if not pt._lock.acquire(blocking=False):
            print("look_at_user: サーボロック取得失敗（他操作が実行中）", file=sys.stderr)
            pt = None
        else:
            servo_lock_acquired = True
            pt.center()
            time.sleep(0.5)
    except Exception as e:
        print(f"サーボ初期化失敗（顔識別のみ実行）: {e}", file=sys.stderr)
        pt = None

    try:
        # ウォームアップ（明るさを安定させる）
        for _ in range(5):
            cam.capture()

        face_not_found_count = 0
        success = False
        final_pan = 90
        final_tilt = 90
        last_frame = None

        for i in range(max_iterations):
            frame = cam.capture()
            if frame is None:
                print("フレームの取得に失敗しました", file=sys.stderr)
                break

            faces = detect_faces(frame)

            if not faces:
                face_not_found_count += 1
                if face_not_found_count >= 3:
                    break
                time.sleep(loop_interval)
                continue

            face_not_found_count = 0
            last_frame = frame

            if pt is None:
                # サーボなし: 顔検出できたら即終了（識別へ進む）
                success = True
                break

            # 最大面積の顔を選択
            best_face = max(faces, key=lambda f: f['w'] * f['h'])

            cx = best_face['x'] + best_face['w'] / 2
            cy = best_face['y'] + best_face['h'] / 2

            dx = cx - center_x
            dy = cy - center_y

            # 収束判定
            if abs(dx) < convergence_px and abs(dy) < convergence_px:
                success = True
                final_pan = pt.current_pan
                final_tilt = pt.current_tilt
                last_frame = frame
                break

            # 角度補正
            new_pan = pt.current_pan + (dx * pan_gain)
            new_tilt = pt.current_tilt + (dy * tilt_gain)

            pt.set_pan(int(new_pan))
            pt.set_tilt(int(new_tilt))

            time.sleep(loop_interval)

        # 顔識別: 顔が1フレームでも検出できていれば実行
        person_name = None
        if last_frame is not None:
            try:
                recognizer = FaceRecognizer()
                person_name = recognizer.identify(last_frame)
            except Exception as e:
                print(f"顔識別エラー: {e}", file=sys.stderr)

        result = {
            "success": success,
            "pan": final_pan,
            "tilt": final_tilt,
            "identified": person_name  # "学長" / "unknown" / None
        }

        print(json.dumps(result, ensure_ascii=False))

    finally:
        cam.release()
        if pt is not None and servo_lock_acquired:
            pt._lock.release()

if __name__ == "__main__":
    main()
