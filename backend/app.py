"""
FastAPI application for ImpulseGuard Slow Brain System

Provides endpoints for purchase analysis and memory synchronization.
"""

import os
import json
import shutil
from typing import Optional, List, Any, Dict
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
    version="2.1.0"
)

# CORS middleware for browser extension
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
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
# Larger std = less trigger-happy: need bigger deviation from mean to drive high likelihood
DEFAULT_BASELINE = {
    # BIOMETRICS_DISABLED: HR and RR baselines kept for backward compatibility but not used
    # # Biometrics (user baseline) — wider std so normal variation doesn't flag as impulsive
    # "heart_rate": {"mean": 67.0, "std": 22.0},
    # "respiration_rate": {"mean": 10.0, "std": 6.5},

    # Behavioral telemetry — wide stds so z-scores stay in ~0–2.5 range
    "scroll_velocity": {"mean": 600.0, "std": 5500.0},
    "click_rate": {"mean": 0.15, "std": 1.0},

    # time_on_site: seconds (used for compatibility; TTC used for impulse)
    "time_on_site": {"mean": 180.0, "std": 110.0},

    # time_to_cart: baseline 2.5s; only very fast TTC is strongly impulsive
    "time_to_cart": {"mean": 2.5, "std": 32.0}
}

# BIOMETRICS_DISABLED: Presage vitals no longer fetched
# # Placeholder biometrics (fallback when persage unavailable)
# DEFAULT_BIOMETRICS = {
#     "heart_rate": 67.0,        # Match baseline mean for neutral Z-score
#     "respiration_rate": 10.0,  # Match baseline mean for neutral Z-score
#     "emotion_arousal": 0.5     # Neutral arousal level
# }

# PERSAGE_VITALS_URL = os.getenv("PERSAGE_VITALS_URL", "http://localhost:8766/vitals")


# async def get_current_biometrics() -> dict:
#     """Fetch real-time vitals from persage service for pipeline analysis."""
#     try:
#         async with httpx.AsyncClient(timeout=2.0) as client:
#             resp = await client.get(PERSAGE_VITALS_URL)
#             if resp.status_code == 200:
#                 data = resp.json()
#                 return {
#                     "heart_rate": float(data.get("heart_rate", 75.0)),
#                     "respiration_rate": float(data.get("respiration_rate", 16.0)),
#                     "emotion_arousal": DEFAULT_BIOMETRICS["emotion_arousal"],
#                 }
#     except Exception as e:
#         print(f"[Vitals] Could not fetch from persage: {e}")
#     return DEFAULT_BIOMETRICS.copy()

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


class UpdatePreferencesRequest(BaseModel):
    """Request model for /update-preferences endpoint."""
    budget: float = Field(..., ge=0, description="Monthly spending budget in dollars")
    threshold: float = Field(default=0, ge=0, description="Large purchase threshold in dollars")
    sensitivity: str = Field(default="medium", description="Spending sensitivity: low, medium, or high")
    financial_goals: Optional[str] = Field(default=None, description="User's financial goals and purchase preferences")


class UpdatePreferencesResponse(BaseModel):
    """Response model for /update-preferences endpoint."""
    status: str = Field(..., description="Status of the operation")
    budget_updated: bool = Field(..., description="Whether Budget.md was updated")
    goals_updated: bool = Field(default=False, description="Whether memory files were updated with financial goals")
    message: str = Field(..., description="Details about the update")


class ResetMemoryResponse(BaseModel):
    """Response model for /reset-memory endpoint."""
    status: str = Field(..., description="Status of the operation")
    files_reset: int = Field(..., ge=0, description="Number of files reset")
    message: str = Field(..., description="Details about the reset")


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
        "version": "2.1.0",
        "endpoints": ["/pipeline-analyze", "/analyze", "/sync-memory", "/consolidate-memory", "/gemini-analyze"],
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


# ===================== UPDATE PREFERENCES ENDPOINT =====================

