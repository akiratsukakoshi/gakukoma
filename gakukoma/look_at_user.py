import sys
import time
import yaml
import os

# プロジェクトルートをパスに追加
sys.path.append('/home/tukapontas/gakukoma')

from camera.capture import CameraCapture
from camera.face_detect import detect_faces
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
        
    try:
        pt = PanTiltController(CONFIG_PATH)
    except Exception as e:
        print(f"サーボドライバが見つかりません（PCA9685未接続）: {e}")
        cam.release()
        sys.exit(1)

    # ロック取得
    if not pt._lock.acquire(blocking=False):
        print("look_at_user中断: 他のサーボ操作が実行中です")
        cam.release()
        sys.exit(1)

    try:
        # センターに向ける
        pt.center()
        time.sleep(0.5)
        
        # ウォームアップ（明るさを安定させる）
        for _ in range(5):
            cam.capture()

        face_not_found_count = 0
        success = False
        final_pan = 90
        final_tilt = 90

        for i in range(max_iterations):
            frame = cam.capture()
            if frame is None:
                print("フレームの取得に失敗しました")
                break
                
            faces = detect_faces(frame)
            
            if not faces:
                face_not_found_count += 1
                if face_not_found_count >= 3:
                    break
                time.sleep(loop_interval)
                continue
                
            face_not_found_count = 0
            
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
                break
                
            # 角度補正
            new_pan = pt.current_pan + (dx * pan_gain)
            new_tilt = pt.current_tilt + (dy * tilt_gain)
            
            pt.set_pan(int(new_pan))
            pt.set_tilt(int(new_tilt))
            
            time.sleep(loop_interval)

        if success:
            print(f"顔追跡成功: pan={final_pan}° tilt={final_tilt}°")
        else:
            print("タイムアウト: 顔が見つかりませんでした")

    finally:
        cam.release()
        pt._lock.release()

if __name__ == "__main__":
    main()
