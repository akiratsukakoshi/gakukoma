import cv2
import sys
import os

def detect_faces(input_data) -> list[dict]:
    """
    input_data: image_path (str) OR image_frame (numpy array)
    戻り値: [{"x": int, "y": int, "w": int, "h": int, "cx": int, "cy": int}, ...]
    cx, cy は矩形の中心座標
    顔が見つからない場合は空リスト []
    """
    image = None
    if isinstance(input_data, str):
        if not os.path.exists(input_data):
            return []
        image = cv2.imread(input_data)
    else:
        image = input_data

    if image is None:
        return []
        
    # Haar Cascade ファイルの検索
    possible_paths = [
        os.path.join(cv2.data.haarcascades, "haarcascade_frontalface_default.xml") if hasattr(cv2, 'data') else None,
        "/usr/share/opencv4/haarcascades/haarcascade_frontalface_default.xml",
        "/usr/share/opencv/haarcascades/haarcascade_frontalface_default.xml"
    ]
    
    cascade_path = None
    for path in possible_paths:
        if path and os.path.exists(path):
            cascade_path = path
            break
            
    if not cascade_path:
        print("Error: Haar Cascade file not found.")
        return []
        
    face_cascade = cv2.CascadeClassifier(cascade_path)
    
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    
    faces = face_cascade.detectMultiScale(
        gray,
        scaleFactor=1.1,
        minNeighbors=3,
        minSize=(30, 30)
    )
    
    results = []
    for (x, y, w, h) in faces:
        results.append({
            "x": int(x),
            "y": int(y),
            "w": int(w),
            "h": int(h),
            "cx": int(x + w // 2),
            "cy": int(y + h // 2)
        })
        
    return results

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 face_detect.py <image_path>")
        sys.exit(1)
        
    image_path = sys.argv[1]
    results = detect_faces(image_path)
    
    print(f"検出件数: {len(results)}")
    for i, face in enumerate(results):
        print(f"Face {i+1}: Center({face['cx']}, {face['cy']}), Rect({face['x']}, {face['y']}, {face['w']}, {face['h']})")
