# ImpulseGuard Slow Brain API Documentation

## Overview

The ImpulseGuard Slow Brain API is a RAG-based reasoning engine that analyzes purchase decisions by combining:
- **Fast Brain** (Bayesian Inference): Real-time biometric and behavioral analysis
- **Slow Brain** (RAG + Vertex AI): Context-aware reasoning using user's goals, budget, state, and behavior patterns

The system maintains a self-refining memory in Markdown files that updates after each interaction, learning from user behavior patterns.

## Architecture

```
┌─────────────────┐
│ Browser         │
│ Extension       │
└────────┬────────┘
         │
         │ POST /analyze
         │ {p_impulse_fast, product, cost, website}
         ▼
┌─────────────────────────────────────────────────┐
│ FastAPI Backend (app.py)                        │
│                                                 │
│  ┌──────────────────────────────────────────┐  │
│  │ MemoryEngine (memory.py)                 │  │
│  │                                            │  │
│  │  1. RAG Retrieval (ChromaDB)              │  │
│  │     └─> Query: "product $cost website"    │  │
│  │     └─> Returns: Top 3 context snippets   │  │
│  │                                            │  │
│  │  2. Vertex AI Reasoning (REST API)        │  │
│  │     └─> Input: Fast Brain score + context │  │
│  │     └─> Output: impulse_score, reasoning  │  │
│  │                                            │  │
│  │  3. Memory Update (if needed)             │  │
│  │     └─> Appends to Markdown files         │  │
│  │     └─> Upserts to ChromaDB               │  │
│  └──────────────────────────────────────────┘  │
└────────┬────────────────────────────────────────┘
         │
         │ Response
         │ {impulse_score, confidence, reasoning, 
         │  intervention_action, memory_update}
         ▼
┌─────────────────┐
│ Browser         │
│ Extension       │
└─────────────────┘
```

## Data Flow

### Purchase Analysis Pipeline

1. **Input**: Fast Brain score (`p_impulse_fast`) + Purchase data
2. **RAG Retrieval**: Query ChromaDB with purchase context
3. **Vertex AI Reasoning**: Combine Fast Brain score + RAG context (using OAuth2 service account authentication)
4. **Memory Update**: If insights detected, update Markdown files
5. **Output**: Final impulse score + reasoning + intervention action

### Memory System

The system maintains 4 Markdown files in `backend/memory_store/`:
- **Goals.md**: Long-term financial and personal goals
- **Budget.md**: Monthly spending limits and current status
- **State.md**: Current financial state (accounts, income)
- **Behavior.md**: Observed spending patterns and triggers

These files are:
- Indexed in ChromaDB for semantic search
- Updated incrementally using `collection.upsert()`
- Queried for relevant context on each `/analyze` call

## Base URL

```
http://localhost:8000
```

## Authentication

### Client Authentication

Currently, no authentication is required for API endpoints. The API uses CORS to allow requests from Chrome extensions.

### Vertex AI Service Account Authentication

The backend uses Google Cloud service account authentication to access Vertex AI (Gemini). This provides enterprise-grade security and access control through Google Cloud IAM.

**Setup:**

