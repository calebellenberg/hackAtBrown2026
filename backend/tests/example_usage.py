"""
Example usage and test cases for ImpulseGuard Inference Engine

This file demonstrates how to use the ImpulseInferenceEngine and includes
test cases for various scenarios including happy excitement vs impulsive stress.
"""

from inference_engine import ImpulseInferenceEngine
import json


def print_separator(title: str = ""):
    """Print a visual separator for test cases."""
    print("\n" + "=" * 80)
    if title:
        print(f"  {title}")
        print("=" * 80)
    print()


def main():
    """Run example usage and test cases."""
    
    # Sample baseline data (typical user)
    sample_baseline = {
        "heart_rate": {"mean": 72.0, "std": 10.0},  # BPM
        "respiration_rate": {"mean": 16.0, "std": 3.0},  # breaths/min
        "scroll_velocity": {"mean": 50.0, "std": 20.0},  # pixels/sec
        "click_rate": {"mean": 2.0, "std": 1.0},  # clicks/sec
        "time_on_site": {"mean": 180.0, "std": 60.0}  # seconds
    }
    
    # Initialize engine
    engine = ImpulseInferenceEngine(baseline_data=sample_baseline, prior_p=0.2)
    
    print_separator("ImpulseGuard Inference Engine - Example Usage")
    
    # Test Case 1: Happy Excitement (Planned Gift Purchase)
    print_separator("Test Case 1: Happy Excitement (Planned Gift Purchase)")
    
    happy_excitement_data = {
        "heart_rate": 75.0,  # Slightly elevated but normal
        "respiration_rate": 17.0,  # Normal
        "emotion_arousal": 0.35,  # Low arousal (calm)
        "click_rate": 1.5,  # Moderate clicking
        "time_on_website": 450.0,  # Long browsing time
        "system_time": 14,  # 2 PM (daytime)
        "scroll_velocity_peak": 45.0,  # Normal scrolling
        "time_to_cart": 420.0,  # High TTC (7 minutes) - planned purchase
        "website_name": "amazon.com"
    }
    
    p_happy = engine.calculate_p_impulse(happy_excitement_data)
    intervention_happy = engine.get_intervention_level(p_happy)
    structured_happy = engine.get_structured_output(happy_excitement_data)
    
    print(f"Probability: {p_happy:.3f}")
    print(f"Intervention Level: {intervention_happy}")
    print("\nStructured Output:")
    print(json.dumps(structured_happy, indent=2))
    print("\nValidation Logic:")
    print(engine.validate_logic(happy_excitement_data, p_happy))
    
    # Test Case 2: Impulsive Stress (Late Night Flash Sale)
    print_separator("Test Case 2: Impulsive Stress (Late Night Flash Sale)")
    
    impulsive_stress_data = {
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
    
    p_impulsive = engine.calculate_p_impulse(impulsive_stress_data)
    intervention_impulsive = engine.get_intervention_level(p_impulsive)
    structured_impulsive = engine.get_structured_output(impulsive_stress_data)
    
    print(f"Probability: {p_impulsive:.3f}")
    print(f"Intervention Level: {intervention_impulsive}")
    print("\nStructured Output:")
    print(json.dumps(structured_impulsive, indent=2))
    print("\nValidation Logic:")
    print(engine.validate_logic(impulsive_stress_data, p_impulsive))
    
    # Test Case 3: Moderate Scenario (Normal Shopping)
    print_separator("Test Case 3: Moderate Scenario (Normal Shopping)")
    
    moderate_data = {
        "heart_rate": 70.0,  # Normal
        "respiration_rate": 15.0,  # Normal
        "emotion_arousal": 0.50,  # Moderate arousal
        "click_rate": 2.5,  # Normal clicking
        "time_on_website": 200.0,  # Average time
        "system_time": 19,  # 7 PM (evening)
        "scroll_velocity_peak": 55.0,  # Normal scrolling
        "time_to_cart": 180.0,  # Moderate TTC (3 minutes)
        "website_name": "target.com"
    }
    
    p_moderate = engine.calculate_p_impulse(moderate_data)
    intervention_moderate = engine.get_intervention_level(p_moderate)
    structured_moderate = engine.get_structured_output(moderate_data)
    
    print(f"Probability: {p_moderate:.3f}")
    print(f"Intervention Level: {intervention_moderate}")
    print("\nStructured Output:")
    print(json.dumps(structured_moderate, indent=2))
    print("\nValidation Logic:")
    print(engine.validate_logic(moderate_data, p_moderate))
    
    # Test Case 4: Extreme Impulse (Gambling Site)
    print_separator("Test Case 4: Extreme Impulse (Gambling Site)")
    
    extreme_data = {
        "heart_rate": 110.0,  # Very elevated
        "respiration_rate": 25.0,  # Very elevated
        "emotion_arousal": 0.95,  # Extreme arousal
        "click_rate": 8.0,  # Very rapid clicking
        "time_on_website": 30.0,  # Very short time
        "system_time": 2,  # 2 AM (late night)
        "scroll_velocity_peak": 150.0,  # Extreme scrolling
        "time_to_cart": 15.0,  # Very low TTC (15 seconds)
        "website_name": "casino.com"  # Gambling site (highest risk)
    }
    
    p_extreme = engine.calculate_p_impulse(extreme_data)
    intervention_extreme = engine.get_intervention_level(p_extreme)
    structured_extreme = engine.get_structured_output(extreme_data)
    
    print(f"Probability: {p_extreme:.3f}")
    print(f"Intervention Level: {intervention_extreme}")
    print("\nStructured Output:")
    print(json.dumps(structured_extreme, indent=2))
    print("\nValidation Logic:")
    print(engine.validate_logic(extreme_data, p_extreme))
    
    # Test Case 5: Edge Case - Missing Data
    print_separator("Test Case 5: Edge Case - Missing Data (Defaults Applied)")
    
    incomplete_data = {
        "heart_rate": 80.0,
        "respiration_rate": 18.0,
        # Missing emotion_arousal (defaults to 0.0)
        "click_rate": 2.0,
        "time_on_website": 150.0,
        "system_time": 12,
        "scroll_velocity_peak": 50.0,
        # Missing time_to_cart (defaults to inf)
        "website_name": "walmart.com"
    }
    
    p_incomplete = engine.calculate_p_impulse(incomplete_data)
    intervention_incomplete = engine.get_intervention_level(p_incomplete)
    
    print(f"Probability: {p_incomplete:.3f}")
    print(f"Intervention Level: {intervention_incomplete}")
    print("\nNote: Missing fields use default values (arousal=0.0, TTC=inf)")
    
    # Test Case 6: Intervention Level Thresholds
    print_separator("Test Case 6: Intervention Level Thresholds")
    
    test_scores = [0.15, 0.35, 0.55, 0.75, 0.90]
    print("Testing intervention level thresholds:")
    for score in test_scores:
        level = engine.get_intervention_level(score)
        print(f"  P={score:.2f} → {level}")
    
    # Summary
    print_separator("Summary")
    print("Test Cases Completed:")
    print("  ✓ Happy Excitement (Planned Purchase)")
    print("  ✓ Impulsive Stress (Late Night Flash Sale)")
    print("  ✓ Moderate Scenario (Normal Shopping)")
    print("  ✓ Extreme Impulse (Gambling Site)")
    print("  ✓ Edge Case (Missing Data)")
    print("  ✓ Intervention Level Thresholds")
    print("\nAll test cases demonstrate the engine's ability to:")
    print("  - Distinguish between happy excitement and impulsive stress")
    print("  - Apply contextual multipliers (time of day, website risk)")
    print("  - Handle missing data gracefully")
    print("  - Provide detailed reasoning for classifications")


if __name__ == "__main__":
    main()
