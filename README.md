# Stopify

<div>

**AI-Powered Impulse Purchase Prevention System**

Built at Hack@Brown 2026

**2nd Place - Marshal Wace Intelligent Systems Prize**

</div>

## Overview

Stopify is an intelligent browser extension and backend system that helps users make better purchasing decisions by detecting and preventing impulse purchases. The system combines real-time biometric analysis with AI-powered contextual reasoning to identify when users are making impulsive decisions and provides timely interventions.

### Key Features

- **Dual-Brain Analysis System**
  - **Fast Brain**: Real-time Bayesian inference using biometric data (heart rate, facial expressions)
  - **Slow Brain**: RAG-based reasoning with Google Vertex AI for contextual analysis

- **Biometric Monitoring** (via Presage SDK)
  - Heart rate variability detection
  - Facial expression analysis
  - Stress level indicators

- **Smart Intervention**
  - Real-time purchase decision analysis
  - Personalized warnings based on user goals and budget
  - Self-refining memory system that learns from user behavior

- **Wide E-Commerce Support**
  - Amazon, eBay, Walmart, Target, Best Buy
  - Etsy, AliExpress, Temu, Wayfair
  - Nike, Adidas, Shein, IKEA, and more
  - Gambling site detection and prevention

## Architecture

```
┌─────────────────┐
│ Browser         │
│ Extension       │
│ (Stopify)       │
└────────┬────────┘
         │
         │ Biometric Data + Product Info
         ▼
┌─────────────────────────────────────────────────┐
│ FastAPI Backend                                 │
│                                                 │
│  ┌──────────────────────────────────────────┐   │
│  │ Fast Brain (Bayesian Inference)          │   │
│  │  └─> Real-time impulse score             │   │
│  └──────────────────────────────────────────┘   │
│                                                 │
│  ┌──────────────────────────────────────────┐   │
│  │ Slow Brain (RAG + Vertex AI)             │   │
│  │  ├─> RAG Retrieval (ChromaDB)            │   │
│  │  ├─> Context Analysis                    │   │
│  │  └─> Gemini AI Reasoning                 │   │
│  └──────────────────────────────────────────┘   │
│                                                 │
│  ┌──────────────────────────────────────────┐   │
│  │ Memory System (Self-Refining)            │   │
│  │  ├─> Goals.md                            │   │
│  │  ├─> Budget.md                           │   │
│  │  ├─> Behavior.md                         │   │
│  │  └─> State.md                            │   │
│  └──────────────────────────────────────────┘   │
└────────┬────────────────────────────────────────┘
         │
         │ {impulse_score, reasoning, intervention}
         ▼
┌─────────────────┐
│ User Interface  │
│ (Popup/Overlay) │
└─────────────────┘
```

## Getting Started

### Prerequisites

- Python 3.10+
- Google Cloud account with Vertex AI API access
- Chrome/Chromium browser
- (Optional) Presage SmartSpectra SDK for real biometric data

### Backend Setup

1. **Clone the repository**
   ```bash
   git clone https://github.com/calebellenberg/hackAtBrown2026.git
   cd hackAtBrown2026/hackAtBrown2026/backend
   ```

2. **Create virtual environment**
   ```bash
   python -m venv venv
   # Windows
   venv\Scripts\activate
   # macOS/Linux
   source venv/bin/activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment variables**
   
   Create a `.env` file in the `backend` directory:
   ```env
   VERTEX_SERVICE_ACCOUNT_PATH=path/to/your/key.json
   GOOGLE_CLOUD_PROJECT=your-project-id
   ```

5. **Set up Google Cloud credentials**
   - Create a service account in Google Cloud Console
   - Enable Vertex AI API
   - Download the JSON key file
   - Place it in the backend directory and update `.env`

6. **Run the backend server**
   ```bash
   uvicorn app:app --host 0.0.0.0 --port 8000 --reload
   ```

   The API will be available at `http://localhost:8000`

### Extension Setup

1. **Navigate to extension directory**
   ```bash
   cd ../extension
   ```

2. **Configure the backend URL**
   
   Update the API endpoint in `background.js` if needed (default: `http://localhost:8000`)

3. **Load extension in Chrome**
   - Open Chrome and go to `chrome://extensions/`
   - Enable "Developer mode" (top right)
   - Click "Load unpacked"
   - Select the `extension` directory

4. **Grant permissions**
   - Allow camera access when prompted (for biometric monitoring)
   - The extension will request access to e-commerce websites

### Presage Vitals Setup (Optional)

For real biometric monitoring using the Presage SmartSpectra SDK:

#### Windows/Linux
```bash
cd backend/persage
./build.sh
python broker.py
```

#### macOS
```bash
cd backend/persage
python mac_broker.py
```

