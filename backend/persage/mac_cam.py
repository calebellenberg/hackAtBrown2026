import cv2
import time
from flask import Flask, Response, jsonify
import threading
import platform

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
    """Find first working camera index on macOS."""
    # Based on our test, camera 1 works
    working_cameras = []
    for i in range(5):  # Check first 5 indices
        try:
            cap = cv2.VideoCapture(i, cv2.CAP_AVFOUNDATION)
            if cap.isOpened():
                ret, _ = cap.read()
                if ret:
                    print(f"Found working camera at index {i}")
                    working_cameras.append(i)
                cap.release()
        except Exception as e:
            print(f"Error testing camera {i}: {e}")
    
    if working_cameras:
        return working_cameras[0]  # Return first working camera
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
                # Use AVFoundation backend for macOS
                camera = cv2.VideoCapture(CAMERA_INDEX, cv2.CAP_AVFOUNDATION)
                if camera.isOpened():
                    camera.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                    camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                    camera.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                    camera.set(cv2.CAP_PROP_FPS, TARGET_FPS)
                    print("[Camera] Camera opened successfully")
                    consecutive_failures = 0
                else:
                    raise Exception("Failed to open camera")
            except Exception as e:
                print(f"[Camera] Error: {e}")
                consecutive_failures += 1
                if consecutive_failures > 5:
                    print("[Camera] Too many failures, sleeping longer...")
                    time.sleep(10)
                else:
                    time.sleep(2)
                continue

        # Capture frame
        try:
            ret, frame = camera.read()
            if not ret:
                raise Exception("Failed to read frame")

            with camera_lock:
                current_frame = frame.copy()
                frame_ready.set()
            
            consecutive_failures = 0
            time.sleep(FRAME_INTERVAL_S)
            
        except Exception as e:
            print(f"[Camera] Capture error: {e}")
            consecutive_failures += 1
            if camera:
                camera.release()
                camera = None
            time.sleep(1)


def generate_mjpeg_stream():
    """Generate MJPEG stream for HTTP response."""
    while True:
        if not frame_ready.wait(timeout=1.0):
            # No frame available, send a placeholder or continue
            time.sleep(0.1)
            continue
        
        with camera_lock:
            if current_frame is not None:
                frame = current_frame.copy()
            else:
                continue
        
        # Encode frame as JPEG
        try:
            encode_params = [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY]
            success, buffer = cv2.imencode('.jpg', frame, encode_params)
            
            if success:
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')
            else:
                print("[Stream] Failed to encode frame")
        except Exception as e:
            print(f"[Stream] Encoding error: {e}")
            time.sleep(0.1)


@app.route('/video_feed')
def video_feed():
    """Video streaming endpoint."""
    return Response(generate_mjpeg_stream(),
                   mimetype='multipart/x-mixed-replace; boundary=frame')


@app.route('/status')
def status():
    """Camera status endpoint."""
    is_healthy = frame_ready.is_set() and current_frame is not None
    return jsonify({
        'status': 'healthy' if is_healthy else 'unhealthy',
        'platform': platform.system(),
        'camera_index': CAMERA_INDEX,
        'target_fps': TARGET_FPS,
        'frame_available': is_healthy
    })


@app.route('/info')
def info():
    """Camera info endpoint."""
    return jsonify({
        'platform': platform.system(),
        'opencv_version': cv2.__version__,
        'camera_backend': 'AVFoundation (macOS)',
        'target_fps': TARGET_FPS,
        'resolution': '640x480',
        'jpeg_quality': JPEG_QUALITY
    })


if __name__ == "__main__":
    print("=== macOS Camera Server for Persage ===")
    print(f"Platform: {platform.system()}")
    print(f"OpenCV Version: {cv2.__version__}")
    
    # Find camera
    CAMERA_INDEX = find_working_camera()
    if CAMERA_INDEX is None:
        print("ERROR: No working camera found!")
        print("Make sure:")
        print("1. Camera is connected and not used by other apps")
        print("2. Camera permissions are granted to Terminal/Python")
        print("3. Try running: tccutil reset Camera")
        exit(1)
    
    print(f"Using camera index: {CAMERA_INDEX}")
    
    # Start camera thread
    camera_thread = threading.Thread(target=camera_capture_thread, daemon=True)
    camera_thread.start()
    
    # Wait for first frame
    print("Waiting for camera initialization...")
    if frame_ready.wait(timeout=10):
        print("✓ Camera ready")
    else:
        print("⚠ Camera startup timeout - continuing anyway")
    
    # Start Flask server
    print("Starting MJPEG server on http://localhost:5001")
    print("Endpoints:")
    print("  - /video_feed - MJPEG stream")
    print("  - /status - Camera status")
    print("  - /info - Camera information")
    print("Press Ctrl+C to stop")
    
    try:
        app.run(host='0.0.0.0', port=5001, debug=False, threaded=True)
    except KeyboardInterrupt:
        print("\nShutting down...")