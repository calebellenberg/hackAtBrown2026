"""
Test script for Stop Shopping Extension with Inference Engine

This script loads JSON data from the Chrome extension and tests it with
the ImpulseInferenceEngine to get impulse buy probability scores.

Usage:
    1. Export your data from the browser console using api_test.js
    2. Save it as a JSON file (e.g., test_data.json)
    3. Run: python test_with_extension_data.py

Or use the sample data provided below for testing.
"""

import json
from inference_engine import ImpulseInferenceEngine


def load_extension_data(filepath: str) -> dict:
    """Load exported JSON data from the extension."""
    with open(filepath, 'r') as f:
        return json.load(f)


def convert_extension_data_to_engine_format(purchase_entry: dict, user_prefs: dict = None) -> dict:
    """
    Convert extension data format to inference engine input format.
    
    Args:
        purchase_entry: A single purchase attempt from the extension
        user_prefs: User preferences (budget, threshold, sensitivity)
    
    Returns:
        Dict formatted for ImpulseInferenceEngine.calculate()
    """
    # Map extension data to engine format
    engine_input = {
        # Behavioral signals from extension
        'scroll_velocity': purchase_entry.get('peakScrollVelocity', 0),
        'click_rate': purchase_entry.get('cartClickRate', 0),
        'time_to_cart': purchase_entry.get('timeToCart') or purchase_entry.get('timeOnSite', 60),
        
        # These would come from biometric sensors (use defaults for testing)
        'heart_rate': 75,  # Default resting heart rate
        'respiration_rate': 16,  # Default respiration
        'emotion_arousal': 0.5,  # Neutral arousal
        
        # Baselines (would normally come from user profile)
        'baseline_heart_rate': 70,
        'baseline_respiration': 14,
        'baseline_scroll_velocity': 500,
        'baseline_click_rate': 0.5,
        
        # Context
        'website_type': detect_website_type(purchase_entry.get('domain', '')),
        'time_of_day': extract_hour(purchase_entry.get('timestamp', '')),
        
        # User preferences if available
        'user_budget': user_prefs.get('budget', 500) if user_prefs else 500,
        'user_threshold': user_prefs.get('threshold', 100) if user_prefs else 100,
        'sensitivity': user_prefs.get('sensitivity', 'medium') if user_prefs else 'medium',
        
        # Product info
        'price': purchase_entry.get('priceValue', 0),
        'product_name': purchase_entry.get('productName', 'Unknown'),
        'action_type': purchase_entry.get('actionType', 'add_to_cart')
    }
    
    return engine_input


def detect_website_type(domain: str) -> str:
    """Detect website type from domain for risk factor."""
    domain = domain.lower()
    
    if 'amazon' in domain:
        return 'amazon'
    elif 'ebay' in domain:
        return 'ebay'
    elif 'aliexpress' in domain:
        return 'aliexpress'
    elif any(g in domain for g in ['draftkings', 'fanduel', 'bet365', 'casino']):
        return 'gambling'
    elif 'wish' in domain:
        return 'wish'
    else:
        return 'generic_ecommerce'


def extract_hour(timestamp: str) -> int:
    """Extract hour from ISO timestamp."""
    try:
        from datetime import datetime
        dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
        return dt.hour
    except:
        return 12  # Default to noon


def analyze_purchase_attempt(engine: ImpulseInferenceEngine, purchase: dict, user_prefs: dict = None) -> dict:
    """
    Analyze a single purchase attempt.
    
    Returns:
        Analysis result with impulse probability and recommendation
    """
    # Convert to engine format
    engine_input = convert_extension_data_to_engine_format(purchase, user_prefs)
    
    # Calculate impulse probability
    result = engine.calculate(
        heart_rate=engine_input['heart_rate'],
        respiration_rate=engine_input['respiration_rate'],
        scroll_velocity=engine_input['scroll_velocity'],
        emotion_arousal=engine_input['emotion_arousal'],
        click_rate=engine_input['click_rate'],
        time_to_cart=engine_input['time_to_cart'],
        website_type=engine_input['website_type'],
        time_of_day=engine_input['time_of_day'],
        baseline_heart_rate=engine_input['baseline_heart_rate'],
        baseline_respiration=engine_input['baseline_respiration'],
        baseline_scroll_velocity=engine_input['baseline_scroll_velocity'],
        baseline_click_rate=engine_input['baseline_click_rate']
    )
    
    # Add context from purchase
    result['product_name'] = engine_input['product_name']
    result['price'] = engine_input['price']
    result['action_type'] = engine_input['action_type']
    result['domain'] = purchase.get('domain', 'unknown')
    
    # Check against user budget/threshold
    if user_prefs:
        price = engine_input['price'] or 0
        threshold = user_prefs.get('threshold', 100)
        budget = user_prefs.get('budget', 500)
        
        result['exceeds_threshold'] = price >= threshold
        result['budget_impact'] = f"{(price / budget * 100):.1f}%" if budget > 0 else "N/A"
    
    return result


