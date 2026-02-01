import asyncio
import json
import websockets
import os
import subprocess
import shutil
import time
import requests
import signal
import sys
from pathlib import Path
import socket
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import platform

# CONFIG
API_KEY = "iOU9ZoC5omYKKt9y6M3KjfP0Qz7bfk9s2gJUTz80"
CPP_PATH = "./build/headless_vitals"
FRAME_DIR = "/tmp/presage_frames"  # macOS: use /tmp instead of /dev/shm
TARGET_FPS = 30
FRAME_INTERVAL_S = 1.0 / TARGET_FPS
FRAME_INTERVAL_US = int(1_000_000 / TARGET_FPS)
MAX_BUFFERED_FRAMES = 45  # ~1.5s - enough for breathing detection

# Global state
stop_event = threading.Event()
cpp_process = None
frame_bridge_healthy = threading.Event()

# Latest vitals for HTTP /vitals endpoint (main backend queries this)
latest_vitals = {"heart_rate": 75.0, "respiration_rate": 16.0, "timestamp": 0}
VITALS_HTTP_PORT = 8766


def get_camera_host_ip():
    """Get the IP where the camera server is running (localhost for macOS)."""
    return "127.0.0.1"  # Camera server runs on same machine for macOS


def setup_frame_dir():
    """Create/clean the frame directory on macOS."""
    global FRAME_DIR
    
    # Try different locations for macOS
    candidates = ["/tmp/presage_frames", f"{os.environ.get('HOME', '')}/tmp/presage_frames"]
    
    for candidate in candidates:
        try:
            path = Path(candidate)
            parent = path.parent
            if parent.exists() and os.access(parent, os.W_OK):
                if path.exists():
                    shutil.rmtree(path)
                path.mkdir(parents=True, exist_ok=True)
                FRAME_DIR = candidate
                print(f"[Setup] Frame directory: {FRAME_DIR}")
                return
        except Exception as e:
            print(f"[Setup] Failed to create {candidate}: {e}")
            continue
    
    raise RuntimeError("Could not create frame directory")


def fetch_mjpeg_stream(camera_url):
    """Connect to MJPEG stream with retry. Returns response or None."""
    max_retries = 10
    retry_delay = 2
    
    for attempt in range(max_retries):
        if stop_event.is_set():
            return None
        try:
            response = requests.get(camera_url, stream=True, timeout=15)
            response.raise_for_status()
            return response
        except Exception as e:
            print(f"[FrameBridge] Connection attempt {attempt + 1}/{max_retries} failed: {e}")
            if attempt == 0:
                print(f"[FrameBridge] Make sure camera server is running: python mac_cam.py")
            time.sleep(retry_delay)
    
    return None


def fetch_mjpeg_frames_sync(camera_url, stop_event):
    """Fetch MJPEG frames continuously with auto-reconnect."""
    
    while not stop_event.is_set():
        print(f"[FrameBridge] Connecting to {camera_url}...")
        frame_bridge_healthy.clear()
        
        response = fetch_mjpeg_stream(camera_url)
        if response is None:
            print("[FrameBridge] Failed to connect, retrying in 5s...")
            time.sleep(5)
            continue
        
        print(f"[FrameBridge] Connected, streaming at {TARGET_FPS} fps...")
        frame_bridge_healthy.set()
        
        buffer = b""
        frame_count = 0
        last_write_time = time.perf_counter()
        next_timestamp_us = int(time.time() * 1_000_000)
        
        try:
            for chunk in response.iter_content(chunk_size=65536):  # 64KB = fewer syscalls
                if stop_event.is_set():
                    break
                
                if not chunk:
                    continue
                
                buffer += chunk
                
                # Look for JPEG frame boundaries
                while True:
                    start = buffer.find(b'\xff\xd8')  # JPEG SOI
                    if start == -1:
                        break
                    
                    end = buffer.find(b'\xff\xd9', start + 2)  # JPEG EOI
                    if end == -1:
                        break
                    
                    end += 2  # Include EOI marker
                    
                    # Extract frame
                    frame_data = buffer[start:end]
                    buffer = buffer[end:]
                    
                    # Throttle to target FPS
                    current_time = time.perf_counter()
                    time_since_last = current_time - last_write_time
                    if time_since_last < FRAME_INTERVAL_S:
                        continue  # Skip frame
                    
                    # Write frame with microsecond timestamp
                    frame_filename = f"frame{next_timestamp_us:019d}.jpg"
                    frame_path = Path(FRAME_DIR) / frame_filename
                    
                    try:
                        frame_path.write_bytes(frame_data)
                        frame_count += 1
                        last_write_time = current_time
                        next_timestamp_us += FRAME_INTERVAL_US
                        
                        # Manage buffer size
                        if frame_count % 10 == 0:  # Every 10 frames
                            cleanup_old_frames()
                        
                    except Exception as e:
                        print(f"[FrameBridge] Frame write error: {e}")
                        
        except Exception as e:
            print(f"[FrameBridge] Stream error: {e}")
            frame_bridge_healthy.clear()
            time.sleep(5)


def cleanup_old_frames():
    """Remove old frames to prevent disk overflow."""
    try:
        frame_files = sorted(Path(FRAME_DIR).glob("frame*.jpg"))
        if len(frame_files) > MAX_BUFFERED_FRAMES:
            for old_frame in frame_files[:-MAX_BUFFERED_FRAMES]:
                old_frame.unlink()
    except Exception as e:
        print(f"[Cleanup] Error: {e}")


