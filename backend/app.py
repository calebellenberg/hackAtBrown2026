"""
FastAPI application for ImpulseGuard Slow Brain System

Provides endpoints for purchase analysis and memory synchronization.
"""

import os
import json
from typing import Optional, List, Any
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from dotenv import load_dotenv
import httpx
from google.oauth2 import service_account
import google.auth.transport.requests

from memory import MemoryEngine
from inference_engine import ImpulseInferenceEngine

# Load environment variables from .env file
# Look for .env in the backend directory
env_path = os.path.join(os.path.dirname(__file__), '.env')
load_dotenv(dotenv_path=env_path)

# Initialize FastAPI app
app = FastAPI(
    title="ImpulseGuard Slow Brain API",
    description="RAG-based reasoning engine for purchase analysis",
    version="1.0.0"
)

# CORS middleware for browser extension
# Allow chrome-extension:// origins and wildcard for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*", "chrome-extension://*"],  # Allows all origins including chrome-extension://
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize Memory Engine
MEMORY_DIR = os.path.join(os.path.dirname(__file__), "memory_store")
CHROMA_DIR = os.path.join(os.path.dirname(__file__), "memory_store")
VERTEX_SERVICE_ACCOUNT_PATH = os.getenv("VERTEX_SERVICE_ACCOUNT_PATH")

# Make service account path optional - will use fallback if not set
if VERTEX_SERVICE_ACCOUNT_PATH:
    # Resolve relative paths to absolute
    if not os.path.isabs(VERTEX_SERVICE_ACCOUNT_PATH):
        VERTEX_SERVICE_ACCOUNT_PATH = os.path.join(
            os.path.dirname(__file__),
            VERTEX_SERVICE_ACCOUNT_PATH
        )
    print(f"Using service account: {VERTEX_SERVICE_ACCOUNT_PATH}")
else:
    print("WARNING: VERTEX_SERVICE_ACCOUNT_PATH not set. Gemini API will use fallback mode.")

# Initialize Memory Engine only if service account is available
memory_engine = None
if VERTEX_SERVICE_ACCOUNT_PATH and os.path.exists(VERTEX_SERVICE_ACCOUNT_PATH):
    try:
        memory_engine = MemoryEngine(
            memory_dir=MEMORY_DIR,
            chroma_persist_dir=CHROMA_DIR,
            service_account_path=VERTEX_SERVICE_ACCOUNT_PATH
        )
        print("Memory engine initialized successfully")
    except Exception as e:
        print(f"Warning: Could not initialize memory engine: {e}")

# Default baseline for users without calibration (used by Fast Brain)
DEFAULT_BASELINE = {
    "heart_rate": {"mean": 72.0, "std": 10.0},
    "respiration_rate": {"mean": 16.0, "std": 3.0},
    "scroll_velocity": {"mean": 50.0, "std": 20.0},
    "click_rate": {"mean": 2.0, "std": 1.0},
    "time_on_site": {"mean": 180.0, "std": 60.0}
}

# Placeholder biometrics (fallback when persage unavailable)
DEFAULT_BIOMETRICS = {
    "heart_rate": 75.0,
    "respiration_rate": 16.0,
    "emotion_arousal": 0.5
}

PERSAGE_VITALS_URL = os.getenv("PERSAGE_VITALS_URL", "http://localhost:8766/vitals")


async def get_current_biometrics() -> dict:
    """Fetch real-time vitals from persage service for pipeline analysis."""
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            resp = await client.get(PERSAGE_VITALS_URL)
            if resp.status_code == 200:
                data = resp.json()
                return {
                    "heart_rate": float(data.get("heart_rate", 75.0)),
                    "respiration_rate": float(data.get("respiration_rate", 16.0)),
                    "emotion_arousal": DEFAULT_BIOMETRICS["emotion_arousal"],
                }
    except Exception as e:
        print(f"[Vitals] Could not fetch from persage: {e}")
    return DEFAULT_BIOMETRICS.copy()

# Initialize Fast Brain inference engine
fast_brain = ImpulseInferenceEngine(baseline_data=DEFAULT_BASELINE, prior_p=0.2)
print("Fast Brain inference engine initialized successfully")


