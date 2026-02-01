# Persage Vitals Integration – macOS Setup

## Overview

This setup adapts the Persage vitals detection system for macOS. The original Windows + WSL architecture has been modified to work natively on macOS.

**Important Note**: The SmartSpectra C++ SDK for macOS is not yet publicly available. According to the official documentation, you need to contact `support@presagetech.com` for access to the macOS SDK.

## Architecture

- **Camera Server** (`mac_cam.py`): Captures video from macOS camera using AVFoundation backend
- **Broker** (`mac_broker.py`): Processes frames and provides vitals endpoint for main backend
- **C++ SDK**: Not yet available for macOS - contact Presage for access

## Prerequisites

### System Requirements

- macOS (tested on macOS with ARM64)
- Camera with permissions granted
- Python 3.11+
- Homebrew package manager

### Install Build Tools

```bash
# Install Homebrew (if not already installed)
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Install required tools
brew install cmake ninja git opencv
```

### Python Environment

```bash
cd backend
# Virtual environment is already configured
pip install -r persage/requirements.txt
```

Or manually:
```bash
pip install opencv-python>=4.5.0 flask>=2.0.0 websockets>=11.0 requests>=2.28.0
```

## Camera Permissions

macOS requires explicit camera permissions:

1. **Grant Terminal camera access**:
   - System Settings → Privacy & Security → Camera
   - Enable for Terminal (or your IDE)

2. **Reset permissions if needed**:
   ```bash
   tccutil reset Camera
   ```

## Quick Start (Without C++ SDK)

You can run the system without the C++ SDK - it will use mock vitals data:

### 1. Start Camera Server

```bash
cd backend/persage
python mac_cam.py
```

Expected output:
```
=== macOS Camera Server for Persage ===
Platform: Darwin
OpenCV Version: 4.13.0
Using camera index: 0
✓ Camera ready
Starting MJPEG server on http://localhost:5001
```

### 2. Test Camera

In another terminal:
```bash
curl http://localhost:5000/status
curl http://localhost:5000/info
```

### 3. Start Broker

```bash
cd backend/persage
python mac_broker.py
```

Expected output:
```
=== Persage Broker for macOS ===
Platform: Darwin
Frame directory: /tmp/presage_frames
[HTTP] Vitals endpoint: http://localhost:8766/vitals
[Warning] Running without real vitals - using mock data
[WebSocket] Starting server on ws://localhost:8765
```

### 4. Test Vitals Endpoint

```bash
curl http://localhost:8766/vitals
```

Expected response:
```json
{
  "heart_rate": 75.0,
  "respiration_rate": 16.0,
  "timestamp": 1738454400,
  "status": "healthy",
  "platform": "Darwin"
}
```

### 5. Start Main Backend

```bash
cd backend
uvicorn app:app --host 0.0.0.0 --port 8000
```

## Getting the SmartSpectra C++ SDK for macOS

The C++ SDK is required for real vitals detection. To get access:

1. **Contact Presage Technologies**:
   - Email: `support@presagetech.com`
   - Subject: "macOS SmartSpectra C++ SDK Access Request"
   - Mention your use case and project details

2. **What to expect**:
   - Partner license agreement
   - macOS SDK package (ARM64 support planned)
   - Build instructions
   - API key for Physiology REST API

3. **Once you have the SDK**:
   ```bash
   cd backend/persage
   
   # Build the C++ component
   mkdir -p build
   cd build
   cmake -G "Ninja" -DCMAKE_BUILD_TYPE=Release ..
   ninja
   
   # Or with Make
   cmake -G "Unix Makefiles" -DCMAKE_BUILD_TYPE=Release ..
   make -j$(sysctl -n hw.ncpu)
   ```

## Environment Variables

Create `.env` file in the backend directory:

```bash
# Persage configuration
PERSAGE_VITALS_URL=http://localhost:8766/vitals
SMARTSPECTRA_API_KEY=your_api_key_here

# Main app configuration (existing)
VERTEX_SERVICE_ACCOUNT_PATH=key.json
```

## Troubleshooting

### Camera Issues

```bash
# Check available cameras
python -c "import cv2; print([i for i in range(10) if cv2.VideoCapture(i).isOpened()])"

# Test camera directly
python -c "
import cv2
cap = cv2.VideoCapture(0, cv2.CAP_AVFOUNDATION)
print('Camera opened:', cap.isOpened())
ret, frame = cap.read()
print('Frame captured:', ret, frame.shape if ret else 'None')
cap.release()
"
```

### Permission Issues

```bash
# Reset all camera permissions
tccutil reset Camera

# Check what apps have camera access
sqlite3 ~/Library/TCC/TCC.db "SELECT service, client, auth_value FROM access WHERE service='kTCCServiceCamera';"
```

### Port Conflicts

```bash
# Check what's using the ports
lsof -i :5000  # Camera server
lsof -i :8765  # WebSocket
lsof -i :8766  # Vitals HTTP
```

## Architecture Differences from Windows Setup

| Component | Windows + WSL | macOS Native |
|-----------|---------------|--------------|
| Camera Backend | DirectShow | AVFoundation |
| Frame Storage | `/dev/shm` | `/tmp` |
| IP Detection | WSL → Windows | localhost |
| SDK Status | Available (Linux) | Contact needed |

## API Endpoints

- **Camera Server** (port 5000):
  - `GET /video_feed` - MJPEG stream
  - `GET /status` - Camera health
  - `GET /info` - Camera information

- **Broker** (port 8765/8766):
  - `WS ws://localhost:8765` - Real-time vitals
  - `GET http://localhost:8766/vitals` - HTTP vitals endpoint

- **Main Backend** (port 8000):
  - All existing ImpulseGuard endpoints
  - Integrates with Persage via `PERSAGE_VITALS_URL`

## Development Notes

- Mock vitals are generated when C++ SDK is not available
- Frame processing continues without SDK (useful for testing)
- WebSocket provides real-time updates to frontend
- HTTP endpoint used by main FastAPI backend

## Next Steps

1. **Get SDK Access**: Contact Presage for macOS SDK
2. **Integration**: Test with browser extension
3. **Calibration**: Adjust vitals thresholds for your use case
4. **Production**: Deploy with proper API keys and monitoring