The vitals broker will run on `http://localhost:8766`

See [persage/SETUP.md](hackAtBrown2026/backend/persage/SETUP.md) for detailed setup instructions.

## Usage

1. **Set Your Goals and Budget**
   - Click the extension icon
   - Configure your financial goals and spending limits
   - The system will learn from your preferences

2. **Browse Shopping Sites**
   - Navigate to any supported e-commerce website
   - The extension monitors your browsing behavior
   - Biometric data is collected in real-time

3. **Receive Intelligent Warnings**
   - When an impulse purchase is detected, you'll see a warning
   - The system considers:
     - Your current emotional state (via biometrics)
     - Your stated goals and budget
     - Past purchasing patterns
     - Product price and context

4. **Make Informed Decisions**
   - Review the AI's reasoning
   - Proceed with purchase or reconsider
   - The system learns from your decisions

## Technology Stack

### Backend
- **FastAPI** - High-performance API framework
- **Google Vertex AI** - Gemini AI for contextual reasoning
- **ChromaDB** - Vector database for RAG retrieval
- **NumPy/SciPy** - Bayesian inference calculations
- **OpenCV** - Camera/biometric processing

### Frontend
- **Chrome Extension API** - Browser integration
- **WebSockets** - Real-time data streaming
- **Vanilla JavaScript** - Lightweight and fast

### Biometric Processing
- **Presage SmartSpectra SDK** - Heart rate and vitals detection
- **C++ with OpenCV** - High-performance video processing

## Project Structure

```
hackAtBrown2026/
├── backend/
│   ├── app.py                    # Main FastAPI application
│   ├── memory.py                 # Memory engine with RAG
│   ├── inference_engine.py       # Bayesian inference (Fast Brain)
│   ├── analyze_with_gemini.py    # Vertex AI integration
│   ├── requirements.txt          # Python dependencies
│   ├── memory_store/             # Self-refining markdown memory
│   │   ├── Goals.md
│   │   ├── Budget.md
│   │   ├── Behavior.md
│   │   └── State.md
│   ├── persage/                  # Biometric monitoring system
│   │   ├── broker.py             # Vitals data broker
│   │   ├── headless_vitals.cpp   # C++ vitals processor
│   │   ├── mac_broker.py         # macOS compatibility
│   │   └── build/                # Compiled binaries
│   └── tests/                    # Test suite
│
└── extension/
    ├── manifest.json             # Extension configuration
    ├── background.js             # Service worker
    ├── content.js                # Page interaction
    ├── popup.html/js             # User interface
    ├── tracker.js                # Behavior tracking
    ├── camera.html/js            # Biometric data capture
    ├── icon.png                  # Extension icon
    └── gambling_sites.json       # Gambling site blocklist
```

## API Endpoints

### Main Analysis Endpoint

**POST** `/analyze`

Analyzes a purchase decision combining biometric data and contextual reasoning.

```json
{
  "p_impulse_fast": 0.75,
  "product": "Wireless Headphones",
  "cost": 199.99,
  "website": "amazon.com",
  "user_id": "user123"
}
```

**Response:**
```json
{
  "impulse_score": 0.82,
  "confidence": 0.91,
  "reasoning": "High impulse likelihood detected...",
  "intervention_action": "warn",
  "memory_update": true
}
```

### Other Endpoints

- **POST** `/sync-memory` - Force re-indexing of all memory files
- **POST** `/update-preferences` - Update user goals and budget preferences
- **POST** `/reset-memory` - Reset memory to defaults
- **GET** `/health` - Health check endpoint
- **GET** `/vitals` - Get current biometric data
- **POST** `/pipeline-analyze` - Full pipeline analysis with vitals
- **POST** `/gemini-analyze` - Direct Gemini AI analysis

See [API_DOCUMENTATION.md](hackAtBrown2026/backend/API_DOCUMENTATION.md) for complete API reference.

## Testing

```bash
cd backend

# Run all tests
pytest

# Test API endpoints
python tests/test_api.py

# Test memory system
python tests/test_memory.py

# Test Vertex AI integration
python tests/test_vertex_ai.py

# Run with extension data
python tests/test_with_extension_data.py
```

## Contributing

This project was built for Hack@Brown 2026. Contributions, issues, and feature requests are welcome!

## Team

Built at Hack@Brown 2026

**Winner - 2nd Place in Marshal Wace Intelligent Systems Prize**

## Acknowledgments

- **Marshal Wace** - For recognizing innovative approaches to intelligent systems
- **Presage Technologies** - SmartSpectra SDK for biometric monitoring
- **Google Cloud** - Vertex AI and Gemini API
- **Hack@Brown** - For the amazing hackathon experience

---

<div align="center">

**Made at Hack@Brown 2026**

</div>