# Request/Response Models
class AnalyzeRequest(BaseModel):
    """Request model for /analyze endpoint."""
    p_impulse_fast: float = Field(..., ge=0.0, le=1.0, description="Fast Brain probability score")
    product: str = Field(..., description="Product name")
    cost: float = Field(..., ge=0, description="Purchase cost in dollars")
    website: str = Field(..., description="Website where purchase is being made")


class AnalyzeResponse(BaseModel):
    """Response model for /analyze endpoint."""
    impulse_score: float = Field(..., ge=0.0, le=1.0, description="Final impulse score")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence in assessment")
    reasoning: str = Field(..., description="Explanation of the analysis")
    intervention_action: str = Field(..., description="Recommended intervention action")
    memory_update: Optional[str] = Field(None, description="Memory update markdown string if applicable")


class SyncMemoryResponse(BaseModel):
    """Response model for /sync-memory endpoint."""
    status: str = Field(..., description="Status of the operation")
    files_indexed: int = Field(..., ge=0, description="Number of files indexed")


class PipelineRequest(BaseModel):
    """Request model for /pipeline-analyze endpoint - integrates Fast Brain + Slow Brain."""
    # Purchase data
    product: str = Field(..., description="Product name")
    cost: float = Field(..., ge=0, description="Purchase cost in dollars")
    website: str = Field(..., description="Website domain")
    
    # Telemetry from tracker.js
    time_to_cart: Optional[float] = Field(None, description="Time from page load to cart click (seconds)")
    time_on_site: float = Field(..., description="Total time on site (seconds)")
    click_count: int = Field(default=0, description="Total clicks on page")
    peak_scroll_velocity: float = Field(default=0.0, description="Peak scroll velocity (px/s)")
    system_hour: int = Field(..., ge=0, le=23, description="Hour of day (0-23)")


class PipelineResponse(BaseModel):
    """Response model for /pipeline-analyze endpoint."""
    # Fast Brain output
    p_impulse_fast: float = Field(..., ge=0.0, le=1.0, description="Fast Brain probability score")
    fast_brain_intervention: str = Field(..., description="Fast Brain intervention level")
    fast_brain_dominant_trigger: str = Field(..., description="Which input most influenced the Fast Brain score")
    
    # Slow Brain output
    impulse_score: float = Field(..., ge=0.0, le=1.0, description="Final impulse score after Slow Brain reasoning")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence in the assessment")
    reasoning: str = Field(..., description="Explanation citing specific goals/budget")
    intervention_action: str = Field(..., description="COOLDOWN, MIRROR, PHRASE, or NONE")
    memory_update: Optional[str] = Field(None, description="Memory update if patterns detected")


@app.on_event("startup")
async def startup_event():
    """Initialize memory index on startup."""
    if memory_engine:
        try:
            await memory_engine.reindex_memory()
            print("Memory index initialized successfully")
        except Exception as e:
            print(f"Warning: Could not initialize memory index: {e}")
    else:
        print("Memory engine not available - skipping reindex")


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "message": "ImpulseGuard API",
        "version": "2.0.0",
        "endpoints": ["/pipeline-analyze", "/analyze", "/sync-memory", "/gemini-analyze"],
        "fast_brain_available": fast_brain is not None,
        "slow_brain_available": memory_engine is not None
    }


