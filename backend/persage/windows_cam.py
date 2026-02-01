import cv2
import time
from flask import Flask, Response, jsonify
import threading

app = Flask(__name__)

CAMERA_INDEX = None
TARGET_FPS = 30
FRAME_INTERVAL_S = 1.0 / TARGET_FPS
JPEG_QUALITY = 85  # Higher = better for breathing detection (chest movement)

# Thread-safe camera access
camera_lock = threading.Lock()
current_frame = None
frame_ready = threading.Event()


def find_working_camera():
    """Find first working camera index."""
    for i in range(5):
        cap = cv2.VideoCapture(i, cv2.CAP_DSHOW)
        if cap.isOpened():
            ret, _ = cap.read()
            if ret:
                print(f"Found camera at index {i}")
                cap.release()
                return i
            cap.release()
    return None


def camera_capture_thread():
    """Background thread that continuously captures frames."""
    global current_frame, CAMERA_INDEX
    
    camera = None
    consecutive_failures = 0
    
    while True:
        # Open camera if needed
        if camera is None or not camera.isOpened():
            print("[Camera] Opening camera...")
            try:
                camera = cv2.VideoCapture(CAMERA_INDEX, cv2.CAP_DSHOW)
                if camera.isOpened():
                    camera.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                    camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                    camera.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                    camera.set(cv2.CAP_PROP_FPS, TARGET_FPS)
                    # Flush buffer to get freshest frame (reduces stale frame latency)
                    for _ in range(10):
                        camera.grab()
                    consecutive_failures = 0
                    print("[Camera] Opened successfully")
                else:
                    print("[Camera] Failed to open, retrying...")
                    time.sleep(2)
                    continue
            except Exception as e:
                print(f"[Camera] Error opening: {e}")
                time.sleep(2)
                continue
        
        # Capture frame
        try:
            if camera.grab():
                ret, frame = camera.retrieve()
                if ret and frame is not None:
                    # Encode to JPEG (lower quality = faster, smaller)
                    ret, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
                    if ret:
                        with camera_lock:
                            current_frame = buffer.tobytes()
                        frame_ready.set()
                        consecutive_failures = 0
                    else:
                        consecutive_failures += 1
                else:
                    consecutive_failures += 1
            else:
                consecutive_failures += 1
            
            # Reconnect camera after too many failures
            if consecutive_failures > 30:
                print("[Camera] Too many failures, reconnecting...")
                if camera:
                    camera.release()
                camera = None
                consecutive_failures = 0
                continue
            
            # Rate limit
            time.sleep(FRAME_INTERVAL_S)
            
        except Exception as e:
            print(f"[Camera] Capture error: {e}")
            consecutive_failures += 1
            time.sleep(0.1)


def generate_frames():
    """Generate MJPEG stream - yield immediately when new frame available."""
    while True:
        frame_ready.wait(timeout=1.0)
        
        with camera_lock:
            frame_data = current_frame
        
        if frame_data:
            frame_ready.clear()  # Allow capture thread to signal next frame
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame_data + b'\r\n')


@app.route('/')
def video_feed():
    """MJPEG video stream."""
    return Response(
        generate_frames(),
        mimetype='multipart/x-mixed-replace; boundary=frame'
    )


@app.route('/health')
def health():
    """Health check endpoint."""
    return jsonify({
        "status": "ok",
        "camera_index": CAMERA_INDEX,
        "has_frame": current_frame is not None
    })


if __name__ == '__main__':
    print("=" * 50)
    print("SmartSpectra Camera Server")
    print("=" * 50)
    
    CAMERA_INDEX = find_working_camera()
    if CAMERA_INDEX is None:
        print("Error: No camera found")
        exit(1)

    print(f"Using camera index {CAMERA_INDEX}")
    
    # Start background capture thread
    capture_thread = threading.Thread(target=camera_capture_thread, daemon=True)
    capture_thread.start()
    
    # Wait for first frame
    print("Waiting for first frame...")
    frame_ready.wait(timeout=10)
    
    if current_frame is None:
        print("Error: Could not capture initial frame")
        exit(1)
    
    print("Camera ready!")
    print("Starting server on http://0.0.0.0:5000")
    print("Press Ctrl+C to stop")
    print("=" * 50)
    
    app.run(host='0.0.0.0', port=5000, threaded=True, debug=False)