def test_with_sample_data():
    """Test the engine with sample extension data."""
    
    # Sample data in extension format
    sample_purchases = [
        {
            "id": "add_to_cart_1706745600000_abc123",
            "timestamp": "2026-01-31T14:30:00.000Z",
            "actionType": "add_to_cart",
            "domain": "amazon.com",
            "pageUrl": "https://www.amazon.com/dp/B09V3KXJPB",
            "productName": "Apple AirPods Pro (2nd Generation)",
            "priceRaw": "$249.00",
            "priceValue": 249.00,
            "timeToCart": 15.5,
            "timeOnSite": 45.2,
            "clickCount": 12,
            "cartClickCount": 1,
            "cartClickRate": 1.33,
            "peakScrollVelocity": 2500.0,
            "navigationPathLength": 3
        },
        {
            "id": "buy_now_1706745700000_def456",
            "timestamp": "2026-01-31T02:15:00.000Z",
            "actionType": "buy_now",
            "domain": "amazon.com",
            "pageUrl": "https://www.amazon.com/dp/B0CHX3PNKB",
            "productName": "Gaming Keyboard RGB Mechanical",
            "priceRaw": "$89.99",
            "priceValue": 89.99,
            "timeToCart": 8.2,
            "timeOnSite": 8.2,
            "clickCount": 5,
            "cartClickCount": 1,
            "cartClickRate": 7.32,
            "peakScrollVelocity": 4200.0,
            "navigationPathLength": 1
        },
        {
            "id": "add_to_cart_1706745800000_ghi789",
            "timestamp": "2026-01-31T10:00:00.000Z",
            "actionType": "add_to_cart",
            "domain": "bestbuy.com",
            "pageUrl": "https://www.bestbuy.com/site/samsung-tv",
            "productName": "Samsung 65\" OLED TV",
            "priceRaw": "$1,799.99",
            "priceValue": 1799.99,
            "timeToCart": 180.5,
            "timeOnSite": 600.0,
            "clickCount": 45,
            "cartClickCount": 2,
            "cartClickRate": 0.2,
            "peakScrollVelocity": 800.0,
            "navigationPathLength": 8
        }
    ]
    
    sample_prefs = {
        "budget": 500,
        "threshold": 100,
        "sensitivity": "medium"
    }
    
    # Initialize engine
    engine = ImpulseInferenceEngine()
    
    print("=" * 70)
    print("STOP SHOPPING - IMPULSE BUY ANALYSIS")
    print("=" * 70)
    print(f"\nUser Preferences:")
    print(f"  Monthly Budget: ${sample_prefs['budget']}")
    print(f"  Large Purchase Threshold: ${sample_prefs['threshold']}")
    print(f"  Sensitivity: {sample_prefs['sensitivity']}")
    print("\n" + "-" * 70)
    
    for i, purchase in enumerate(sample_purchases, 1):
        print(f"\n📦 PURCHASE ATTEMPT #{i}")
        print(f"   Product: {purchase['productName']}")
        print(f"   Price: {purchase['priceRaw']}")
        print(f"   Action: {purchase['actionType']}")
        print(f"   Domain: {purchase['domain']}")
        print(f"   Time to Cart: {purchase['timeToCart']:.1f}s")
        print(f"   Peak Scroll Velocity: {purchase['peakScrollVelocity']:.0f} px/s")
        
        result = analyze_purchase_attempt(engine, purchase, sample_prefs)
        
        print(f"\n   🎯 ANALYSIS RESULT:")
        print(f"   Impulse Probability: {result['impulse_probability']:.1%}")
        print(f"   Intervention Level: {result['intervention_level']}")
        print(f"   Confidence: {result.get('confidence', 'N/A')}")
        
        if 'exceeds_threshold' in result:
            print(f"   Exceeds Threshold: {'⚠️ YES' if result['exceeds_threshold'] else '✅ No'}")
            print(f"   Budget Impact: {result['budget_impact']}")
        
        print("-" * 70)
    
    print("\n✅ Analysis complete!")


def test_with_file(filepath: str):
    """Test with exported JSON file from extension."""
    
    data = load_extension_data(filepath)
    engine = ImpulseInferenceEngine()
    
    user_prefs = data.get('userPreferences')
    purchases = data.get('allPurchaseAttempts', [])
    
    if not purchases:
        print("No purchase attempts found in file.")
        return
    
    print(f"Loaded {len(purchases)} purchase attempts from {filepath}")
    
    for purchase in purchases:
        result = analyze_purchase_attempt(engine, purchase, user_prefs)
        print(f"\n{purchase['productName']} - {result['impulse_probability']:.1%} impulse probability")
        print(f"  Intervention: {result['intervention_level']}")


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        # Test with provided file
        test_with_file(sys.argv[1])
    else:
        # Test with sample data
        test_with_sample_data()