@app.post("/analyze", response_model=AnalyzeResponse)
async def analyze_purchase(request: AnalyzeRequest) -> AnalyzeResponse:
    """
    Analyze a purchase decision using RAG and Vertex AI reasoning.
    
    This is the main high-frequency endpoint that:
    1. Retrieves relevant context from memory via ChromaDB
    2. Performs reasoning using Vertex AI (Gemini) REST API
    3. Updates memory files if needed using upsert
    4. Returns structured analysis
    
    Args:
        request: Analysis request with Fast Brain score and purchase details
        
    Returns:
        Analysis response with impulse score, reasoning, intervention action, and optional memory_update
    """
    if not memory_engine:
        return AnalyzeResponse(
            impulse_score=request.p_impulse_fast,
            confidence=0.3,
            reasoning="Memory engine not available. Using Fast Brain score only.",
            intervention_action="NONE",
            memory_update=None
        )
    
    try:
        # Convert to purchase data dict
        purchase_dict = {
            "product": request.product,
            "cost": request.cost,
            "website": request.website
        }
        
        # Perform analysis
        result = await memory_engine.analyze_purchase(
            p_impulse_fast=request.p_impulse_fast,
            purchase_data=purchase_dict
        )
        
        return AnalyzeResponse(
            impulse_score=result['impulse_score'],
            confidence=result['confidence'],
            reasoning=result['reasoning'],
            intervention_action=result['intervention_action'],
            memory_update=result.get('memory_update')
        )
        
    except Exception as e:
        # Fallback to Fast Brain score if Vertex AI fails
        print(f"Error in analyze_purchase: {e}")
        
        # Return fallback response
        return AnalyzeResponse(
            impulse_score=request.p_impulse_fast,
            confidence=0.3,  # Low confidence for fallback
            reasoning=f"Fast Brain analysis only. Slow Brain unavailable: {str(e)}",
            intervention_action="NONE",
            memory_update=None
        )


@app.post("/sync-memory", response_model=SyncMemoryResponse)
async def sync_memory() -> SyncMemoryResponse:
    """
    Force re-indexing of all Markdown memory files.
    
    This endpoint is used when:
    - User manually edits their .md files
    - First initializing the app
    - After bulk updates
    
    Returns:
        Status and count of indexed files
        
    Raises:
        HTTPException: If reindexing fails
    """
    if not memory_engine:
        return SyncMemoryResponse(
            status="skipped",
            files_indexed=0
        )
    
    try:
        success = await memory_engine.reindex_memory()
        
        if not success:
            raise HTTPException(
                status_code=500,
                detail="Failed to reindex memory"
            )
        
        # Count files in memory directory
        memory_files = [
            f for f in os.listdir(MEMORY_DIR)
            if f.endswith('.md')
        ]
        
        return SyncMemoryResponse(
            status="success",
            files_indexed=len(memory_files)
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error syncing memory: {str(e)}"
        )


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "memory_indexed": memory_engine._indexed if memory_engine else False,
        "chroma_collection_count": memory_engine.collection.count() if memory_engine and memory_engine._indexed else 0,
        "gemini_available": gemini_client is not None,
        "fast_brain_available": fast_brain is not None
    }


# ===================== PIPELINE ANALYZE ENDPOINT =====================

