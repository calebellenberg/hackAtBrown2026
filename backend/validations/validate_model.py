#!/usr/bin/env python3
"""
Model Validation Script for ImpulseGuard

This script validates the Fast Brain + Slow Brain architecture by:
1. Running comprehensive test scenarios through both systems
2. Validating outputs against multiple criteria:
   - Consistency: Slow Brain adjusts Fast Brain score contextually
   - Reasoning Quality: Cites specific user goals/budget from memory
   - Intervention Logic: Appropriate actions based on score thresholds
   - Memory Updates: Relevant updates when new patterns detected
3. Generating detailed validation report

Prerequisites:
- FastAPI server running: uvicorn app:app --reload
- Vertex AI API enabled with service account configured
- Memory store populated with user data

Usage:
    cd backend
    source venv/bin/activate
    python validate_model.py
"""

import asyncio
import json
import sys
import os
from typing import Dict, List, Any, Optional
from datetime import datetime
import httpx

# Check dependencies
try:
    from inference_engine import ImpulseInferenceEngine
except ImportError:
    print("❌ Error: inference_engine module not found.")
    sys.exit(1)


class ModelValidator:
    """
    Validates the Fast Brain + Slow Brain architecture end-to-end.
    """
    
    def __init__(self, api_base_url: str = "http://localhost:8000"):
        """
        Initialize the validator.
        
        Args:
            api_base_url: Base URL for the FastAPI backend
        """
        self.api_base_url = api_base_url
        self.results = []
        self.validation_summary = {
            "total_scenarios": 0,
            "passed": 0,
            "failed": 0,
            "warnings": 0,
            "consistency_checks": {"passed": 0, "failed": 0},
            "reasoning_checks": {"passed": 0, "failed": 0},
            "intervention_checks": {"passed": 0, "failed": 0},
            "memory_checks": {"passed": 0, "failed": 0}
        }
    
    def load_scenarios(self, scenarios_file: str = "test_scenarios.json") -> Dict[str, Any]:
        """
        Load test scenarios from JSON file.
        
        Args:
            scenarios_file: Path to scenarios JSON file
            
        Returns:
            Dictionary containing baseline data and scenarios
        """
        try:
            with open(scenarios_file, 'r') as f:
                data = json.load(f)
            print(f"✓ Loaded {len(data['scenarios'])} test scenarios")
            return data
        except FileNotFoundError:
            print(f"❌ Error: Scenarios file not found: {scenarios_file}")
            sys.exit(1)
        except json.JSONDecodeError as e:
            print(f"❌ Error: Invalid JSON in scenarios file: {e}")
            sys.exit(1)
    
    async def run_fast_brain(self, 
                            baseline_data: Dict[str, Any],
                            biometric_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Run Fast Brain (Bayesian Inference Engine).
        
        Args:
            baseline_data: User baseline statistics
            biometric_data: Current biometric and telemetry data
            
        Returns:
            Fast Brain results including p_impulse and structured output
        """
        try:
            engine = ImpulseInferenceEngine(
                baseline_data=baseline_data,
                prior_p=0.2
            )
            
            p_impulse_fast = engine.calculate_p_impulse(biometric_data)
            intervention_level = engine.get_intervention_level(p_impulse_fast)
            structured_output = engine.get_structured_output(biometric_data)
            
            return {
                "p_impulse_fast": p_impulse_fast,
                "intervention_level": intervention_level,
                "dominant_trigger": structured_output.get("dominant_trigger"),
                "contributions": structured_output.get("contributions"),
                "validation": engine.validate_logic(biometric_data, p_impulse_fast)
            }
        except Exception as e:
            return {
                "error": str(e),
                "p_impulse_fast": 0.5,  # Default fallback
                "intervention_level": "UNKNOWN"
            }
    
    async def run_slow_brain(self,
                            p_impulse_fast: float,
                            purchase_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Run Slow Brain via FastAPI endpoint.
        
        Args:
            p_impulse_fast: Fast Brain impulse probability
            purchase_data: Purchase details (product, cost, website)
            
        Returns:
            Slow Brain analysis results or None if API fails
        """
        request_data = {
            "p_impulse_fast": p_impulse_fast,
            "product": purchase_data["product"],
            "cost": purchase_data["cost"],
            "website": purchase_data["website"]
        }
        
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    f"{self.api_base_url}/analyze",
                    json=request_data
                )
                response.raise_for_status()
                return response.json()
        except httpx.HTTPError as e:
            print(f"\n⚠️  Slow Brain API error: {e}")
            return None
        except Exception as e:
            print(f"\n⚠️  Unexpected error calling Slow Brain: {e}")
            return None
    
    def validate_consistency(self,
                            fast_brain_result: Dict[str, Any],
                            slow_brain_result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate consistency: Slow Brain should contextually adjust Fast Brain score.
        
        Args:
            fast_brain_result: Fast Brain analysis
            slow_brain_result: Slow Brain analysis
            
        Returns:
            Validation result with passed/failed status and details
        """
        p_fast = fast_brain_result.get("p_impulse_fast", 0.5)
        p_slow = slow_brain_result.get("impulse_score", 0.5)
        
        # Check 1: Scores should be in valid range
        if not (0.0 <= p_slow <= 1.0):
            return {
                "passed": False,
                "reason": f"Slow Brain score {p_slow} out of range [0.0, 1.0]"
            }
        
        # Check 2: Slow Brain shouldn't just copy Fast Brain
        # Allow for small adjustments (±0.03) but require meaningful difference
        if abs(p_fast - p_slow) < 0.03:
            # Exception: If Fast Brain is already at extremes (0.0 or 1.0)
            # and context supports it, this is acceptable
            if p_fast <= 0.05 or p_fast >= 0.95:
                # Check if reasoning justifies the extreme score
                reasoning = slow_brain_result.get("reasoning", "")
                has_context_justification = any(kw in reasoning.lower() for kw in 
                    ["within budget", "aligns with", "violates", "exceeds", "conflicts", 
                     "budget", "goal", "limit", "supports", "appropriate"])
                if has_context_justification:
                    return {
                        "passed": True,
                        "score_adjustment": p_slow - p_fast,
                        "reason": "Extreme score justified by context"
                    }
            return {
                "passed": False,
                "reason": f"Score adjustment too small ({abs(p_fast - p_slow):.3f}), lacks contextual adjustment"
            }
        
        # Check 3: Large adjustments should make sense
        score_diff = p_slow - p_fast
        if abs(score_diff) > 0.3:
            # Large adjustment - should be justified in reasoning
            reasoning = slow_brain_result.get("reasoning", "")
            has_justification = any(keyword in reasoning.lower() for keyword in 
                                   ["budget", "goal", "savings", "limit", "exceeded", "aligns", "conflicts"])
            if not has_justification:
                return {
                    "passed": False,
                    "reason": f"Large score adjustment ({score_diff:+.3f}) not justified in reasoning"
                }
        
        return {
            "passed": True,
            "score_adjustment": score_diff,
            "reason": "Contextual adjustment appropriate"
        }
    
    def validate_reasoning_quality(self, slow_brain_result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate reasoning quality: Should cite specific user goals/budget.
        
        Args:
            slow_brain_result: Slow Brain analysis
            
        Returns:
            Validation result with passed/failed status and details
        """
        reasoning = slow_brain_result.get("reasoning", "").lower()
        
        if not reasoning or len(reasoning) < 20:
            return {
                "passed": False,
                "reason": "Reasoning too short or missing"
            }
        
        # Check for specific citations from memory
        memory_citations = []
        if "goals.md" in reasoning or "goal" in reasoning:
            memory_citations.append("Goals")
        if "budget.md" in reasoning or "budget" in reasoning or "spending limit" in reasoning:
            memory_citations.append("Budget")
        if "state.md" in reasoning or "balance" in reasoning or "financial state" in reasoning:
            memory_citations.append("State")
        if "behavior.md" in reasoning or "pattern" in reasoning or "behavior" in reasoning:
            memory_citations.append("Behavior")
        
        # Check for specific values/amounts
        has_specifics = any(indicator in reasoning for indicator in 
                          ["$", "limit", "spent", "remaining", "save", "vacation", "emergency fund"])
        
        if not memory_citations:
            return {
                "passed": False,
                "reason": "No citations from user memory (Goals/Budget/State/Behavior)"
            }
        
        if not has_specifics:
            return {
                "passed": False,
                "reason": "No specific values or constraints cited"
            }
        
        return {
            "passed": True,
            "citations": memory_citations,
            "has_specifics": True,
            "reason": f"Cites {', '.join(memory_citations)} with specific details"
        }
    
    def validate_intervention_logic(self,
                                   slow_brain_result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate intervention logic: Appropriate action based on score thresholds.
        
        Args:
            slow_brain_result: Slow Brain analysis
            
        Returns:
            Validation result with passed/failed status and details
        """
        score = slow_brain_result.get("impulse_score", 0.5)
        action = slow_brain_result.get("intervention_action", "NONE")
        
        # Define expected actions based on thresholds
        if score < 0.3:
            expected = ["NONE"]
        elif score < 0.6:
            expected = ["NONE", "MIRROR"]
        elif score < 0.8:
            expected = ["MIRROR", "COOLDOWN", "PHRASE"]
        else:
            expected = ["COOLDOWN", "PHRASE"]
        
        if action not in expected:
            return {
                "passed": False,
                "score": score,
                "action": action,
                "expected": expected,
                "reason": f"Action '{action}' inappropriate for score {score:.3f} (expected: {', '.join(expected)})"
            }
        
        return {
            "passed": True,
            "score": score,
            "action": action,
            "reason": f"Action '{action}' appropriate for score {score:.3f}"
        }
    
    def validate_memory_updates(self,
                               scenario: Dict[str, Any],
                               slow_brain_result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate memory updates: Relevant updates when new patterns detected.
        
        Args:
            scenario: Test scenario data
            slow_brain_result: Slow Brain analysis
            
        Returns:
            Validation result with passed/failed status and details
        """
        memory_update = slow_brain_result.get("memory_update")
        score = slow_brain_result.get("impulse_score", 0.5)
        
        # High impulse scenarios should often (but not always) generate memory updates
        if score > 0.7:
            if memory_update:
                # Validate update is meaningful
                if len(memory_update) < 10:
                    return {
                        "passed": False,
                        "reason": "Memory update too short to be meaningful"
                    }
                return {
                    "passed": True,
                    "has_update": True,
                    "update_length": len(memory_update),
                    "reason": "Appropriate memory update generated"
                }
            else:
                # No update is acceptable, just note it
                return {
                    "passed": True,
                    "has_update": False,
                    "reason": "No memory update (acceptable)"
                }
        else:
            # Low/medium scores - update optional
            return {
                "passed": True,
                "has_update": bool(memory_update),
                "reason": "Memory update optional for this score"
            }
    
    async def validate_scenario(self,
                               scenario: Dict[str, Any],
                               baseline_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Run complete validation for a single scenario.
        
        Args:
            scenario: Test scenario data
            baseline_data: User baseline statistics
            
        Returns:
            Complete validation results for the scenario
        """
        print(f"\n{'='*80}")
        print(f"Scenario: {scenario['name']}")
        print(f"ID: {scenario['id']}")
        print(f"{'='*80}")
        
        result = {
            "scenario_id": scenario["id"],
            "scenario_name": scenario["name"],
            "description": scenario["description"],
            "expected_outcome": scenario["expected_outcome"],
            "timestamp": datetime.now().isoformat()
        }
        
        # Step 1: Run Fast Brain
        print("\n[1/4] Running Fast Brain...")
        fast_brain_result = await self.run_fast_brain(
            baseline_data,
            scenario["biometric_data"]
        )
        result["fast_brain"] = fast_brain_result
        print(f"      p_impulse_fast: {fast_brain_result.get('p_impulse_fast', 'N/A'):.3f}")
        print(f"      Intervention: {fast_brain_result.get('intervention_level', 'N/A')}")
        
        # Step 2: Run Slow Brain
        print("\n[2/4] Running Slow Brain...")
        slow_brain_result = await self.run_slow_brain(
            fast_brain_result["p_impulse_fast"],
            scenario["purchase_data"]
        )
        
        if not slow_brain_result:
            result["slow_brain"] = None
            result["validation"] = {
                "overall_passed": False,
                "error": "Slow Brain API unavailable"
            }
            return result
        
        result["slow_brain"] = slow_brain_result
        print(f"      impulse_score: {slow_brain_result.get('impulse_score', 'N/A'):.3f}")
        print(f"      Confidence: {slow_brain_result.get('confidence', 'N/A'):.3f}")
        print(f"      Intervention: {slow_brain_result.get('intervention_action', 'N/A')}")
        
        # Step 3: Run validation checks
        print("\n[3/4] Running validation checks...")
        
        consistency = self.validate_consistency(fast_brain_result, slow_brain_result)
        print(f"      Consistency: {'✓ PASS' if consistency['passed'] else '✗ FAIL'} - {consistency['reason']}")
        
        reasoning = self.validate_reasoning_quality(slow_brain_result)
        print(f"      Reasoning: {'✓ PASS' if reasoning['passed'] else '✗ FAIL'} - {reasoning['reason']}")
        
        intervention = self.validate_intervention_logic(slow_brain_result)
        print(f"      Intervention: {'✓ PASS' if intervention['passed'] else '✗ FAIL'} - {intervention['reason']}")
        
        memory = self.validate_memory_updates(scenario, slow_brain_result)
        print(f"      Memory: {'✓ PASS' if memory['passed'] else '✗ FAIL'} - {memory['reason']}")
        
        # Step 4: Overall assessment
        all_checks = [consistency, reasoning, intervention, memory]
        overall_passed = all(check["passed"] for check in all_checks)
        
        result["validation"] = {
            "overall_passed": overall_passed,
            "consistency": consistency,
            "reasoning": reasoning,
            "intervention": intervention,
            "memory": memory
        }
        
        print(f"\n[4/4] Overall: {'✓ PASSED' if overall_passed else '✗ FAILED'}")
        
        # Update summary statistics
        self.validation_summary["total_scenarios"] += 1
        if overall_passed:
            self.validation_summary["passed"] += 1
        else:
            self.validation_summary["failed"] += 1
        
        # Update category statistics
        for category, check in [("consistency", consistency), ("reasoning", reasoning),
                               ("intervention", intervention), ("memory", memory)]:
            key = f"{category}_checks"
            if check["passed"]:
                self.validation_summary[key]["passed"] += 1
            else:
                self.validation_summary[key]["failed"] += 1
        
        return result
    
    async def run_validation_suite(self, scenarios_file: str = "test_scenarios.json") -> List[Dict[str, Any]]:
        """
        Run the complete validation suite.
        
        Args:
            scenarios_file: Path to scenarios JSON file
            
        Returns:
            List of validation results for all scenarios
        """
        print("\n" + "="*80)
        print("ImpulseGuard Model Validation Suite")
        print("="*80)
        print(f"Start Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"API Base URL: {self.api_base_url}")
        
        # Check API health
        print("\nChecking API availability...")
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self.api_base_url}/health")
                response.raise_for_status()
            print("✓ API is available")
        except Exception as e:
            print(f"✗ API is not available: {e}")
            print("\nPlease start the FastAPI server:")
            print("  cd backend && uvicorn app:app --reload")
            sys.exit(1)
        
        # Load scenarios
        data = self.load_scenarios(scenarios_file)
        baseline_data = data["baseline_data"]
        scenarios = data["scenarios"]
        
        print(f"\nBaseline Data: {json.dumps(baseline_data, indent=2)}")
        print(f"\nRunning {len(scenarios)} scenarios...")
        
        # Run each scenario
        for i, scenario in enumerate(scenarios, 1):
            print(f"\n\n{'#'*80}")
            print(f"# Scenario {i}/{len(scenarios)}")
            print(f"{'#'*80}")
            
            result = await self.validate_scenario(scenario, baseline_data)
            self.results.append(result)
            
            # Longer delay between scenarios to avoid rate limiting (429 errors)
            await asyncio.sleep(3)
        
        # Print summary
        self.print_summary()
        
        return self.results
    
    def print_summary(self):
        """Print validation summary statistics."""
        print("\n\n" + "="*80)
        print("VALIDATION SUMMARY")
        print("="*80)
        
        summary = self.validation_summary
        total = summary["total_scenarios"]
        passed = summary["passed"]
        failed = summary["failed"]
        pass_rate = (passed / total * 100) if total > 0 else 0
        
        print(f"\nOverall Results:")
        print(f"  Total Scenarios: {total}")
        print(f"  Passed: {passed} ({pass_rate:.1f}%)")
        print(f"  Failed: {failed}")
        
        print(f"\nValidation Criteria Breakdown:")
        for category in ["consistency", "reasoning", "intervention", "memory"]:
            key = f"{category}_checks"
            cat_passed = summary[key]["passed"]
            cat_failed = summary[key]["failed"]
            cat_total = cat_passed + cat_failed
            cat_rate = (cat_passed / cat_total * 100) if cat_total > 0 else 0
            print(f"  {category.title()}: {cat_passed}/{cat_total} ({cat_rate:.1f}%)")
        
        print(f"\n{'='*80}")
    
    def save_results(self, output_file: str = "validation_results.json"):
        """
        Save validation results to JSON file.
        
        Args:
            output_file: Output file path
        """
        output_data = {
            "metadata": {
                "timestamp": datetime.now().isoformat(),
                "api_base_url": self.api_base_url,
                "total_scenarios": self.validation_summary["total_scenarios"]
            },
            "summary": self.validation_summary,
            "results": self.results
        }
        
        with open(output_file, 'w') as f:
            json.dump(output_data, f, indent=2)
        
        print(f"\n✓ Results saved to: {output_file}")


async def main():
    """Main execution function."""
    validator = ModelValidator()
    
    try:
        results = await validator.run_validation_suite()
        validator.save_results()
        
        # Exit with appropriate code
        if validator.validation_summary["failed"] > 0:
            sys.exit(1)
        else:
            sys.exit(0)
            
    except KeyboardInterrupt:
        print("\n\n⚠️  Validation interrupted by user")
        validator.save_results("validation_results_partial.json")
        sys.exit(130)
    except Exception as e:
        print(f"\n\n❌ Validation failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