async def process_financial_goals_with_gemini(financial_goals_text: str, memory_engine: MemoryEngine) -> Dict[str, Any]:
    """
    Process financial goals text using Gemini API to format it appropriately for memory files.
    
    Args:
        financial_goals_text: User's financial goals and purchase preferences text
        memory_engine: MemoryEngine instance for calling Gemini API
        
    Returns:
        Dictionary with file updates: {"Goals.md": "...", "Budget.md": "...", etc.}
    """
    system_prompt = """You are a financial assistant that helps format user financial goals and purchase preferences 
for an AI decision-making system. Your task is to analyze the user's input and format it appropriately for memory files 
that will be used by an AI to make better purchase decisions.

The system has 4 memory files:
1. **Goals.md**: Long-term financial goals, savings targets, personal aspirations, future plans
2. **Budget.md**: Monthly spending limits, budget constraints, category-specific budgets, spending thresholds
3. **Behavior.md**: Purchase preferences, spending patterns, triggers to avoid, behavioral preferences
4. **State.md**: Current financial state information (account balances, income, current savings)

Your job is to:
- Parse the user's financial goals text
- Extract relevant information for each memory file type
- Format updates as markdown that preserves context for future AI decisions
- Make content easily retrievable via RAG queries by being specific and clear
- Preserve information in a way that helps the AI later make better decisions by referencing specific goals, budgets, and preferences

IMPORTANT FORMATTING GUIDELINES:
- Use clear, specific language that the AI can reference later
- Include specific dollar amounts, timeframes, and categories when mentioned
- Format as markdown sections that fit into existing file structures
- For Goals.md: Use bullet points or checkboxes for goals
- For Budget.md: Include specific limits and thresholds
- For Behavior.md: Describe preferences and patterns clearly
- For State.md: Only include if current financial state is mentioned

Return a JSON object with keys for each file that needs updating. Only include files that have relevant content.
Example format:
{
  "Goals.md": "## Financial Goals\\n- Save $5000 for vacation by June 2026\\n- Build emergency fund of $10000",
  "Budget.md": "## Category Budgets\\n- Electronics: $200/month",
  "Behavior.md": "## Purchase Preferences\\n- Prefer quality over quantity for clothing\\n- Avoid impulse electronics purchases"
}

If a file doesn't need updating, omit it from the response. Return only valid JSON."""

    user_prompt = f"""Analyze the following user financial goals and purchase preferences, then format them appropriately 
for the memory files:

{financial_goals_text}

Format this information for the appropriate memory files. Be specific and clear so the AI can reference this information 
when making purchase decisions later."""

    try:
        result = await memory_engine._call_gemini_api(user_prompt, system_instruction=system_prompt)
        return result
    except Exception as e:
        print(f"[Preferences] Error calling Gemini API for financial goals: {e}")
        raise