@app.post("/pipeline-analyze", response_model=PipelineResponse)
async def pipeline_analyze(request: PipelineRequest) -> PipelineResponse:
    """
    Full pipeline analysis: Fast Brain (Bayesian) -> Slow Brain (RAG + Vertex AI).
    
    This endpoint is called by the browser extension when a user clicks
    "Add to Cart" or "Buy Now". It:
    1. Runs Fast Brain Bayesian inference with telemetry data
    2. Passes result to Slow Brain for RAG-enhanced reasoning
    3. Returns combined analysis with appropriate intervention
    
    Args:
        request: Pipeline request with purchase data and telemetry
        
    Returns:
        Combined Fast Brain + Slow Brain analysis with intervention action
    """
    try:
        # Step 1: Fetch real vitals from persage (or fallback to defaults)
        biometrics = await get_current_biometrics()
        # Step 2: Prepare Fast Brain input data
        current_data = {
            "heart_rate": biometrics["heart_rate"],
            "respiration_rate": biometrics["respiration_rate"],
            "emotion_arousal": biometrics["emotion_arousal"],
            
            # Real telemetry from browser extension
            "click_rate": request.click_count / max(request.time_on_site, 1),  # clicks per second
            "time_on_site": request.time_on_site,
            "time_to_cart": request.time_to_cart if request.time_to_cart else request.time_on_site,
            "scroll_velocity_peak": request.peak_scroll_velocity,
            "system_hour": request.system_hour,
            "system_time": request.system_hour,  # inference_engine expects this key
            
            # Website context
            "website_name": request.website
        }
        
        # Step 3: Run Fast Brain inference
        p_impulse_fast = fast_brain.calculate_p_impulse(current_data)
        fast_intervention = fast_brain.get_intervention_level(p_impulse_fast)
        
        # Get structured output for dominant trigger
        structured_output = fast_brain.get_structured_output(current_data)
        dominant_trigger = structured_output.get("dominant_trigger", "unknown")
        
        print(f"[Pipeline] Fast Brain: p_impulse={p_impulse_fast:.3f}, intervention={fast_intervention}, trigger={dominant_trigger}")
        
        # Step 4: Run Slow Brain analysis
        if memory_engine:
            try:
                purchase_dict = {
                    "product": request.product,
                    "cost": request.cost,
                    "website": request.website
                }
                
                slow_brain_result = await memory_engine.analyze_purchase(
                    p_impulse_fast=p_impulse_fast,
                    purchase_data=purchase_dict
                )
                
                print(f"[Pipeline] Slow Brain: score={slow_brain_result['impulse_score']:.3f}, action={slow_brain_result['intervention_action']}")
                
                return PipelineResponse(
                    # Fast Brain output
                    p_impulse_fast=p_impulse_fast,
                    fast_brain_intervention=fast_intervention,
                    fast_brain_dominant_trigger=dominant_trigger,
                    
                    # Slow Brain output
                    impulse_score=slow_brain_result['impulse_score'],
                    confidence=slow_brain_result['confidence'],
                    reasoning=slow_brain_result['reasoning'],
                    intervention_action=slow_brain_result['intervention_action'],
                    memory_update=slow_brain_result.get('memory_update')
                )
                
            except Exception as slow_brain_error:
                print(f"[Pipeline] Slow Brain error: {slow_brain_error}")
                # Fall through to Fast Brain only response
        
        # Fallback: Fast Brain only (Slow Brain unavailable)
        # Map Fast Brain intervention to Slow Brain format
        intervention_mapping = {
            "NONE": "NONE",
            "NUDGE": "MIRROR",
            "CHALLENGE": "COOLDOWN",
            "LOCKOUT": "PHRASE"
        }
        
        return PipelineResponse(
            p_impulse_fast=p_impulse_fast,
            fast_brain_intervention=fast_intervention,
            fast_brain_dominant_trigger=dominant_trigger,
            impulse_score=p_impulse_fast,  # Use Fast Brain score directly
            confidence=0.5,  # Medium confidence without Slow Brain
            reasoning=f"Fast Brain analysis only. Score based on {dominant_trigger}. Slow Brain unavailable.",
            intervention_action=intervention_mapping.get(fast_intervention, "MIRROR"),
            memory_update=None
        )
        
    except Exception as e:
        print(f"[Pipeline] Error: {e}")
        # Complete fallback
        return PipelineResponse(
            p_impulse_fast=0.5,
            fast_brain_intervention="NUDGE",
            fast_brain_dominant_trigger="error",
            impulse_score=0.5,
            confidence=0.3,
            reasoning=f"Analysis error: {str(e)}. Using default intervention.",
            intervention_action="MIRROR",
            memory_update=None
        )


# ===================== GEMINI ANALYSIS ENDPOINT =====================

class PurchaseAttempt(BaseModel):
    """Single purchase attempt data from extension."""
    id: Optional[str] = None
    timestamp: Optional[str] = None
    actionType: str = Field(..., description="'add_to_cart' or 'buy_now'")
    domain: Optional[str] = None
    pageUrl: Optional[str] = None
    productName: Optional[str] = None
    priceRaw: Optional[str] = None
    priceValue: Optional[float] = None
    timeToCart: Optional[float] = None
    timeOnSite: Optional[float] = None
    clickCount: Optional[int] = None
    cartClickCount: Optional[int] = None
    peakScrollVelocity: Optional[float] = None


class GeminiAnalyzeRequest(BaseModel):
    """Request model for /gemini-analyze endpoint."""
    current_purchase: PurchaseAttempt = Field(..., description="Current purchase being attempted")
    purchase_history: Optional[List[PurchaseAttempt]] = Field(default=[], description="Recent purchase history")
    preferences: Optional[dict] = Field(default={}, description="User preferences (budget, threshold, sensitivity)")


