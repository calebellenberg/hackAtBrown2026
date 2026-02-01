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

# CONFIG
API_KEY = "iOU9ZoC5omYKKt9y6M3KjfP0Qz7bfk9s2gJUTz80"
CPP_PATH = "./build/headless_vitals"
FRAME_DIR = "/dev/shm/presage_frames"
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


def get_windows_ip():
    """Extracts the Windows host IP from WSL."""
    methods = [
        lambda: subprocess.check_output(
            "ip route show | grep default | awk '{print $3}'",
            shell=True,
        ).decode().strip(),
        lambda: subprocess.check_output(
            "grep nameserver /etc/resolv.conf | awk '{print $2}'",
            shell=True,
        ).decode().strip(),
    ]
    for method in methods:
        try:
            ip = method()
            if ip and ip != "127.0.0.1" and not ip.startswith("10.255"):
                print(f"[Setup] Detected Windows Host IP: {ip}")
                return ip
        except Exception:
            continue
    raise RuntimeError("Could not detect Windows host IP")


def setup_frame_dir():
    """Create/clean the frame directory."""
    global FRAME_DIR
    
    for candidate in ["/dev/shm/presage_frames", "/tmp/presage_frames"]:
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
                
                # Process all complete frames in buffer
                while True:
                    start = buffer.find(b'\xff\xd8')
                    end = buffer.find(b'\xff\xd9')
                    
                    if start == -1 or end == -1 or end <= start:
                        break
                    
                    jpeg_data = buffer[start:end + 2]
                    buffer = buffer[end + 2:]
                    
                    if len(jpeg_data) < 100:
                        continue
                    
                    # Minimal rate limit: only throttle if ahead of schedule
                    now = time.perf_counter()
                    elapsed = now - last_write_time
                    sleep_time = FRAME_INTERVAL_S - elapsed
                    if sleep_time > 0.005:  # Only sleep if >5ms to save
                        time.sleep(sleep_time)
                    
                    # Write frame with logical timestamp
                    timestamp_us = next_timestamp_us
                    next_timestamp_us += FRAME_INTERVAL_US
                    
                    filename = f"frame{timestamp_us:019d}.jpg"
                    filepath = os.path.join(FRAME_DIR, filename)
                    
                    try:
                        with open(filepath, 'wb') as f:
                            f.write(jpeg_data)
                        frame_count += 1
                        last_write_time = time.perf_counter()
                        
                        if frame_count % 10 == 0:  # Cleanup more often
                            cleanup_old_frames()
                    except Exception:
                        pass
                
                # Limit buffer size to prevent memory growth
                if len(buffer) > 500000:
                    buffer = buffer[-100000:]
                    
        except requests.exceptions.ChunkedEncodingError:
            print("[FrameBridge] Stream interrupted (chunked encoding error)")
        except requests.exceptions.ConnectionError:
            print("[FrameBridge] Connection lost")
        except Exception as e:
            print(f"[FrameBridge] Stream error: {type(e).__name__}: {e}")
        
        frame_bridge_healthy.clear()
        print(f"[FrameBridge] Disconnected after {frame_count} frames, reconnecting...")
        time.sleep(2)
    
    print("[FrameBridge] Stopped")


def cleanup_old_frames():
    """Remove old frames, keeping the most recent ones."""
    try:
        path = Path(FRAME_DIR)
        frames = sorted(path.glob("frame*.jpg"))
        if len(frames) > MAX_BUFFERED_FRAMES:
            for f in frames[:-MAX_BUFFERED_FRAMES]:
                try:
                    f.unlink()
                except Exception:
                    pass
    except Exception:
        pass


async def log_stderr(process):
    """Log C++ stderr."""
    try:
        async for line in process.stderr:
            decoded = line.decode(errors="replace").strip()
            if decoded and not decoded.startswith("I0000"):
                print(f"[C++ STDERR] {decoded}")
    except Exception:
        pass