def start_cpp_vitals():
    """Start the C++ vitals processing (if SDK available)."""
    global cpp_process
    
    if not Path(CPP_PATH).exists():
        print(f"[CPP] Warning: {CPP_PATH} not found")
        print("[CPP] SmartSpectra SDK for macOS is not publicly available yet")
        print("[CPP] Contact support@presagetech.com for access")
        print("[CPP] Running without vitals processing...")
        return False
    
    try:
        env = os.environ.copy()
        env['SMARTSPECTRA_API_KEY'] = API_KEY
        env['FRAME_DIR'] = FRAME_DIR
        
        cpp_process = subprocess.Popen(
            [CPP_PATH],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            universal_newlines=True,
            env=env
        )
        print(f"[CPP] Started vitals processing (PID: {cpp_process.pid})")
        return True
        
    except Exception as e:
        print(f"[CPP] Failed to start: {e}")
        return False


def process_cpp_output():
    """Process output from C++ vitals detection."""
    global latest_vitals
    
    if cpp_process is None:
        return
    
    try:
        for line in cpp_process.stdout:
            if stop_event.is_set():
                break
            
            line = line.strip()
            if not line:
                continue
            
            try:
                data = json.loads(line)
                if data.get("type") == "vitals":
                    pulse = data.get("pulse", 0)
                    breathing = data.get("breathing", 0)
                    
                    if pulse > 0 or breathing > 0:
                        latest_vitals = {
                            "heart_rate": float(pulse) if pulse > 0 else latest_vitals["heart_rate"],
                            "respiration_rate": float(breathing) if breathing > 0 else latest_vitals["respiration_rate"],
                            "timestamp": int(time.time())
                        }
                        print(f"[Vitals] HR: {latest_vitals['heart_rate']:.1f}, BR: {latest_vitals['respiration_rate']:.1f}")
            except json.JSONDecodeError:
                print(f"[CPP] Non-JSON output: {line}")
                
    except Exception as e:
        print(f"[CPP] Output processing error: {e}")


class VitalsHTTPHandler(BaseHTTPRequestHandler):
    """HTTP handler for /vitals endpoint."""
    
    def do_GET(self):
        if self.path == '/vitals':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            
            response_data = {
                **latest_vitals,
                "status": "healthy" if frame_bridge_healthy.is_set() else "unhealthy",
                "platform": platform.system()
            }
            self.wfile.write(json.dumps(response_data).encode())
        else:
            self.send_error(404)
    
    def log_message(self, format, *args):
        # Suppress HTTP logs
        pass


async def websocket_handler(websocket, path):
    """WebSocket handler for real-time vitals streaming."""
    print(f"[WS] Client connected from {websocket.remote_address}")
    
    try:
        while not stop_event.is_set():
            # Send vitals data
            data = {
                "type": "vitals",
                **latest_vitals,
                "frame_bridge_healthy": frame_bridge_healthy.is_set()
            }
            
            await websocket.send(json.dumps(data))
            await asyncio.sleep(1.0)  # Send every second
            
    except websockets.exceptions.ConnectionClosed:
        print(f"[WS] Client disconnected")
    except Exception as e:
        print(f"[WS] Error: {e}")


def signal_handler(sig, frame):
    """Handle shutdown signals."""
    print(f"\n[Shutdown] Received signal {sig}")
    stop_event.set()
    
    if cpp_process:
        print("[Shutdown] Stopping C++ process...")
        cpp_process.terminate()
        cpp_process.wait(timeout=5)
    
    sys.exit(0)


async def main():
    """Main async function."""
    print("=== Persage Broker for macOS ===")
    print(f"Platform: {platform.system()}")
    print(f"Frame directory: {FRAME_DIR}")
    
    # Setup
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        setup_frame_dir()
    except Exception as e:
        print(f"[Error] {e}")
        return
    
    # Start HTTP server for /vitals endpoint
    http_server = HTTPServer(('0.0.0.0', VITALS_HTTP_PORT), VitalsHTTPHandler)
    http_thread = threading.Thread(target=http_server.serve_forever, daemon=True)
    http_thread.start()
    print(f"[HTTP] Vitals endpoint: http://localhost:{VITALS_HTTP_PORT}/vitals")
    
    # Start frame bridge
    camera_url = f"http://{get_camera_host_ip()}:5001/video_feed"
    frame_thread = threading.Thread(
        target=fetch_mjpeg_frames_sync, 
        args=(camera_url, stop_event), 
        daemon=True
    )
    frame_thread.start()
    
    # Start C++ vitals processing (if available)
    if start_cpp_vitals():
        cpp_thread = threading.Thread(target=process_cpp_output, daemon=True)
        cpp_thread.start()
    else:
        print("[Warning] Running without real vitals - using mock data")
    
    # Start WebSocket server
    print(f"[WebSocket] Starting server on ws://localhost:8765")
    print("\nTo test the setup:")
    print("1. Start camera server: python mac_cam.py")
    print("2. Check camera: curl http://localhost:5001/status")
    print("3. Check vitals: curl http://localhost:8766/vitals")
    print("4. Start main backend: uvicorn app:app --host 0.0.0.0 --port 8000")
    print("\nPress Ctrl+C to stop")
    
    start_server = websockets.serve(websocket_handler, "0.0.0.0", 8765)
    await start_server
    
    # Keep running
    while not stop_event.is_set():
        await asyncio.sleep(1)


if __name__ == "__main__":
    asyncio.run(main())