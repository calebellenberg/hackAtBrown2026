#!/usr/bin/env python3
"""
Analyze shopping behavior data with Gemini AI.

This script reads extension data (exported from the Chrome extension) and sends it
to Google's Gemini API for AI-powered impulse buying analysis and recommendations.

Usage:
    # With a JSON file exported from the extension:
    python analyze_with_gemini.py ~/Downloads/extension_data.json
    
    # With sample data for testing:
    python analyze_with_gemini.py --sample

Prerequisites:
    - VERTEX_SERVICE_ACCOUNT_PATH must be set in backend/.env
    - Generative Language API must be enabled in Google Cloud
"""

import os
import sys
import json
import asyncio
from datetime import datetime

# Load environment variables
try:
    from dotenv import load_dotenv
    env_path = os.path.join(os.path.dirname(__file__), '.env')
    load_dotenv(dotenv_path=env_path)
except ImportError:
    print("❌ Error: python-dotenv not installed. Run: pip install python-dotenv")
    sys.exit(1)

try:
    from google.oauth2 import service_account
    import google.auth.transport.requests
except ImportError:
    print("❌ Error: google-auth not installed. Run: pip install google-auth")
    sys.exit(1)

try:
    import httpx
except ImportError:
    print("❌ Error: httpx not installed. Run: pip install httpx")
    sys.exit(1)


class GeminiAnalyzer:
    """Analyzes shopping data using Google's Gemini API."""
    
    VERTEX_AI_BASE = "https://generativelanguage.googleapis.com/v1beta"
    MODEL = "gemini-1.5-flash"
    
    def __init__(self):
        self.credentials = None
        self.access_token = None
        self._setup_credentials()
    
    def _setup_credentials(self):
        """Load service account credentials and get access token."""
        service_account_path = os.getenv("VERTEX_SERVICE_ACCOUNT_PATH")
        
        if not service_account_path:
            raise ValueError(
                "VERTEX_SERVICE_ACCOUNT_PATH not set in .env file.\n"
                "Please set it to the path of your service account JSON file."
            )
        
        # Resolve relative paths
        if not os.path.isabs(service_account_path):
            service_account_path = os.path.join(
                os.path.dirname(__file__),
                service_account_path
            )
        
        if not os.path.exists(service_account_path):
            raise FileNotFoundError(f"Service account file not found: {service_account_path}")
        
        # Load credentials
        self.credentials = service_account.Credentials.from_service_account_file(
            service_account_path,
            scopes=['https://www.googleapis.com/auth/generative-language']
        )
        
        # Get access token
        request = google.auth.transport.requests.Request()
        if not self.credentials.valid:
            self.credentials.refresh(request)
        self.access_token = self.credentials.token
    
    async def analyze_shopping_data(self, data: dict) -> dict:
        """
        Send shopping data to Gemini for analysis.
        
        Args:
            data: Dictionary containing shopping behavior data from the extension
            
        Returns:
            Dictionary with Gemini's analysis and recommendations
        """
        # Build the analysis prompt
        prompt = self._build_analysis_prompt(data)
        
        # Make request to Gemini
        url = f"{self.VERTEX_AI_BASE}/models/{self.MODEL}:generateContent"
        
        payload = {
            "contents": [{
                "parts": [{
                    "text": prompt
                }]
            }],
            "generationConfig": {
                "responseMimeType": "application/json",
                "temperature": 0.7
            }
        }
        
        headers = {
            'Authorization': f'Bearer {self.access_token}',
            'Content-Type': 'application/json'
        }
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            result = response.json()
        
        # Extract the response text
        if 'candidates' in result and len(result['candidates']) > 0:
            text = result['candidates'][0]['content']['parts'][0].get('text', '')
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return {"raw_response": text}
        
        return {"error": "No response from Gemini"}
    
    def _build_analysis_prompt(self, data: dict) -> str:
        """Build the prompt for Gemini analysis."""
        
        # Extract relevant data
        add_to_cart = data.get('add_to_cart_history', [])
        buy_now = data.get('buy_now_history', [])
        all_attempts = data.get('all_purchase_attempts', [])
        preferences = data.get('preferences', {})
        
        # Calculate summary stats
        total_attempts = len(all_attempts)
        total_value = sum(
            float(str(item.get('price', '0')).replace('$', '').replace(',', ''))
            for item in all_attempts
            if item.get('price')
        )
        
        prompt = f"""You are a behavioral finance AI assistant helping users understand and control their shopping impulses.

Analyze the following shopping behavior data from a browser extension that tracks "Add to Cart" and "Buy Now" clicks:

## User Preferences
- Budget: ${preferences.get('budget', 'Not set')}
- Impulse Threshold: ${preferences.get('threshold', 'Not set')}
- Sensitivity: {preferences.get('sensitivity', 'Not set')}

## Shopping Activity Summary
- Total purchase attempts: {total_attempts}
- Add to Cart clicks: {len(add_to_cart)}
- Buy Now clicks: {len(buy_now)}
- Total potential spending: ${total_value:.2f}

## Detailed Purchase Attempts
```json
{json.dumps(all_attempts[-20:], indent=2)}
```

## Analysis Request
Please analyze this shopping behavior and provide:

1. **Impulse Risk Assessment**: Rate the overall impulse buying risk (LOW, MEDIUM, HIGH, CRITICAL)
2. **Pattern Analysis**: Identify any concerning patterns (time of day, price ranges, product types, frequency)
3. **Behavioral Insights**: What does this data reveal about the user's shopping habits?
4. **Budget Analysis**: Compare spending patterns to the stated budget
5. **Specific Concerns**: Flag any particularly impulsive purchases
6. **Recommendations**: Provide 3-5 actionable recommendations to improve shopping discipline
7. **Intervention Suggestions**: Suggest what type of intervention would be most helpful for this user

Respond in this exact JSON format:
{{
    "risk_level": "LOW|MEDIUM|HIGH|CRITICAL",
    "risk_score": 0-100,
    "pattern_analysis": {{
        "peak_shopping_times": ["time1", "time2"],
        "average_price": 0.00,
        "most_common_sites": ["site1", "site2"],
        "concerning_patterns": ["pattern1", "pattern2"]
    }},
    "behavioral_insights": "string describing key insights",
    "budget_analysis": {{
        "total_attempted_spend": 0.00,
        "budget_remaining": 0.00,
        "over_budget": true/false,
        "percentage_of_budget": 0
    }},
    "flagged_purchases": [
        {{
            "product": "name",
            "price": 0.00,
            "reason": "why this is concerning"
        }}
    ],
    "recommendations": [
        "recommendation 1",
        "recommendation 2",
        "recommendation 3"
    ],
    "intervention_type": "NONE|GENTLE_REMINDER|COOL_DOWN|STRICT_BLOCK",
    "personalized_message": "A friendly, encouraging message for the user"
}}
"""
        return prompt


