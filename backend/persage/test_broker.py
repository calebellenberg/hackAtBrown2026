#!/usr/bin/env python3
"""Quick test of broker components (run in WSL)."""
import asyncio

from broker import get_windows_ip, verify_camera_stream


def main():
    print("Testing IP detection...")
    try:
        ip = get_windows_ip()
        print(f"  OK: {ip}")
    except Exception as e:
        print(f"  FAIL: {e}")
        return 1

    print("Testing camera stream verification...")
    camera_url = f"http://{ip}:5000"
    ok = asyncio.run(verify_camera_stream(camera_url))
    if ok:
        print(f"  OK: {camera_url} is reachable")
    else:
        print(f"  SKIP: {camera_url} not reachable (start windows_cam.py first)")
    return 0


if __name__ == "__main__":
    exit(main())