class GeminiAnalyzeResponse(BaseModel):
    """Response model for /gemini-analyze endpoint."""
    risk_level: str = Field(..., description="LOW, MEDIUM, HIGH, or CRITICAL")
    risk_score: int = Field(..., ge=0, le=100, description="Risk score 0-100")
    should_intervene: bool = Field(..., description="Whether to show intervention")
    intervention_type: str = Field(..., description="NONE, GENTLE_REMINDER, COOL_DOWN, or STRICT_BLOCK")
    reasoning: str = Field(..., description="Why this is or isn't impulsive")
    recommendations: List[str] = Field(..., description="Actionable recommendations")
    personalized_message: str = Field(..., description="Message to show the user")


class GeminiClient:
    """Client for calling Gemini API."""
    
    VERTEX_AI_BASE = "https://generativelanguage.googleapis.com/v1beta"
    MODEL = "gemini-1.5-flash"
    
    def __init__(self, service_account_path: str):
        self.service_account_path = service_account_path
        self.credentials = None
        self.access_token = None
        self._setup_credentials()
    
    def _setup_credentials(self):
        """Load service account credentials."""
        if not os.path.exists(self.service_account_path):
            raise FileNotFoundError(f"Service account not found: {self.service_account_path}")
        
        self.credentials = service_account.Credentials.from_service_account_file(
            self.service_account_path,
            scopes=['https://www.googleapis.com/auth/generative-language']
        )
        self._refresh_token()
    
    def _refresh_token(self):
        """Refresh the access token."""
        request = google.auth.transport.requests.Request()
        if not self.credentials.valid:
            self.credentials.refresh(request)
        self.access_token = self.credentials.token
    
    async def analyze(self, prompt: str) -> dict:
        """Send prompt to Gemini and get response."""
        self._refresh_token()
        
        url = f"{self.VERTEX_AI_BASE}/models/{self.MODEL}:generateContent"
        
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "temperature": 0.7
            }
        }
        
        headers = {
            'Authorization': f'Bearer {self.access_token}',
            'Content-Type': 'application/json'
        }
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            result = response.json()
        
        if 'candidates' in result and len(result['candidates']) > 0:
            text = result['candidates'][0]['content']['parts'][0].get('text', '')
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return {"error": "Failed to parse Gemini response", "raw": text}
        
        return {"error": "No response from Gemini"}


# Initialize Gemini client
gemini_client = None
try:
    gemini_client = GeminiClient(VERTEX_SERVICE_ACCOUNT_PATH)
    print("Gemini client initialized successfully")
except Exception as e:
    print(f"Warning: Could not initialize Gemini client: {e}")