def load_extension_data(file_path: str) -> dict:
    """Load extension data from a JSON file."""
    with open(file_path, 'r') as f:
        return json.load(f)


def get_sample_data() -> dict:
    """Generate sample data for testing."""
    return {
        "preferences": {
            "budget": 500,
            "threshold": 50,
            "sensitivity": "medium"
        },
        "add_to_cart_history": [
            {
                "timestamp": "2026-01-31T10:30:00Z",
                "productName": "Apple AirPods Pro",
                "price": "$249.00",
                "url": "https://amazon.com/dp/B09JQMJHXY",
                "site": "amazon.com"
            },
            {
                "timestamp": "2026-01-31T11:15:00Z",
                "productName": "Mechanical Gaming Keyboard",
                "price": "$89.99",
                "url": "https://amazon.com/dp/B08K1234",
                "site": "amazon.com"
            }
        ],
        "buy_now_history": [
            {
                "timestamp": "2026-01-31T14:22:00Z",
                "productName": "Samsung 65\" 4K TV",
                "price": "$1,799.99",
                "url": "https://bestbuy.com/product/12345",
                "site": "bestbuy.com"
            }
        ],
        "all_purchase_attempts": [
            {
                "timestamp": "2026-01-31T10:30:00Z",
                "productName": "Apple AirPods Pro",
                "price": "$249.00",
                "url": "https://amazon.com/dp/B09JQMJHXY",
                "site": "amazon.com",
                "actionType": "add_to_cart"
            },
            {
                "timestamp": "2026-01-31T11:15:00Z",
                "productName": "Mechanical Gaming Keyboard",
                "price": "$89.99",
                "url": "https://amazon.com/dp/B08K1234",
                "site": "amazon.com",
                "actionType": "add_to_cart"
            },
            {
                "timestamp": "2026-01-31T14:22:00Z",
                "productName": "Samsung 65\" 4K TV",
                "price": "$1,799.99",
                "url": "https://bestbuy.com/product/12345",
                "site": "bestbuy.com",
                "actionType": "buy_now"
            },
            {
                "timestamp": "2026-01-31T15:45:00Z",
                "productName": "Designer Sneakers",
                "price": "$350.00",
                "url": "https://nike.com/product/abc",
                "site": "nike.com",
                "actionType": "add_to_cart"
            },
            {
                "timestamp": "2026-01-31T16:30:00Z",
                "productName": "Wireless Mouse",
                "price": "$29.99",
                "url": "https://amazon.com/dp/mouse123",
                "site": "amazon.com",
                "actionType": "add_to_cart"
            }
        ]
    }


