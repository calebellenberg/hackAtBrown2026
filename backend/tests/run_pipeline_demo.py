#!/usr/bin/env python3
"""
Complete Pipeline Demo: Fast Brain → Slow Brain

This script demonstrates the full ImpulseGuard pipeline:
1. Fast Brain (Bayesian Inference) calculates initial impulse probability
2. Slow Brain (RAG + Gemini) provides context-aware reasoning
3. Results are displayed showing the complete flow

Prerequisites:
- FastAPI server must be running: uvicorn app:app --reload
- VERTEX_SERVICE_ACCOUNT_PATH must be set in backend/.env (path to Google Cloud service account JSON file)
- Memory files must exist in backend/memory_store/

Usage:
    cd backend
    source venv/bin/activate
    uvicorn app:app --reload  # In one terminal
    python run_pipeline_demo.py  # In another terminal
    
    OR use the venv Python directly:
    ./venv/bin/python run_pipeline_demo.py
"""

import asyncio
import json
import sys

# Check for required dependencies
try:
    import httpx
except ImportError:
    print("❌ Error: httpx module not found.")
    print("\nPlease install dependencies:")
    print("  cd backend")
    print("  source venv/bin/activate")
    print("  pip install -r requirements.txt")
    print("\nOr run with the venv Python:")
    print("  ./venv/bin/python run_pipeline_demo.py")
    sys.exit(1)

try:
    from inference_engine import ImpulseInferenceEngine
except ImportError:
    print("❌ Error: inference_engine module not found.")
    print("Make sure you're running from the backend directory.")
    sys.exit(1)


# Sample baseline data (typical user)
SAMPLE_BASELINE = {
    "heart_rate": {"mean": 72.0, "std": 10.0},  # BPM
    "respiration_rate": {"mean": 16.0, "std": 3.0},  # breaths/min
    "scroll_velocity": {"mean": 50.0, "std": 20.0},  # pixels/sec
    "click_rate": {"mean": 2.0, "std": 1.0},  # clicks/sec
    "time_on_site": {"mean": 180.0, "std": 60.0}  # seconds
}

# Sample current biometric/telemetry data
SAMPLE_CURRENT_DATA = {
    "heart_rate": 95.0,  # Elevated (high stress)
    "respiration_rate": 22.0,  # Elevated
    "emotion_arousal": 0.85,  # Very high arousal
    "click_rate": 5.0,  # Rapid clicking
    "time_on_website": 45.0,  # Short time on site
    "system_time": 3,  # 3 AM (late night)
    "scroll_velocity_peak": 120.0,  # Very fast scrolling
    "time_to_cart": 35.0,  # Low TTC (35 seconds) - impulsive
    "website_name": "temu.com"  # High-risk e-commerce
}

# Sample purchase data
SAMPLE_PURCHASE = {
    "product": "Wireless Noise-Cancelling Headphones",
    "cost": 129.99,
    "website": "temu.com"
}

# FastAPI endpoint
API_BASE_URL = "http://localhost:8000"


def print_section(title: str, char: str = "="):
    """Print a formatted section header."""
    print(f"\n{char * 80}")
    print(f"  {title}")
    print(f"{char * 80}\n")


def print_json(data: dict, title: str = "Data"):
    """Pretty print JSON data."""
    print(f"{title}:")
    print(json.dumps(data, indent=2))


