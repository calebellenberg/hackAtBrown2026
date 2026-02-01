#!/usr/bin/env python3
"""
Iterative Validation Script for ImpulseGuard Slow Brain Prompt

This script runs test scenarios through the pipeline API and validates
that outputs are sensible. It supports iterative refinement - run until
all scenarios pass.

Usage:
    cd backend
    source venv/bin/activate
    python validate_prompt.py
"""

import asyncio
import httpx
import json
from datetime import datetime
from typing import Dict, List, Any, Optional
from dataclasses import dataclass

# Backend API URL
BACKEND_URL = "http://localhost:8000"


@dataclass
class TestScenario:
    """A test scenario for validating prompt behavior."""
    name: str
    product: str
    cost: float
    website: str
    system_hour: int
    time_on_site: float
    click_count: int
    peak_scroll_velocity: float
    
    # Expected outcomes
    expected_score_max: float  # Score should be <= this
    expected_score_min: float  # Score should be >= this  
    expected_interventions: List[str]  # Acceptable interventions
    reasoning_must_contain: List[str]  # Keywords that must appear in reasoning
    description: str  # Why this scenario should behave this way


# Define test scenarios
TEST_SCENARIOS = [
    # === LOW RISK ESSENTIALS ===
    TestScenario(
        name="Spoon at 2 AM",
        product="Stainless Steel Spoon Set",
        cost=5.99,
        website="amazon.com",
        system_hour=2,
        time_on_site=120,
        click_count=5,
        peak_scroll_velocity=200,
        expected_score_max=0.45,
        expected_score_min=0.0,
        expected_interventions=["NONE"],
        reasoning_must_contain=[],  # Just needs to be low
        description="Essential household item - late night should NOT increase score"
    ),
    TestScenario(
        name="Kitchen Utensils at Midnight",
        product="Kitchen Utensil Set - Spatula Fork Spoon",
        cost=12.99,
        website="amazon.com",
        system_hour=0,
        time_on_site=180,
        click_count=8,
        peak_scroll_velocity=150,
        expected_score_max=0.45,
        expected_score_min=0.0,
        expected_interventions=["NONE"],
        reasoning_must_contain=[],
        description="Kitchen essentials are low risk even at midnight"
    ),
    TestScenario(
        name="Groceries Morning",
        product="Organic Milk 1 Gallon",
        cost=6.99,
        website="amazon.com",
        system_hour=10,
        time_on_site=60,
        click_count=3,
        peak_scroll_velocity=100,
        expected_score_max=0.35,
        expected_score_min=0.0,
        expected_interventions=["NONE"],
        reasoning_must_contain=[],
        description="Basic grocery item during normal hours"
    ),
    TestScenario(
        name="Toilet Paper Bulk",
        product="Toilet Paper 24 Pack",
        cost=24.99,
        website="amazon.com",
        system_hour=23,
        time_on_site=45,
        click_count=2,
        peak_scroll_velocity=50,
        expected_score_max=0.40,
        expected_score_min=0.0,
        expected_interventions=["NONE"],
        reasoning_must_contain=[],
        description="Essential supplies - even late night should be fine"
    ),
    
    # === HIGH RISK LUXURY ===
    TestScenario(
        name="Gaming Console at 2 AM",
        product="PlayStation 5 Console",
        cost=499.99,
        website="amazon.com",
        system_hour=2,
        time_on_site=300,
        click_count=15,
        peak_scroll_velocity=400,
        expected_score_max=1.0,
        expected_score_min=0.70,
        expected_interventions=["COOLDOWN", "PHRASE"],
        reasoning_must_contain=["budget", "late"],
        description="Expensive luxury item at 2 AM - should trigger strong intervention"
    ),
    TestScenario(
        name="Flash Sale TV at Midnight",
        product="65 inch 4K TV - FLASH SALE LIMITED TIME",
        cost=799.99,
        website="amazon.com",
        system_hour=0,
        time_on_site=120,
        click_count=20,
        peak_scroll_velocity=500,
        expected_score_max=1.0,
        expected_score_min=0.75,
        expected_interventions=["COOLDOWN", "PHRASE"],
        reasoning_must_contain=["budget"],
        description="Flash sale language + expensive + late night = high risk"
    ),
    TestScenario(
        name="Designer Shoes Afternoon",
        product="Gucci Leather Sneakers",
        cost=650.00,
        website="gucci.com",
        system_hour=14,
        time_on_site=600,
        click_count=25,
        peak_scroll_velocity=200,
        expected_score_max=1.0,
        expected_score_min=0.60,
        expected_interventions=["MIRROR", "COOLDOWN", "PHRASE"],
        reasoning_must_contain=["budget"],
        description="Luxury item way over budget - even during day should flag"
    ),
    
    # === GAMBLING (ALWAYS HIGH RISK) ===
    TestScenario(
        name="Poker Chips Gambling Site",
        product="Poker Chips Bundle $100",
        cost=100.00,
        website="pokerstars.com",
        system_hour=22,
        time_on_site=180,
        click_count=10,
        peak_scroll_velocity=300,
        expected_score_max=1.0,
        expected_score_min=0.80,
        expected_interventions=["COOLDOWN", "PHRASE"],
        reasoning_must_contain=[],
        description="Gambling site = always high risk"
    ),
    
    # === GOAL-ALIGNED PURCHASES ===
    TestScenario(
        name="Japanese Phrasebook (Goal Aligned)",
        product="Japanese Language Phrasebook for Travel",
        cost=19.99,
        website="amazon.com",
        system_hour=15,
        time_on_site=300,
        click_count=8,
        peak_scroll_velocity=150,
        expected_score_max=0.45,
        expected_score_min=0.0,
        expected_interventions=["NONE"],
        reasoning_must_contain=["japan", "goal"],
        description="Aligns with stated goal to save for Japan trip"
    ),
    TestScenario(
        name="Travel Luggage (Goal Aligned)",
        product="Carry-On Luggage for Travel",
        cost=89.99,
        website="amazon.com",
        system_hour=12,
        time_on_site=400,
        click_count=12,
        peak_scroll_velocity=180,
        expected_score_max=0.55,
        expected_score_min=0.0,
        expected_interventions=["NONE", "MIRROR"],
        reasoning_must_contain=["travel", "goal"],
        description="Travel gear for planned Japan trip"
    ),
    
    # === BUDGET VIOLATIONS ===
    TestScenario(
        name="Expensive Headphones Over Electronics Budget",
        product="Sony WH-1000XM5 Headphones",
        cost=349.99,
        website="amazon.com",
        system_hour=16,
        time_on_site=500,
        click_count=15,
        peak_scroll_velocity=200,
        expected_score_max=1.0,  # Budget violations can be high
        expected_score_min=0.55,
        expected_interventions=["MIRROR", "COOLDOWN", "PHRASE"],  # Allow PHRASE for significant overages
        reasoning_must_contain=["budget"],
        description="Exceeds $300/month electronics budget"
    ),
    TestScenario(
        name="Clothing Over Budget",
        product="Winter Jacket Premium",
        cost=280.00,
        website="amazon.com",
        system_hour=19,
        time_on_site=350,
        click_count=10,
        peak_scroll_velocity=175,
        expected_score_max=1.0,  # Budget violations can be high
        expected_score_min=0.50,
        expected_interventions=["MIRROR", "COOLDOWN", "PHRASE"],  # Allow PHRASE for significant overages
        reasoning_must_contain=["budget"],
        description="Exceeds $200/month clothing budget"
    ),
    
    # === MEDIUM RISK NORMAL ===
    TestScenario(
        name="Book During Day",
        product="Python Programming Book",
        cost=35.00,
        website="amazon.com",
        system_hour=11,
        time_on_site=200,
        click_count=6,
        peak_scroll_velocity=120,
        expected_score_max=0.50,
        expected_score_min=0.0,
        expected_interventions=["NONE", "MIRROR"],
        reasoning_must_contain=[],
        description="Reasonable discretionary purchase during normal hours"
    ),
    TestScenario(
        name="Moderate Electronics",
        product="Wireless Mouse",
        cost=29.99,
        website="amazon.com",
        system_hour=14,
        time_on_site=150,
        click_count=5,
        peak_scroll_velocity=100,
        expected_score_max=0.45,
        expected_score_min=0.0,
        expected_interventions=["NONE"],
        reasoning_must_contain=[],
        description="Low cost electronics within budget"
    ),
]