async def main():
    """Main function to run the analysis."""
    print("=" * 80)
    print("🛒 STOP SHOPPING - Gemini AI Analysis")
    print("=" * 80)
    
    # Parse command line arguments
    if len(sys.argv) < 2:
        print("\nUsage:")
        print("  python analyze_with_gemini.py <path_to_json>")
        print("  python analyze_with_gemini.py --sample")
        print("\nExport data from Chrome extension console:")
        print("  1. Open DevTools on any shopping site")
        print("  2. Run: chrome.storage.local.get(null, d => console.log(JSON.stringify(d)))")
        print("  3. Copy the JSON and save to a file")
        sys.exit(1)
    
    # Load data
    if sys.argv[1] == '--sample':
        print("\n📦 Using sample data for testing...")
        data = get_sample_data()
    else:
        file_path = sys.argv[1]
        if not os.path.exists(file_path):
            print(f"❌ File not found: {file_path}")
            sys.exit(1)
        print(f"\n📂 Loading data from: {file_path}")
        data = load_extension_data(file_path)
    
    # Show data summary
    print("\n📊 Data Summary:")
    print(f"   Add to Cart clicks: {len(data.get('add_to_cart_history', []))}")
    print(f"   Buy Now clicks: {len(data.get('buy_now_history', []))}")
    print(f"   Total attempts: {len(data.get('all_purchase_attempts', []))}")
    
    # Initialize analyzer
    print("\n🔗 Connecting to Gemini API...")
    try:
        analyzer = GeminiAnalyzer()
        print("   ✓ Connected successfully")
    except Exception as e:
        print(f"   ❌ Failed to connect: {e}")
        sys.exit(1)
    
    # Run analysis
    print("\n🧠 Analyzing shopping behavior with Gemini AI...")
    try:
        result = await analyzer.analyze_shopping_data(data)
    except httpx.HTTPStatusError as e:
        print(f"   ❌ API Error: {e.response.status_code}")
        print(f"   {e.response.text}")
        sys.exit(1)
    except Exception as e:
        print(f"   ❌ Analysis failed: {e}")
        sys.exit(1)
    
    # Display results
    print("\n" + "=" * 80)
    print("📋 ANALYSIS RESULTS")
    print("=" * 80)
    
    if 'error' in result:
        print(f"❌ Error: {result['error']}")
        sys.exit(1)
    
    # Risk Assessment
    risk_level = result.get('risk_level', 'UNKNOWN')
    risk_score = result.get('risk_score', 0)
    risk_emoji = {'LOW': '🟢', 'MEDIUM': '🟡', 'HIGH': '🟠', 'CRITICAL': '🔴'}.get(risk_level, '⚪')
    
    print(f"\n{risk_emoji} IMPULSE RISK: {risk_level} ({risk_score}/100)")
    
    # Pattern Analysis
    patterns = result.get('pattern_analysis', {})
    if patterns:
        print("\n📈 PATTERN ANALYSIS:")
        if patterns.get('peak_shopping_times'):
            print(f"   Peak times: {', '.join(patterns['peak_shopping_times'])}")
        if patterns.get('average_price'):
            print(f"   Average price: ${patterns['average_price']:.2f}")
        if patterns.get('concerning_patterns'):
            print("   Concerning patterns:")
            for pattern in patterns['concerning_patterns']:
                print(f"     ⚠️  {pattern}")
    
    # Budget Analysis
    budget = result.get('budget_analysis', {})
    if budget:
        print("\n💰 BUDGET ANALYSIS:")
        print(f"   Total attempted spend: ${budget.get('total_attempted_spend', 0):.2f}")
        if budget.get('over_budget'):
            print(f"   ❌ OVER BUDGET by ${abs(budget.get('budget_remaining', 0)):.2f}")
        else:
            print(f"   ✓ Budget remaining: ${budget.get('budget_remaining', 0):.2f}")
    
    # Behavioral Insights
    insights = result.get('behavioral_insights', '')
    if insights:
        print(f"\n🔍 BEHAVIORAL INSIGHTS:")
        print(f"   {insights}")
    
    # Flagged Purchases
    flagged = result.get('flagged_purchases', [])
    if flagged:
        print("\n🚩 FLAGGED PURCHASES:")
        for item in flagged:
            print(f"   • {item.get('product', 'Unknown')} (${item.get('price', 0):.2f})")
            print(f"     Reason: {item.get('reason', 'N/A')}")
    
    # Recommendations
    recommendations = result.get('recommendations', [])
    if recommendations:
        print("\n💡 RECOMMENDATIONS:")
        for i, rec in enumerate(recommendations, 1):
            print(f"   {i}. {rec}")
    
    # Intervention
    intervention = result.get('intervention_type', 'NONE')
    intervention_emoji = {
        'NONE': '✅',
        'GENTLE_REMINDER': '💬',
        'COOL_DOWN': '⏸️',
        'STRICT_BLOCK': '🛑'
    }.get(intervention, '❓')
    print(f"\n{intervention_emoji} SUGGESTED INTERVENTION: {intervention}")
    
    # Personalized Message
    message = result.get('personalized_message', '')
    if message:
        print(f"\n💬 MESSAGE FOR YOU:")
        print(f"   \"{message}\"")
    
    print("\n" + "=" * 80)
    print("✅ Analysis complete!")
    print("=" * 80)
    
    # Save results to file
    output_file = os.path.join(os.path.dirname(__file__), 'analysis_result.json')
    with open(output_file, 'w') as f:
        json.dump(result, f, indent=2)
    print(f"\n📁 Full results saved to: {output_file}")


if __name__ == "__main__":
    asyncio.run(main())