async def update_memory_file_with_content(file_name: str, new_content: str, memory_dir: str) -> bool:
    """
    Update a memory file by merging new content with existing content.
    
    Args:
        file_name: Name of the memory file (e.g., "Goals.md")
        new_content: New content to add (formatted markdown)
        memory_dir: Directory containing memory files
        
    Returns:
        True if successful, False otherwise
    """
    from datetime import datetime
    
    try:
        file_path = os.path.join(memory_dir, file_name)
        
        if not os.path.exists(file_path):
            print(f"[Preferences] Warning: {file_name} not found, skipping update")
            return False
        
        # Read existing content
        with open(file_path, 'r', encoding='utf-8') as f:
            existing_content = f.read()
        
        # Find where to insert new content
        # Try to find appropriate sections, otherwise append
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # For Goals.md, look for "Financial Goals" section
        if file_name == "Goals.md":
            if "## Financial Goals" in existing_content:
                # Insert after Financial Goals section
                section_marker = "## Financial Goals"
                if new_content.strip():
                    # Add new content after the section header
                    lines = existing_content.split('\n')
                    insert_index = None
                    for i, line in enumerate(lines):
                        if line.strip() == section_marker:
                            insert_index = i + 1
                            break
                    
                    if insert_index:
                        # Find the next section or end of file
                        next_section = None
                        for i in range(insert_index, len(lines)):
                            if lines[i].startswith('##') and lines[i] != section_marker:
                                next_section = i
                                break
                        
                        if next_section:
                            lines.insert(next_section, f"\n{new_content}\n")
                        else:
                            lines.append(f"\n{new_content}\n")
                        existing_content = '\n'.join(lines)
                    else:
                        existing_content += f"\n\n{new_content}\n"
            else:
                # Add Financial Goals section
                existing_content += f"\n\n## Financial Goals\n{new_content}\n"
        
        # For Budget.md, look for appropriate section
        elif file_name == "Budget.md":
            if "## Category Budgets" in existing_content or "## Spending Limits" in existing_content:
                # Append to existing section
                existing_content += f"\n{new_content}\n"
            else:
                # Add new section before "Last Updated"
                if "## Last Updated" in existing_content:
                    existing_content = existing_content.replace(
                        "## Last Updated",
                        f"{new_content}\n\n## Last Updated"
                    )
                else:
                    existing_content += f"\n\n{new_content}\n"
        
        # For Behavior.md, look for "Purchase Preferences" or "Observed Behaviors"
        elif file_name == "Behavior.md":
            if "## Purchase Preferences" in existing_content:
                existing_content += f"\n{new_content}\n"
            elif "## Observed Behaviors" in existing_content:
                # Add Purchase Preferences section after Observed Behaviors
                existing_content = existing_content.replace(
                    "## Observed Behaviors",
                    f"## Observed Behaviors\n\n## Purchase Preferences\n{new_content}"
                )
            else:
                existing_content += f"\n\n## Purchase Preferences\n{new_content}\n"
        
        # For State.md, update relevant sections
        elif file_name == "State.md":
            if "## Wealth Status" in existing_content:
                existing_content += f"\n{new_content}\n"
            else:
                existing_content += f"\n\n{new_content}\n"
        
        # Update Last Updated timestamp
        import re
        if "## Last Updated" in existing_content:
            existing_content = re.sub(
                r'## Last Updated\n- .*',
                f"## Last Updated\n- {timestamp}",
                existing_content
            )
        else:
            existing_content += f"\n\n## Last Updated\n- {timestamp}\n"
        
        # Write updated content
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(existing_content)
        
        print(f"[Preferences] Updated {file_name} with financial goals content")
        return True
        
    except Exception as e:
        print(f"[Preferences] Error updating {file_name}: {e}")
        return False


@app.post("/update-preferences", response_model=UpdatePreferencesResponse)
async def update_preferences(request: UpdatePreferencesRequest) -> UpdatePreferencesResponse:
    """
    Update user preferences in memory files.
    
    This endpoint is called by the browser extension when the user saves
    their preferences. It updates Budget.md with the new budget limits.
    
    Args:
        request: Preferences data (budget, threshold, sensitivity)
        
    Returns:
        Status of the update operation
    """
    from datetime import datetime
    
    try:
        budget_file = os.path.join(MEMORY_DIR, "Budget.md")
        
        if not os.path.exists(budget_file):
            return UpdatePreferencesResponse(
                status="error",
                budget_updated=False,
                message="Budget.md not found"
            )
        
        # Generate updated Budget.md content
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # Calculate remaining based on budget
        remaining = request.budget
        
        # Sensitivity affects the intervention thresholds
        sensitivity_note = {
            'low': 'Gentle reminders only',
            'medium': 'Balanced intervention',
            'high': 'Strict warnings enabled'
        }.get(request.sensitivity, 'Balanced intervention')
        
        new_content = f"""# Budget Constraints

## Monthly Spending Limits
- Discretionary: ${request.budget:.0f}/month
- Large Purchase Threshold: ${request.threshold:.0f}

## Current Month
- Spent: $0
- Remaining: ${remaining:.0f}

## User Settings
- Sensitivity: {request.sensitivity} ({sensitivity_note})

## Last Updated
- {timestamp}
"""
        
        # Write the updated content
        with open(budget_file, 'w', encoding='utf-8') as f:
            f.write(new_content)
        
        print(f"[Preferences] Updated Budget.md: budget=${request.budget}, threshold=${request.threshold}, sensitivity={request.sensitivity}")
        
        # Process financial goals if provided
        goals_updated = False
        if request.financial_goals and request.financial_goals.strip() and memory_engine:
            try:
                print(f"[Preferences] Processing financial goals with Gemini...")
                # Call Gemini to format the financial goals
                file_updates = await process_financial_goals_with_gemini(
                    request.financial_goals.strip(),
                    memory_engine
                )
                
                # Update each memory file that Gemini identified
                files_updated = []
                for file_name, content in file_updates.items():
                    if file_name.endswith('.md') and content and content.strip():
                        if await update_memory_file_with_content(file_name, content.strip(), MEMORY_DIR):
                            files_updated.append(file_name)
                            goals_updated = True
                
                if files_updated:
                    print(f"[Preferences] Updated memory files: {', '.join(files_updated)}")
                else:
                    print(f"[Preferences] No memory files were updated (Gemini may not have found relevant content)")
                    
            except Exception as e:
                print(f"[Preferences] Error processing financial goals: {e}")
                # Don't fail the entire request if financial goals processing fails
                # Budget update still succeeded
        
        # Reindex ChromaDB to pick up changes (both budget and goals)
        if memory_engine:
            await memory_engine.reindex_memory()
            print("[Preferences] Reindexed memory after preferences update")
        
        message = f"Budget set to ${request.budget}/month with ${request.threshold} large purchase threshold"
        if goals_updated:
            message += ". Financial goals updated in memory files."
        
        return UpdatePreferencesResponse(
            status="success",
            budget_updated=True,
            goals_updated=goals_updated,
            message=message
        )
        
    except Exception as e:
        print(f"[Preferences] Error updating preferences: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error updating preferences: {str(e)}"
        )