async def run_fast_brain() -> float:
    """
    Step 1: Run Fast Brain (Bayesian Inference Engine)
    Calculates initial impulse probability from biometric/telemetry data.
    """
    print_section("STEP 1: Fast Brain (Bayesian Inference)")
    
    # Initialize Fast Brain
    fast_brain = ImpulseInferenceEngine(
        baseline_data=SAMPLE_BASELINE,
        prior_p=0.2
    )
    
    # Calculate impulse probability
    p_impulse_fast = fast_brain.calculate_p_impulse(SAMPLE_CURRENT_DATA)
    
    # Get intervention level
    intervention_level = fast_brain.get_intervention_level(p_impulse_fast)
    
    # Get structured output
    structured_output = fast_brain.get_structured_output(SAMPLE_CURRENT_DATA)
    
    print(f"Input Data:")
    print_json(SAMPLE_CURRENT_DATA, "")
    
    print(f"\nFast Brain Results:")
    print(f"  Probability (p_impulse_fast): {p_impulse_fast:.3f}")
    print(f"  Intervention Level: {intervention_level}")
    print(f"  Dominant Trigger: {structured_output['dominant_trigger']}")
    
    print(f"\nFast Brain Validation:")
    validation = fast_brain.validate_logic(SAMPLE_CURRENT_DATA, p_impulse_fast)
    print(validation)
    
    return p_impulse_fast


async def run_slow_brain(p_impulse_fast: float) -> dict:
    """
    Step 2: Run Slow Brain (RAG + Vertex AI Reasoning)
    Provides context-aware reasoning using user's memory.
    """
    print_section("STEP 2: Slow Brain (RAG + Vertex AI Reasoning)")
    
    # Prepare request
    request_data = {
        "p_impulse_fast": p_impulse_fast,
        "product": SAMPLE_PURCHASE["product"],
        "cost": SAMPLE_PURCHASE["cost"],
        "website": SAMPLE_PURCHASE["website"]
    }
    
    print("Request to Slow Brain API:")
    print_json(request_data, "")
    
    # Call FastAPI endpoint
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.post(
                f"{API_BASE_URL}/analyze",
                json=request_data
            )
            response.raise_for_status()
            result = response.json()
            
            print(f"\nSlow Brain Response:")
            print_json(result, "")
            
            return result
            
        except httpx.HTTPError as e:
            print(f"\n❌ Error calling Slow Brain API: {e}")
            print("Make sure the FastAPI server is running:")
            print("  cd backend && uvicorn app:app --reload")
            return None
        except Exception as e:
            print(f"\n❌ Unexpected error: {e}")
            return None


def print_final_summary(p_impulse_fast: float, slow_brain_result: dict):
    """Print final summary comparing Fast and Slow Brain results."""
    print_section("FINAL SUMMARY: Fast Brain vs Slow Brain")
    
    if slow_brain_result is None:
        print("⚠️  Slow Brain unavailable - using Fast Brain results only")
        print(f"\nFinal Impulse Score: {p_impulse_fast:.3f}")
        return
    
    print("Comparison:")
    print(f"  Fast Brain Score:  {p_impulse_fast:.3f}")
    print(f"  Slow Brain Score:  {slow_brain_result['impulse_score']:.3f}")
    print(f"  Difference:        {abs(slow_brain_result['impulse_score'] - p_impulse_fast):.3f}")
    print(f"  Confidence:        {slow_brain_result['confidence']:.3f}")
    
    print(f"\nFinal Recommendation:")
    print(f"  Intervention: {slow_brain_result['intervention_action']}")
    print(f"  Reasoning: {slow_brain_result['reasoning']}")
    
    if slow_brain_result.get('memory_update'):
        print(f"\n📝 Memory Updated:")
        print(f"  {slow_brain_result['memory_update']}")
    else:
        print(f"\n📝 No memory update needed")


async def main():
    """Run the complete pipeline."""
    print_section("IMPULSEGUARD COMPLETE PIPELINE DEMO", "=")
    print("This demo shows the full flow from Fast Brain to Slow Brain")
    print("=" * 80)
    
    # Step 1: Fast Brain
    p_impulse_fast = await run_fast_brain()
    
    # Step 2: Slow Brain
    slow_brain_result = await run_slow_brain(p_impulse_fast)
    
    # Final Summary
    print_final_summary(p_impulse_fast, slow_brain_result)
    
    print_section("DEMO COMPLETE", "=")


if __name__ == "__main__":
    asyncio.run(main())