async def run_cpp_process(clients):
    """Run the C++ SDK process."""
    global cpp_process
    
    env = os.environ.copy()
    env["SMARTSPECTRA_API_KEY"] = API_KEY
    env["FRAME_DIR"] = FRAME_DIR

    print(f"[SDK] Starting C++ process...")

    try:
        cpp_process = await asyncio.create_subprocess_exec(
            CPP_PATH,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
    except Exception as e:
        print(f"[SDK] Failed to start: {e}")
        return 1

    asyncio.create_task(log_stderr(cpp_process))

    try:
        while cpp_process.returncode is None:
            try:
                line = await asyncio.wait_for(cpp_process.stdout.readline(), timeout=5.0)
            except asyncio.TimeoutError:
                continue

            if not line:
                break

            text = line.decode(errors="replace").strip()
            if text.startswith("{"):
                try:
                    websockets.broadcast(clients, text)
                    data = json.loads(text)
                    if data.get("type") == "vitals":
                        latest_vitals["heart_rate"] = float(data.get("pulse", 75.0))
                        latest_vitals["respiration_rate"] = float(data.get("breathing", 16.0))
                        latest_vitals["timestamp"] = time.time()
                except Exception:
                    pass
                print(f"[Vitals] {text}")
            elif text:
                print(f"[SDK] {text}")
                
    except Exception as e:
        print(f"[SDK] Error: {e}")
    
    # Wait for process to finish
    if cpp_process.returncode is None:
        try:
            await asyncio.wait_for(cpp_process.wait(), timeout=2.0)
        except asyncio.TimeoutError:
            cpp_process.terminate()
            await asyncio.sleep(0.5)
            if cpp_process.returncode is None:
                cpp_process.kill()
    
    return cpp_process.returncode or 0


def run_vitals_http_server():
    """Run HTTP server for /vitals endpoint (main backend queries this)."""
    class VitalsHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/vitals":
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps(latest_vitals).encode())
            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, format, *args):
            pass  # Suppress HTTP log noise

    server = HTTPServer(("0.0.0.0", VITALS_HTTP_PORT), VitalsHandler)
    server.socket.settimeout(1.0)
    while not stop_event.is_set():
        try:
            server.handle_request()
        except (socket.timeout, OSError):
            pass
        except Exception:
            pass


def signal_handler(sig, frame):
    """Handle Ctrl+C."""
    print("\n[Shutdown] Received interrupt signal")
    stop_event.set()
    sys.exit(0)


async def main():
    global stop_event
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    clients = set()

    async def handler(ws):
        clients.add(ws)
        print(f"[WebSocket] Client connected ({len(clients)} total)")
        try:
            await ws.wait_closed()
        except Exception:
            pass
        finally:
            clients.discard(ws)
            print(f"[WebSocket] Client disconnected ({len(clients)} remaining)")

    # Get Windows IP
    windows_ip = get_windows_ip()
    camera_url = f"http://{windows_ip}:5000"
    
    # Setup frame directory
    setup_frame_dir()
    
    # Verify camera stream
    print(f"[Setup] Verifying camera stream at {camera_url}...")
    try:
        resp = requests.get(f"{camera_url}/health", timeout=5)
        if resp.status_code != 200:
            raise Exception(f"Status {resp.status_code}")
        print("[Setup] Camera stream OK")
    except Exception as e:
        print(f"[Error] Camera not reachable: {e}")
        print("[Hint] Start windows_cam.py on Windows first")
        return

    # Start frame bridge (runs forever with auto-reconnect)
    print(f"[Setup] Starting frame bridge...")
    bridge_thread = threading.Thread(
        target=fetch_mjpeg_frames_sync,
        args=(camera_url, stop_event),
        daemon=True
    )
    bridge_thread.start()
    
    # Wait for frames
    print("[Setup] Waiting for frames...")
    for _ in range(10):
        await asyncio.sleep(0.5)
        if len(list(Path(FRAME_DIR).glob("frame*.jpg"))) > 5:
            break
    
    frame_count = len(list(Path(FRAME_DIR).glob("frame*.jpg")))
    if frame_count == 0:
        print("[Error] No frames received")
        stop_event.set()
        return
    print(f"[Setup] {frame_count} frames ready")

    # Start HTTP server for /vitals (main backend)
    http_thread = threading.Thread(target=run_vitals_http_server, daemon=True)
    http_thread.start()
    print(f"[HTTP] Vitals endpoint http://localhost:{VITALS_HTTP_PORT}/vitals")

    # Start WebSocket Server
    server = await websockets.serve(handler, "0.0.0.0", 8765)
    print("[WebSocket] Server running on ws://localhost:8765")
    
    # Run C++ with auto-restart
    restart_delay = 3
    consecutive_failures = 0
    
    while not stop_event.is_set():
        # Wait for frame bridge to be healthy
        if not frame_bridge_healthy.is_set():
            print("[SDK] Waiting for frame bridge...")
            await asyncio.sleep(2)
            continue
        
        exit_code = await run_cpp_process(clients)
        
        if stop_event.is_set():
            break
        
        if exit_code != 0:
            consecutive_failures += 1
            delay = min(restart_delay * consecutive_failures, 30)
            print(f"[SDK] Exited with code {exit_code}, restarting in {delay}s...")
            await asyncio.sleep(delay)
        else:
            consecutive_failures = 0
            await asyncio.sleep(restart_delay)
    
    stop_event.set()
    print("[Shutdown] Done")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[Shutdown] Interrupted")
    except Exception as e:
        print(f"\n[Shutdown] Error: {e}")
    finally:
        stop_event.set()