async def run_scenario(client: httpx.AsyncClient, scenario: TestScenario) -> Dict[str, Any]:
    """Run a single test scenario through the pipeline API."""
    request_body = {
        "product": scenario.product,
        "cost": scenario.cost,
        "website": scenario.website,
        "time_to_cart": scenario.time_on_site * 0.8,  # Assume 80% of time before cart
        "time_on_site": scenario.time_on_site,
        "click_count": scenario.click_count,
        "peak_scroll_velocity": scenario.peak_scroll_velocity,
        "system_hour": scenario.system_hour
    }
    
    try:
        response = await client.post(
            f"{BACKEND_URL}/pipeline-analyze",
            json=request_body,
            timeout=60.0
        )
        response.raise_for_status()
        return response.json()
    except Exception as e:
        return {"error": str(e)}


def validate_scenario(scenario: TestScenario, result: Dict[str, Any]) -> Dict[str, Any]:
    """Validate a scenario result against expected outcomes."""
    if "error" in result:
        return {
            "passed": False,
            "reason": f"API Error: {result['error']}",
            "checks": {}
        }
    
    checks = {}
    all_passed = True
    
    # Check 1: Score within expected range
    score = result.get("impulse_score", 0)
    score_in_range = scenario.expected_score_min <= score <= scenario.expected_score_max
    checks["score_range"] = {
        "passed": score_in_range,
        "expected": f"{scenario.expected_score_min:.2f} - {scenario.expected_score_max:.2f}",
        "actual": f"{score:.3f}"
    }
    if not score_in_range:
        all_passed = False
    
    # Check 2: Intervention is acceptable
    intervention = result.get("intervention_action", "UNKNOWN")
    intervention_ok = intervention in scenario.expected_interventions
    checks["intervention"] = {
        "passed": intervention_ok,
        "expected": scenario.expected_interventions,
        "actual": intervention
    }
    if not intervention_ok:
        all_passed = False
    
    # Check 3: Reasoning contains required keywords
    reasoning = result.get("reasoning", "").lower()
    missing_keywords = []
    for keyword in scenario.reasoning_must_contain:
        if keyword.lower() not in reasoning:
            missing_keywords.append(keyword)
    
    keywords_ok = len(missing_keywords) == 0
    checks["reasoning_keywords"] = {
        "passed": keywords_ok,
        "expected": scenario.reasoning_must_contain,
        "missing": missing_keywords
    }
    if not keywords_ok:
        all_passed = False
    
    return {
        "passed": all_passed,
        "reason": "All checks passed" if all_passed else "One or more checks failed",
        "checks": checks,
        "reasoning": result.get("reasoning", ""),
        "memory_update": result.get("memory_update")
    }


