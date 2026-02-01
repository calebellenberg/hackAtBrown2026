"""
FastAPI application for ImpulseGuard Slow Brain System

Provides endpoints for purchase analysis and memory synchronization.
"""

import os
from typing import Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from dotenv import load_dotenv

from memory import MemoryEngine

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

if not VERTEX_SERVICE_ACCOUNT_PATH:
    raise ValueError("VERTEX_SERVICE_ACCOUNT_PATH environment variable is required")

# Resolve relative paths to absolute
if not os.path.isabs(VERTEX_SERVICE_ACCOUNT_PATH):
    VERTEX_SERVICE_ACCOUNT_PATH = os.path.join(
        os.path.dirname(__file__),
        VERTEX_SERVICE_ACCOUNT_PATH
    )

memory_engine = MemoryEngine(
    memory_dir=MEMORY_DIR,
    chroma_persist_dir=CHROMA_DIR,
    service_account_path=VERTEX_SERVICE_ACCOUNT_PATH
)


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


@app.on_event("startup")
async def startup_event():
    """Initialize memory index on startup."""
    try:
        await memory_engine.reindex_memory()
        print("Memory index initialized successfully")
    except Exception as e:
        print(f"Warning: Could not initialize memory index: {e}")


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "message": "ImpulseGuard Slow Brain API",
        "version": "1.0.0",
        "endpoints": ["/analyze", "/sync-memory"]
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
        "memory_indexed": memory_engine._indexed,
        "chroma_collection_count": memory_engine.collection.count() if memory_engine._indexed else 0
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