# ===================== RESET MEMORY ENDPOINT =====================

# Template content for memory files
MEMORY_TEMPLATES = {
    "Budget.md": """# Budget Constraints

## Monthly Spending Limits
- Discretionary: $500/month

## Current Month
- Spent: $0
- Remaining: $500

## Last Updated
- {timestamp}
""",
    "Goals.md": """# Long-term Goals

## Financial Goals
- [ ] Set your savings goals here

## Personal Goals & Aspirations
- [ ] Reduce impulse purchases
- [ ] Build better spending habits

## Last Updated
- {timestamp}
""",
    "Behavior.md": """# Spending Patterns

## Observed Behaviors
- [No patterns recorded yet]

## Spending Patterns
- [No patterns recorded yet]

## High-Risk Triggers
- Late night shopping (after 11 PM)
- Flash sale websites

## Positive Patterns
- [None recorded yet]

## Last Updated
- {timestamp}
""",
    "State.md": """# Current Financial State

## Financial Overview
- Dedicated savings for fun purchases: $[AMOUNT]
- Savings Account: $[AMOUNT]
- Checking Account: $[AMOUNT]
- Monthly Income: $[AMOUNT]

## Recent Changes
- [No recent changes]

## Last Updated
- {timestamp}
"""
}


@app.post("/reset-memory", response_model=ResetMemoryResponse)
async def reset_memory() -> ResetMemoryResponse:
    """
    Reset all memory files to their template state.
    
    This endpoint erases all user data and preferences, returning
    the memory files to their initial template state.
    
    WARNING: This action cannot be undone!
    
    Returns:
        Status of the reset operation
    """
    from datetime import datetime
    
    try:
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        files_reset = 0
        
        # Ensure memory directory exists
        os.makedirs(MEMORY_DIR, exist_ok=True)
        
        # Step 1: Reset all .md files to template state
        for filename, template in MEMORY_TEMPLATES.items():
            file_path = os.path.join(MEMORY_DIR, filename)
            
            # Replace {timestamp} placeholder
            content = template.format(timestamp=timestamp)
            
            # Write template content (creates file if it doesn't exist)
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                
                # Verify file was written
                if os.path.exists(file_path):
                    files_reset += 1
                    print(f"[Reset] ✓ Reset {filename} to template state")
                else:
                    print(f"[Reset] ✗ ERROR: {filename} was not created!")
            except Exception as e:
                print(f"[Reset] ✗ ERROR writing {filename}: {e}")
                raise
        
        # Step 2: Clear ChromaDB persistent storage
        # Delete chroma.sqlite3 and all UUID-named directories
        chroma_db_file = os.path.join(MEMORY_DIR, "chroma.sqlite3")
        if os.path.exists(chroma_db_file):
            try:
                os.remove(chroma_db_file)
                print("[Reset] ✓ Deleted chroma.sqlite3")
            except Exception as e:
                print(f"[Reset] ⚠ Warning: Could not delete chroma.sqlite3: {e}")
        
        # Delete all UUID-named directories (ChromaDB collection data)
        uuid_dirs_deleted = 0
        for item in os.listdir(MEMORY_DIR):
            item_path = os.path.join(MEMORY_DIR, item)
            # Check if it's a UUID-named directory (format: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx)
            if os.path.isdir(item_path) and len(item) == 36 and item.count('-') == 4:
                try:
                    shutil.rmtree(item_path)
                    uuid_dirs_deleted += 1
                    print(f"[Reset] ✓ Deleted ChromaDB collection directory: {item}")
                except Exception as e:
                    print(f"[Reset] ⚠ Warning: Could not delete {item}: {e}")
        
        print(f"[Reset] Cleared {uuid_dirs_deleted} ChromaDB collection directories")
        
        # Step 3: Reindex ChromaDB with fresh templates
        # Note: reindex_memory() deletes the existing collection and creates a new one,
        # effectively clearing all old data from ChromaDB before indexing the reset .md files
        if memory_engine:
            # Explicitly clear ChromaDB by deleting and recreating the collection
            # This ensures all old chunks, embeddings, and metadata are removed
            print("[Reset] Reindexing ChromaDB with fresh templates...")
            await memory_engine.reindex_memory()
            print(f"[Reset] ✓ ChromaDB cleared and reindexed with {files_reset} fresh template files")
        
        return ResetMemoryResponse(
            status="success",
            files_reset=files_reset,
            message=f"Reset {files_reset} memory files to template state and cleared ChromaDB persistent storage"
        )
        
    except Exception as e:
        print(f"[Reset] Error resetting memory: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Error resetting memory: {str(e)}"
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


class ConsolidateMemoryResponse(BaseModel):
    """Response model for /consolidate-memory endpoint."""
    status: str = Field(..., description="Overall status of the operation")
    results: Dict[str, Any] = Field(..., description="Consolidation results per file")
    message: str = Field(..., description="Summary message")


@app.post("/consolidate-memory", response_model=ConsolidateMemoryResponse)
async def consolidate_memory() -> ConsolidateMemoryResponse:
    """
    Consolidate memory files that have grown too large.

    This endpoint checks each memory file and uses Gemini to consolidate/deduplicate
    entries in files that exceed size (>2KB) or observation (>10) thresholds.

    Use this endpoint periodically for maintenance or when memory files become bloated.

    Returns:
        Consolidation results for each file including size reduction stats
    """
    if not memory_engine:
        return ConsolidateMemoryResponse(
            status="error",
            results={},
            message="Memory engine not available"
        )

    try:
        results = await memory_engine.consolidate_memory()

        # Count consolidated files
        consolidated_count = sum(1 for r in results.values() if r.get('status') == 'consolidated')
        skipped_count = sum(1 for r in results.values() if r.get('status') == 'skipped')
        error_count = sum(1 for r in results.values() if r.get('status') == 'error')

        message = f"Consolidated {consolidated_count} files, skipped {skipped_count}, errors {error_count}"

        return ConsolidateMemoryResponse(
            status="success" if error_count == 0 else "partial",
            results=results,
            message=message
        )

    except Exception as e:
        print(f"[Consolidate] Error: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error consolidating memory: {str(e)}"
        )


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
        # BIOMETRICS_DISABLED: No longer fetching vitals from persage
        # # Step 1: Fetch real vitals from persage (or fallback to defaults)
        # biometrics = await get_current_biometrics()

        # Calculate derived telemetry values
        # Click rate: clicks per second (avoid division by zero)
        click_rate_calculated = request.click_count / max(request.time_on_site, 1.0)

        # Time to cart: use provided value or fallback to time_on_site
        time_to_cart_value = request.time_to_cart if request.time_to_cart is not None else request.time_on_site

        # Step 2: Prepare Fast Brain input data
        # BIOMETRICS_DISABLED: HR and RR removed, emotion_arousal set to neutral 0.5
        current_data = {
            # "heart_rate": biometrics["heart_rate"],
            # "respiration_rate": biometrics["respiration_rate"],
            "emotion_arousal": 0.5,  # Neutral arousal level (BIOMETRICS_DISABLED)

            # Real telemetry from browser extension
            "click_rate": click_rate_calculated,  # clicks per second
            "time_on_site": request.time_on_site,
            "time_to_cart": time_to_cart_value,
            "scroll_velocity_peak": request.peak_scroll_velocity,
            "system_hour": request.system_hour,
            "system_time": request.system_hour,  # inference_engine expects this key

            # Website context
            "website_name": request.website
        }
        
        # Step 3: Run Fast Brain inference
        p_impulse_fast = fast_brain.calculate_p_impulse(current_data)
        fast_intervention = fast_brain.get_intervention_level(p_impulse_fast)
        
        # Get structured output for dominant trigger and detailed logging
        structured_output = fast_brain.get_structured_output(current_data)
        dominant_trigger = structured_output.get("dominant_trigger", "unknown")
        logic_summary = structured_output.get("logic_summary", {})
        
        # ============ FAST BRAIN DETAILED OUTPUT ============
        print(f"\n[Pipeline] FAST BRAIN ANALYSIS:")
        print(f"  p_impulse: {p_impulse_fast:.3f}")
        print(f"  intervention_level: {fast_intervention}")
        print(f"  dominant_trigger: {dominant_trigger}")
        if logic_summary:
            print(f"  ---")
            print(f"  Z-scores: {logic_summary.get('z_scores', {})}")
            print(f"  Likelihoods: {logic_summary.get('likelihoods', {})}")
            print(f"  Weighted contributions: {logic_summary.get('weighted_contributions', {})}")
            print(f"  Context factors: {logic_summary.get('context_factors', {})}")
        print(f"{'='*60}\n")
        
        # Step 4: Run Slow Brain analysis
        if memory_engine:
            try:
                purchase_dict = {
                    "product": request.product,
                    "cost": request.cost,
                    "website": request.website,
                    "system_hour": request.system_hour,  # Time of day for late-night detection
                    # Telemetry for behavioral pattern learning
                    "time_to_cart": time_to_cart_value,
                    "time_on_site": request.time_on_site,
                    "click_rate": click_rate_calculated,
                    "peak_scroll_velocity": request.peak_scroll_velocity,
                    "click_count": request.click_count,
                    # BIOMETRICS_DISABLED: Real-time vitals no longer sent to Slow Brain
                    # "heart_rate": biometrics["heart_rate"],
                    # "respiration_rate": biometrics["respiration_rate"],
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
        # Fast Brain now uses same naming as Slow Brain: NONE/MIRROR/COOLDOWN/PHRASE
        return PipelineResponse(
            p_impulse_fast=p_impulse_fast,
            fast_brain_intervention=fast_intervention,
            fast_brain_dominant_trigger=dominant_trigger,
            impulse_score=p_impulse_fast,  # Use Fast Brain score directly
            confidence=0.5,  # Medium confidence without Slow Brain
            reasoning=f"Fast Brain analysis only. Score based on {dominant_trigger}. Slow Brain unavailable.",
            intervention_action=fast_intervention,  # No mapping needed - names now match
            memory_update=None
        )
        
    except Exception as e:
        print(f"[Pipeline] Error: {e}")
        # Complete fallback
        return PipelineResponse(
            p_impulse_fast=0.5,
            fast_brain_intervention="MIRROR",
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
if VERTEX_SERVICE_ACCOUNT_PATH and os.path.exists(VERTEX_SERVICE_ACCOUNT_PATH):
    try:
        gemini_client = GeminiClient(VERTEX_SERVICE_ACCOUNT_PATH)
        print("Gemini client initialized successfully")
    except Exception as e:
        print(f"Warning: Could not initialize Gemini client: {e}")
else:
    print("WARNING: Gemini client not initialized (no service account path)")


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
