# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

ImpulseGuard is a dual-brain AI system to combat impulse purchasing. It combines real-time biometric monitoring with AI-powered reasoning through a Chrome extension and Python FastAPI backend.

**Architecture**: Fast Brain (Bayesian inference for real-time impulse detection) → Slow Brain (RAG + Vertex AI Gemini for deliberate reasoning) → Intervention (NONE/WARN/BLOCK/STOP thresholds)

## Build & Run Commands

### Backend
```bash
cd backend
pip install -r requirements.txt
uvicorn app:app --host 0.0.0.0 --port 8000
```

### Tests
```bash
cd backend
pytest tests/                      # All tests
pytest tests/test_memory.py -v     # Specific module
python tests/run_pipeline_demo.py  # Full pipeline validation
```

### Chrome Extension
Load unpacked from `/extension/` directory via `chrome://extensions/` with Developer mode enabled.

### Biometric Module (optional)
```bash
cd backend/persage
python mac_broker.py   # macOS - starts on port 8766
python windows_cam.py  # Windows - MJPEG server on port 5000
```

## Architecture

```
extension/          Chrome extension (MV3)
├── tracker.js      Behavioral telemetry (scroll velocity, click rate, time-to-cart)
├── content.js      Price extraction, DOM injection
├── popup.js        Settings UI, memory management
└── background.js   Service worker

backend/            FastAPI server
├── app.py          Main API endpoints
├── inference_engine.py  Fast Brain - Bayesian scoring
├── memory.py       Slow Brain - RAG + Vertex AI integration
└── memory_store/   Persistent state (Markdown + ChromaDB)
    ├── Goals.md    User financial goals
    ├── Budget.md   Spending limits/tracking
    ├── State.md    Financial state
    └── Behavior.md Observed patterns

backend/persage/    Biometric data collection (Presage SDK)
```

## Key APIs

| Endpoint | Purpose |
|----------|---------|
| POST `/analyze` | Main dual-brain analysis (Fast Brain score + product → Slow Brain reasoning) |
| POST `/pipeline-analyze` | Full pipeline with complete telemetry |
| POST `/update-preferences` | Update budget, sensitivity, goals |
| POST `/sync-memory` | Sync memory files to ChromaDB |
| POST `/reset-memory` | Clear all memory |
| POST `/consolidate-memory` | Consolidate large memory files (>2KB or >10 observations) |

## Environment Variables

Required in `backend/.env`:
```
VERTEX_SERVICE_ACCOUNT_PATH=key.json
```

Optional:
```
PERSAGE_VITALS_URL=http://localhost:8766/vitals
```

## Intervention Thresholds

- 0.0-0.3: NONE (allow purchase)
- 0.3-0.6: MIRROR (gentle reflection)
- 0.6-0.85: COOLDOWN (wait period)
- 0.85-1.0: PHRASE (strong intervention)

## Key Implementation Details

- **Fast Brain** (`inference_engine.py`): Uses z-score normalization against baselines (heart_rate mean=67, scroll_velocity mean=600, etc.) with sigmoid transformation
- **Slow Brain** (`memory.py`): RAG retrieval from ChromaDB (top 3 matches) + Vertex AI Gemini 1.5 with custom system instruction prioritizing goal alignment
- **Memory files** are human-readable Markdown that auto-update based on detected patterns
- **Extension targets** 40+ retail/gambling domains defined in `gambling_sites.json` and `manifest.json`
- **Biometrics currently use placeholders** (`USE_PLACEHOLDER_BIOMETRICS=True`) - Presage SDK integration incomplete
