# Persage Vitals Integration – Setup

## Packages

### Windows (camera server)

```bash
cd backend/persage
pip install -r requirements.txt
```

Installs: `opencv-python`, `flask`, `websockets`, `requests`.

### WSL (broker + C++ SDK)

**Python (broker):**
```bash
cd backend/persage
pip install -r requirements.txt
```

**C++ (headless_vitals):** Requires SmartSpectra SDK and OpenCV in WSL (e.g. Presage PPA + `libopencv-dev`).

```bash
cd backend/persage
./build.sh
```
Or manually:
```bash
cd backend/persage
mkdir -p build && cd build
cmake ..
make -j$(nproc)
```
Output: `./build/headless_vitals`. Set `SMARTSPECTRA_API_KEY` and `FRAME_DIR` when running (broker.py does this).

### Main backend

```bash
cd backend
pip install -r requirements.txt
```

Already includes `httpx` for fetching vitals.

## Run order

1. **Windows:** `python backend/persage/windows_cam.py` → MJPEG on port 5000  
2. **WSL:** `python backend/persage/broker.py` → WebSocket 8765, HTTP vitals 8766  
3. **Backend:** `uvicorn app:app --host 0.0.0.0 --port 8000` (from `backend/`)  
4. Load extension; ensure `host_permissions` includes `http://localhost:5000/*`

## When backend runs on Windows and broker on WSL

Set the vitals URL so the backend can reach the broker:

```bash
set PERSAGE_VITALS_URL=http://<WSL_IP>:8766/vitals
uvicorn app:app --host 0.0.0.0 --port 8000
```

Get WSL IP from Windows: `wsl hostname -I` (use first address).

## Extension

No extra packages. Reload the extension after changing `manifest.json` or `host_permissions`.