def build_gemini_prompt(request: GeminiAnalyzeRequest) -> str:
    """Build the prompt for Gemini analysis."""
    current = request.current_purchase
    history = request.purchase_history or []
    prefs = request.preferences or {}
    
    # Calculate history stats
    total_spent = sum(p.priceValue or 0 for p in history)
    avg_time_to_cart = sum(p.timeToCart or 0 for p in history if p.timeToCart) / max(len([p for p in history if p.timeToCart]), 1)
    
    prompt = f"""You are a behavioral finance AI that detects impulse purchases in real-time.

A user just clicked "{current.actionType.upper().replace('_', ' ')}" on a shopping website. Analyze if this is an impulse purchase.

## Current Purchase Attempt
- Product: {current.productName or 'Unknown'}
- Price: {current.priceRaw or f'${current.priceValue}' if current.priceValue else 'Unknown'}
- Website: {current.domain or 'Unknown'}
- Time to Cart: {current.timeToCart:.1f}s (how fast they clicked)
- Time on Site: {current.timeOnSite:.1f}s
- Click Count: {current.clickCount or 0}
- Scroll Velocity: {current.peakScrollVelocity or 0:.1f}

## User Preferences  
- Monthly Budget: ${prefs.get('budget', 'Not set')}
- Impulse Threshold: ${prefs.get('threshold', 'Not set')}
- Sensitivity: {prefs.get('sensitivity', 'medium')}

## Recent History (last {len(history)} attempts)
- Total attempted spending: ${total_spent:.2f}
- Average time-to-cart: {avg_time_to_cart:.1f}s
- Recent products: {', '.join([p.productName or 'Unknown' for p in history[-5:]])}

## Impulse Buying Indicators
Consider these red flags:
1. Very short time-to-cart (<30 seconds) = impulsive
2. High scroll velocity = rushed browsing
3. Price exceeds threshold or strains budget
4. Multiple purchases in short time
5. Late night shopping (emotional buying)
6. High-ticket items with no research time

## Analysis Request
Determine if this purchase is impulsive and what intervention (if any) to show.

Respond in this exact JSON format:
{{
    "risk_level": "LOW|MEDIUM|HIGH|CRITICAL",
    "risk_score": 0-100,
    "should_intervene": true/false,
    "intervention_type": "NONE|GENTLE_REMINDER|COOL_DOWN|STRICT_BLOCK",
    "reasoning": "Brief explanation of why this is/isn't impulsive",
    "recommendations": ["tip 1", "tip 2", "tip 3"],
    "personalized_message": "A short, friendly message to show the user"
}}

IMPORTANT: 
- risk_score < 30 = LOW, no intervention needed
- risk_score 30-60 = MEDIUM, gentle reminder
- risk_score 60-80 = HIGH, suggest cooling off
- risk_score > 80 = CRITICAL, strongly discourage
"""
    return prompt


@app.post("/gemini-analyze", response_model=GeminiAnalyzeResponse)
async def gemini_analyze_purchase(request: GeminiAnalyzeRequest) -> GeminiAnalyzeResponse:
    """
    Analyze a purchase attempt using Gemini AI.
    
    This endpoint receives real-time data from the extension when a user
    clicks Add to Cart or Buy Now, and returns an AI-powered analysis.
    """
    if not gemini_client:
        # Fallback response if Gemini not available
        return GeminiAnalyzeResponse(
            risk_level="MEDIUM",
            risk_score=50,
            should_intervene=True,
            intervention_type="GENTLE_REMINDER",
            reasoning="AI analysis unavailable. Defaulting to gentle reminder.",
            recommendations=["Take a moment to consider if you really need this item."],
            personalized_message="Gemini AI is not configured. Please check your service account."
        )
    
    try:
        prompt = build_gemini_prompt(request)
        result = await gemini_client.analyze(prompt)
        
        if "error" in result:
            raise ValueError(result.get("error", "Unknown Gemini error"))
        
        return GeminiAnalyzeResponse(
            risk_level=result.get("risk_level", "MEDIUM"),
            risk_score=result.get("risk_score", 50),
            should_intervene=result.get("should_intervene", True),
            intervention_type=result.get("intervention_type", "GENTLE_REMINDER"),
            reasoning=result.get("reasoning", "Unable to determine reasoning."),
            recommendations=result.get("recommendations", []),
            personalized_message=result.get("personalized_message", "")
        )
        
    except Exception as e:
        print(f"Error in gemini_analyze_purchase: {e}")
        
        # Fallback based on quick heuristics
        current = request.current_purchase
        risk_score = 50
        
        # Quick heuristic scoring
        if current.timeToCart and current.timeToCart < 30:
            risk_score += 20
        if current.priceValue and current.priceValue > 100:
            risk_score += 15
        if current.peakScrollVelocity and current.peakScrollVelocity > 1000:
            risk_score += 10
        
        risk_score = min(100, risk_score)
        
        return GeminiAnalyzeResponse(
            risk_level="HIGH" if risk_score > 60 else "MEDIUM",
            risk_score=risk_score,
            should_intervene=risk_score > 40,
            intervention_type="COOL_DOWN" if risk_score > 60 else "GENTLE_REMINDER",
            reasoning=f"AI unavailable. Using heuristics: fast checkout detected. Error: {str(e)}",
            recommendations=["Take a deep breath", "Consider waiting 24 hours"],
            personalized_message="Let's pause and think about this purchase."
        )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