1. Create a service account in Google Cloud Console:
   - Go to [Google Cloud Console](https://console.cloud.google.com/)
   - Create or select a project
   - Enable Vertex AI API
   - Go to IAM & Admin > Service Accounts
   - Create a service account with "Vertex AI User" role

2. Create and download a JSON key:
   - Click on the service account
   - Go to "Keys" tab
   - Click "Add Key" > "Create new key"
   - Select JSON format
   - Download the JSON file

3. Configure the service account path:
   - Place the JSON file in a secure location
   - Set `VERTEX_SERVICE_ACCOUNT_PATH` in `.env` file (relative to `backend/` or absolute path)

**Environment Variables:**

```bash
VERTEX_SERVICE_ACCOUNT_PATH=path/to/your/service-account-key.json
GOOGLE_CLOUD_PROJECT_ID=your-project-id  # Optional
GOOGLE_CLOUD_LOCATION=us-central1        # Optional, defaults to us-central1
```

The service account automatically handles OAuth2 token generation and refresh. Tokens are refreshed automatically when expired.

## Endpoints

### 1. GET `/`

Root endpoint that returns API information.

**Request:**
```http
GET /
```

**Response:**
```json
{
  "message": "ImpulseGuard Slow Brain API",
  "version": "1.0.0",
  "endpoints": ["/analyze", "/sync-memory"]
}
```

---

### 2. POST `/analyze`

Main endpoint for analyzing purchase decisions. This is the high-frequency endpoint used by the browser extension.

**Request:**

```http
POST /analyze
Content-Type: application/json
```

**Request Body:**
```json
{
  "p_impulse_fast": 0.75,
  "product": "Wireless Headphones",
  "cost": 129.99,
  "website": "amazon.com"
}
```

**Field Descriptions:**
- `p_impulse_fast` (float, required): Fast Brain probability score [0.0 - 1.0]
  - Calculated by the Bayesian inference engine from biometric/behavioral data
- `product` (string, required): Name of the product being considered
- `cost` (float, required): Purchase cost in dollars (must be ≥ 0)
- `website` (string, required): Website domain where purchase is being made

**Response:**

**Success (200 OK):**
```json
{
  "impulse_score": 0.68,
  "confidence": 0.85,
  "reasoning": "Based on your Goals.md, you're saving for a vacation. This $129.99 purchase would reduce your savings progress. However, your Budget.md shows you have $200 remaining this month for discretionary spending, so this is within budget.",
  "intervention_action": "COOLDOWN",
  "memory_update": "User is willing to spend $60 on quality apparel"
}
```

**Field Descriptions:**
- `impulse_score` (float): Final impulse probability [0.0 - 1.0]
  - Combines Fast Brain score with contextual reasoning
- `confidence` (float): Confidence in assessment [0.0 - 1.0]
  - Higher when RAG context is relevant and Vertex AI reasoning is clear
- `reasoning` (string): Plain text explanation
  - Cites specific files (Goals.md, Budget.md, etc.)
  - Explains why the purchase is or isn't an impulse
- `intervention_action` (string): Recommended action
  - `"COOLDOWN"`: Suggest waiting period
  - `"MIRROR"`: Show reflection prompt
  - `"PHRASE"`: Require typing a phrase
  - `"NONE"`: No intervention needed
- `memory_update` (string | null): New observation about user
  - Present if the purchase reveals new behavioral patterns
  - Absent (null) if no new insights

**Fallback Response (when Vertex AI API fails):**
```json
{
  "impulse_score": 0.75,
  "confidence": 0.3,
  "reasoning": "Fast Brain analysis only. Slow Brain unavailable: [error message]",
  "intervention_action": "NONE",
  "memory_update": null
}
```

**Error Responses:**

**422 Unprocessable Entity** - Validation error:
```json
{
  "detail": [
    {
      "loc": ["body", "p_impulse_fast"],
      "msg": "ensure this value is less than or equal to 1.0",
      "type": "value_error.number.not_le"
    }
  ]
}
```

**Example Request (cURL):**
```bash
curl -X POST "http://localhost:8000/analyze" \
  -H "Content-Type: application/json" \
  -d '{
    "p_impulse_fast": 0.75,
    "product": "Wireless Headphones",
    "cost": 129.99,
    "website": "amazon.com"
  }'
```

**Example Request (JavaScript):**
```javascript
const response = await fetch('http://localhost:8000/analyze', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
  },
  body: JSON.stringify({
    p_impulse_fast: 0.75,
    product: 'Wireless Headphones',
    cost: 129.99,
    website: 'amazon.com'
  })
});

const result = await response.json();
console.log(result.impulse_score); // 0.68
console.log(result.reasoning); // "Based on your Goals.md..."
```

---

### 3. POST `/sync-memory`

Force re-indexing of all Markdown memory files. Use this when:
- User manually edits their `.md` files
- First initializing the app
- After bulk updates to memory files

**Request:**

```http
POST /sync-memory
Content-Type: application/json
```

**Request Body:**
```json
{}
```

(Empty body is acceptable)

**Response:**

**Success (200 OK):**
```json
{
  "status": "success",
  "files_indexed": 4
}
```

**Field Descriptions:**
- `status` (string): Operation status ("success" or error)
- `files_indexed` (integer): Number of Markdown files indexed

**Error Response (500 Internal Server Error):**
```json
{
  "detail": "Failed to reindex memory"
}
```

**Example Request:**
```bash
curl -X POST "http://localhost:8000/sync-memory" \
  -H "Content-Type: application/json" \
  -d '{}'
```

---

### 4. GET `/health`

Health check endpoint for monitoring and diagnostics.

**Request:**
```http
GET /health
```

**Response:**
```json
{
  "status": "healthy",
  "memory_indexed": true,
  "chroma_collection_count": 12
}
```

**Field Descriptions:**
- `status` (string): Health status ("healthy")
- `memory_indexed` (boolean): Whether memory has been indexed
- `chroma_collection_count` (integer): Number of chunks in ChromaDB

---

## Data Models

### AnalyzeRequest

```typescript
interface AnalyzeRequest {
  p_impulse_fast: number;  // 0.0 - 1.0
  product: string;
  cost: number;            // >= 0
  website: string;
}
```

### AnalyzeResponse

```typescript
interface AnalyzeResponse {
  impulse_score: number;        // 0.0 - 1.0
  confidence: number;           // 0.0 - 1.0
  reasoning: string;
  intervention_action: "COOLDOWN" | "MIRROR" | "PHRASE" | "NONE";
  memory_update: string | null;
}
```

### SyncMemoryResponse

```typescript
interface SyncMemoryResponse {
  status: "success" | "error";
  files_indexed: number;       // >= 0
}
```

---

## Internal Data Flow

### Step-by-Step: `/analyze` Endpoint

1. **Request Received**
   ```
   POST /analyze
   {
     "p_impulse_fast": 0.75,
     "product": "Headphones",
     "cost": 129.99,
     "website": "amazon.com"
   }
   ```

2. **RAG Retrieval** (`MemoryEngine.retrieve_context()`)
   - Builds query: `"Headphones $129.99 amazon.com"`
   - Queries ChromaDB collection for top 3 relevant snippets
   - Returns context from Goals.md, Budget.md, State.md, or Behavior.md

3. **Vertex AI Reasoning** (`MemoryEngine.reason_with_gemini()`)
   - Constructs prompt with:
     - Fast Brain score (0.75)
     - Purchase details (product, cost, website)
     - Retrieved RAG context
   - Calls Vertex AI (Gemini 2.0 Flash Exp) via REST API with OAuth2 service account authentication
   - Uses exponential backoff (1s, 2s, 4s, 8s, 16s) on failures
   - Returns structured JSON:
     ```json
     {
       "impulse_score": 0.68,
       "confidence": 0.85,
       "reasoning": "...",
       "intervention_action": "COOLDOWN",
       "memory_update": "User is willing to spend $60 on quality apparel"
     }
     ```

4. **Memory Update** (if `memory_update` is present)
   - Determines target file (Goals.md, Budget.md, State.md, or Behavior.md)
   - Appends observation to appropriate section
   - Uses `collection.upsert()` to update ChromaDB incrementally
   - No full reindex needed

5. **Response Sent**
   ```json
   {
     "impulse_score": 0.68,
     "confidence": 0.85,
     "reasoning": "...",
     "intervention_action": "COOLDOWN",
     "memory_update": "User is willing to spend $60 on quality apparel"
   }
   ```

### Memory Update Logic

When `memory_update` is present in Vertex AI's response:

1. **File Selection** (`_determine_target_file()`)
   - Analyzes `memory_update` content for keywords
   - Maps to appropriate file:
     - "goal", "objective", "plan" → `Goals.md`
     - "budget", "spent", "limit" → `Budget.md`
     - "balance", "account", "income" → `State.md`
     - Default → `Behavior.md`

2. **File Update**
   - Creates backup of target file
   - Appends to "Observed Behaviors" or "Recent Changes" section
   - Updates "Last Updated" timestamp
   - Writes file atomically

3. **ChromaDB Upsert**
   - Chunks updated file content
   - Uses `collection.upsert()` to update only changed chunks
   - Maintains chunk ID tracking for efficiency

---

## Error Handling

### API Failures

**Vertex AI API Unavailable:**
- System falls back to Fast Brain score
- Returns `confidence: 0.3` (low confidence)
- `intervention_action: "NONE"`
- No memory update
- Error logged for debugging

**ChromaDB Errors:**
- Logs error and continues with empty context
- Reasoning proceeds without RAG context
- Lower confidence in final assessment

**File Write Failures:**
- Restores from backup
- Returns success response (memory update skipped)
- Logs error for debugging

### HTTP Status Codes

- `200 OK`: Successful request
- `422 Unprocessable Entity`: Validation error (invalid input)
- `500 Internal Server Error`: Server error (reindexing failure, etc.)

---

## Rate Limiting

Currently, no rate limiting is implemented. Consider implementing rate limiting for production use.

## CORS Configuration

The API allows requests from:
- All origins (`*`) - for development
- Chrome extension origins (`chrome-extension://*`)

Update CORS settings in production to restrict to specific origins.

---

## Environment Variables

Required environment variables (set in `backend/.env`):

```bash
# Path to Google Cloud service account JSON file
# Can be relative to backend/ directory or absolute path
VERTEX_SERVICE_ACCOUNT_PATH=path/to/your/service-account-key.json

# Optional: Google Cloud Project ID (for some Vertex AI operations)
# GOOGLE_CLOUD_PROJECT_ID=your-project-id

# Optional: Google Cloud Location (defaults to us-central1)
# GOOGLE_CLOUD_LOCATION=us-central1
```

**Service Account Setup:**

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create or select a project
3. Enable Vertex AI API
4. Go to IAM & Admin > Service Accounts
5. Create a service account with "Vertex AI User" role
6. Create a key (JSON) and download it
7. Place the JSON file in a secure location
8. Set `VERTEX_SERVICE_ACCOUNT_PATH` in `.env` file

---

## Example Integration

### Browser Extension Integration

```javascript
// In your browser extension content script

async function analyzePurchase(fastBrainScore, product, cost, website) {
  try {
    const response = await fetch('http://localhost:8000/analyze', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        p_impulse_fast: fastBrainScore,
        product: product,
        cost: cost,
        website: website
      })
    });

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    const result = await response.json();
    
    // Use the results
    if (result.impulse_score > 0.7) {
      showIntervention(result.intervention_action, result.reasoning);
    }
    
    return result;
  } catch (error) {
    console.error('Analysis failed:', error);
    // Fallback to Fast Brain score only
    return {
      impulse_score: fastBrainScore,
      confidence: 0.3,
      reasoning: 'Analysis unavailable',
      intervention_action: 'NONE',
      memory_update: null
    };
  }
}

// Example usage
const analysis = await analyzePurchase(
  0.75,                    // Fast Brain score
  'Wireless Headphones',   // Product
  129.99,                  // Cost
  'amazon.com'             // Website
);
```

---

## Testing

Run the test suite:

```bash
cd backend
source venv/bin/activate
pytest tests/ -v
```

Test coverage includes:
- API endpoint tests
- Memory engine tests
- RAG retrieval tests
- Vertex AI API mocking (service account authentication)
- Error handling tests

---

## Performance Considerations

- **RAG Retrieval**: ~10-50ms (ChromaDB query)
- **Vertex AI API Call**: ~500-2000ms (network + processing + OAuth2 token refresh if needed)
- **Memory Update**: ~50-100ms (file write + ChromaDB upsert)
- **Total Latency**: ~600-2150ms per `/analyze` request

For production, consider:
- Caching frequent queries
- Async memory updates (don't block response)
- Connection pooling for Vertex AI API

---

## Version History

- **v1.0.0**: Initial release
  - RAG-based reasoning with ChromaDB
  - Vertex AI (Gemini 2.0 Flash Exp) integration with service account authentication
  - Self-refining memory system
  - Incremental ChromaDB updates via upsert
