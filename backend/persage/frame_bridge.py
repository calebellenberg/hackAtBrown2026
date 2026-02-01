#!/usr/bin/env python3
"""
Frame bridge: fetches MJPEG frames from Windows camera server,
saves them with timestamps for the SmartSpectra SDK file_stream input.
"""
import os
import time
import shutil
import requests
import threading
from pathlib import Path

# CONFIG
FRAME_DIR = "/tmp/presage_frames"
WINDOWS_IP = None  # Set dynamically


def get_windows_ip():
    """Get Windows host IP from WSL."""
    import subprocess
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
                return ip
        except Exception:
            continue
    raise RuntimeError("Could not detect Windows host IP")


def setup_frame_dir():
    """Create/clean the frame directory."""
    path = Path(FRAME_DIR)
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)
    print(f"[FrameBridge] Frame directory: {FRAME_DIR}")


def fetch_mjpeg_frames(camera_url, stop_event):
    """Fetch MJPEG frames and save with microsecond timestamps."""
    print(f"[FrameBridge] Connecting to {camera_url}")
    
    try:
        response = requests.get(camera_url, stream=True, timeout=10)
        response.raise_for_status()
    except Exception as e:
        print(f"[FrameBridge] Failed to connect: {e}")
        return

    buffer = b""
    frame_count = 0
    
    print("[FrameBridge] Streaming frames...")
    
    for chunk in response.iter_content(chunk_size=4096):
        if stop_event.is_set():
            break
            
        buffer += chunk
        
        # Find JPEG boundaries
        start = buffer.find(b'\xff\xd8')  # JPEG start
        end = buffer.find(b'\xff\xd9')    # JPEG end
        
        if start != -1 and end != -1 and end > start:
            # Extract JPEG frame
            jpeg_data = buffer[start:end + 2]
            buffer = buffer[end + 2:]
            
            # Save with microsecond timestamp
            timestamp_us = int(time.time() * 1_000_000)
            filename = f"frame{timestamp_us:019d}.jpg"
            filepath = os.path.join(FRAME_DIR, filename)
            
            with open(filepath, 'wb') as f:
                f.write(jpeg_data)
            
            frame_count += 1
            
            # Clean old frames (keep last 30)
            if frame_count % 10 == 0:
                cleanup_old_frames(keep=30)
            
            # Throttle to ~30 fps
            time.sleep(0.033)

    print(f"[FrameBridge] Stopped after {frame_count} frames")


def cleanup_old_frames(keep=30):
    """Remove old frames, keeping the most recent ones."""
    path = Path(FRAME_DIR)
    frames = sorted(path.glob("frame*.jpg"))
    if len(frames) > keep:
        for f in frames[:-keep]:
            try:
                f.unlink()
            except Exception:
                pass


def write_end_marker():
    """Write end-of-stream marker for SDK."""
    marker = os.path.join(FRAME_DIR, "end_of_stream")
    Path(marker).touch()


def run_frame_bridge():
    """Main entry point."""
    global WINDOWS_IP
    
    WINDOWS_IP = get_windows_ip()
    camera_url = f"http://{WINDOWS_IP}:5000"
    
    print(f"[FrameBridge] Windows IP: {WINDOWS_IP}")
    print(f"[FrameBridge] Camera URL: {camera_url}")
    
    setup_frame_dir()
    
    stop_event = threading.Event()
    
    try:
        fetch_mjpeg_frames(camera_url, stop_event)
    except KeyboardInterrupt:
        print("\n[FrameBridge] Interrupted")
        stop_event.set()
    finally:
        write_end_marker()


if __name__ == "__main__":
    run_frame_bridge()