async def run_validation_suite() -> Dict[str, Any]:
    """Run all test scenarios and return results."""
    print("=" * 70)
    print("IMPULSE GUARD PROMPT VALIDATION SUITE")
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)
    print()
    
    results = []
    passed_count = 0
    failed_count = 0
    
    async with httpx.AsyncClient() as client:
        # Check if backend is running
        try:
            health = await client.get(f"{BACKEND_URL}/health", timeout=5.0)
            if health.status_code != 200:
                print("ERROR: Backend is not healthy. Please start the server first.")
                return {"error": "Backend not running"}
        except Exception as e:
            print(f"ERROR: Cannot connect to backend at {BACKEND_URL}")
            print(f"Please run: cd backend && source venv/bin/activate && uvicorn app:app --reload")
            return {"error": str(e)}
        
        print(f"Running {len(TEST_SCENARIOS)} test scenarios...\n")
        
        for i, scenario in enumerate(TEST_SCENARIOS, 1):
            print(f"[{i}/{len(TEST_SCENARIOS)}] {scenario.name}")
            print(f"    Product: {scenario.product} (${scenario.cost:.2f})")
            print(f"    Time: {scenario.system_hour}:00, Site: {scenario.website}")
            print(f"    Expected: score {scenario.expected_score_min:.2f}-{scenario.expected_score_max:.2f}, intervention {scenario.expected_interventions}")
            
            # Run the scenario
            api_result = await run_scenario(client, scenario)
            
            # Add delay to avoid rate limiting
            await asyncio.sleep(2)
            
            # Validate
            validation = validate_scenario(scenario, api_result)
            
            # Record result
            result = {
                "scenario": scenario.name,
                "description": scenario.description,
                "api_result": api_result,
                "validation": validation
            }
            results.append(result)
            
            if validation["passed"]:
                passed_count += 1
                print(f"    ✅ PASSED - Score: {api_result.get('impulse_score', 'N/A'):.3f}, Action: {api_result.get('intervention_action', 'N/A')}")
            else:
                failed_count += 1
                print(f"    ❌ FAILED - Score: {api_result.get('impulse_score', 'N/A'):.3f}, Action: {api_result.get('intervention_action', 'N/A')}")
                for check_name, check_result in validation["checks"].items():
                    if not check_result["passed"]:
                        print(f"       - {check_name}: expected {check_result.get('expected')}, got {check_result.get('actual', check_result.get('missing'))}")
            
            print()
    
    # Summary
    print("=" * 70)
    print("VALIDATION SUMMARY")
    print("=" * 70)
    print(f"Total Scenarios: {len(TEST_SCENARIOS)}")
    print(f"Passed: {passed_count} ({100*passed_count/len(TEST_SCENARIOS):.1f}%)")
    print(f"Failed: {failed_count} ({100*failed_count/len(TEST_SCENARIOS):.1f}%)")
    print()
    
    if failed_count > 0:
        print("FAILED SCENARIOS:")
        for result in results:
            if not result["validation"]["passed"]:
                print(f"  - {result['scenario']}: {result['description']}")
                print(f"    Reasoning: {result['validation'].get('reasoning', 'N/A')[:200]}...")
        print()
        print("ACTION: Review the failed scenarios and refine the prompt in memory.py")
    else:
        print("🎉 ALL SCENARIOS PASSED! Prompt is working as expected.")
    
    # Save results to file
    output_file = "prompt_validation_results.json"
    with open(output_file, "w") as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "summary": {
                "total": len(TEST_SCENARIOS),
                "passed": passed_count,
                "failed": failed_count,
                "pass_rate": passed_count / len(TEST_SCENARIOS)
            },
            "results": results
        }, f, indent=2, default=str)
    
    print(f"\nDetailed results saved to: {output_file}")
    
    return {
        "passed": passed_count,
        "failed": failed_count,
        "total": len(TEST_SCENARIOS),
        "results": results
    }


if __name__ == "__main__":
    asyncio.run(run_validation_suite())
