#!/usr/bin/env python3
"""
Simple test script to verify Vertex AI (Gemini) connectivity via service account.

This script tests the direct connection to Vertex AI using service account authentication.
It makes a simple generateContent request to verify the setup is working.

Prerequisites:
- VERTEX_SERVICE_ACCOUNT_PATH must be set in backend/.env
- Service account JSON file must exist and be valid
- Vertex AI API must be enabled in the Google Cloud project

Usage:
    cd backend
    source venv/bin/activate
    python test_vertex_ai.py
"""

import os
import json
import sys

# Check for required dependencies
try:
    from dotenv import load_dotenv
except ImportError:
    print("❌ Error: python-dotenv module not found.")
    print("\nPlease install dependencies:")
    print("  cd backend")
    print("  source venv/bin/activate")
    print("  pip install -r requirements.txt")
    print("\nOr run with the venv Python:")
    print("  ./venv/bin/python test_vertex_ai.py")
    sys.exit(1)

try:
    from google.oauth2 import service_account
    import google.auth.transport.requests
except ImportError:
    print("❌ Error: google-auth module not found.")
    print("\nPlease install dependencies:")
    print("  cd backend")
    print("  source venv/bin/activate")
    print("  pip install -r requirements.txt")
    sys.exit(1)

try:
    import httpx
except ImportError:
    print("❌ Error: httpx module not found.")
    print("\nPlease install dependencies:")
    print("  cd backend")
    print("  source venv/bin/activate")
    print("  pip install -r requirements.txt")
    sys.exit(1)

# Load environment variables
env_path = os.path.join(os.path.dirname(__file__), '.env')
load_dotenv(dotenv_path=env_path)

# Get service account path
SERVICE_ACCOUNT_PATH = os.getenv("VERTEX_SERVICE_ACCOUNT_PATH")

if not SERVICE_ACCOUNT_PATH:
    print("❌ Error: VERTEX_SERVICE_ACCOUNT_PATH not set in .env file")
    print("\nPlease set it in backend/.env:")
    print("  VERTEX_SERVICE_ACCOUNT_PATH=path/to/your/service-account-key.json")
    sys.exit(1)

# Resolve relative paths
if not os.path.isabs(SERVICE_ACCOUNT_PATH):
    SERVICE_ACCOUNT_PATH = os.path.join(
        os.path.dirname(__file__),
        SERVICE_ACCOUNT_PATH
    )

if not os.path.exists(SERVICE_ACCOUNT_PATH):
    print(f"❌ Error: Service account file not found: {SERVICE_ACCOUNT_PATH}")
    sys.exit(1)

print("=" * 80)
print("Vertex AI (Gemini) Connection Test")
print("=" * 80)
print(f"\nService Account Path: {SERVICE_ACCOUNT_PATH}")

# Load service account credentials
# Try multiple scopes - Generative Language API may need specific scope
try:
    print("\n1. Loading service account credentials...")
    # Try with Generative Language API scope first
    try:
        credentials = service_account.Credentials.from_service_account_file(
            SERVICE_ACCOUNT_PATH,
            scopes=['https://www.googleapis.com/auth/generative-language']
        )
        print("   ✓ Credentials loaded with generative-language scope")
    except:
        # Fallback to cloud-platform scope
        credentials = service_account.Credentials.from_service_account_file(
            SERVICE_ACCOUNT_PATH,
            scopes=['https://www.googleapis.com/auth/cloud-platform']
        )
        print("   ✓ Credentials loaded with cloud-platform scope")
except Exception as e:
    print(f"   ❌ Failed to load credentials: {e}")
    sys.exit(1)

# Get access token
try:
    print("\n2. Getting OAuth2 access token...")
    request = google.auth.transport.requests.Request()
    if not credentials.valid:
        credentials.refresh(request)
    access_token = credentials.token
    print(f"   ✓ Access token obtained")
    print(f"   Token (first 20 chars): {access_token[:20]}...")
except Exception as e:
    print(f"   ❌ Failed to get access token: {e}")
    sys.exit(1)

# Vertex AI base URL
VERTEX_AI_BASE = "https://generativelanguage.googleapis.com/v1beta"

# First, list available models
print("\n3. Listing available models...")
try:
    async def list_models():
        async with httpx.AsyncClient(timeout=30.0) as client:
            list_url = f"{VERTEX_AI_BASE}/models"
            headers = {
                'Authorization': f'Bearer {access_token}',
                'Content-Type': 'application/json'
            }
            response = await client.get(list_url, headers=headers)
            response.raise_for_status()
            return response.json()
    
    import asyncio
    models_result = asyncio.run(list_models())
    
    # Extract model names
    available_models = []
    if 'models' in models_result:
        for model in models_result['models']:
            model_name = model.get('name', '').replace('models/', '')
            if 'generateContent' in model.get('supportedGenerationMethods', []):
                available_models.append(model_name)
    
    if available_models:
        print(f"   ✓ Found {len(available_models)} available model(s):")
        for model in available_models[:5]:  # Show first 5
            print(f"     - {model}")
        if len(available_models) > 5:
            print(f"     ... and {len(available_models) - 5} more")
        
        # Try to use gemini-1.5-flash or gemini-pro, or use first available
        preferred_models = ['gemini-2.5-pro', 'gemini-1.5-flash', 'gemini-1.5-pro', 'gemini-pro', 'gemini-1.5-flash-latest']
        selected_model = None
        for pref in preferred_models:
            if pref in available_models:
                selected_model = pref
                break
        
        if not selected_model:
            selected_model = available_models[0]
        
        print(f"\n   Using model: {selected_model}")
    else:
        print("   ⚠️  No models found, using default: gemini-1.5-flash")
        selected_model = "gemini-1.5-flash"
        
except Exception as e:
    print(f"   ⚠️  Could not list models: {e}")
    print("   Using default model: gemini-1.5-flash")
    selected_model = "gemini-1.5-flash"

# Prepare request
print("\n4. Preparing Vertex AI request...")
VERTEX_AI_URL = f"{VERTEX_AI_BASE}/models/{selected_model}:generateContent"

payload = {
    "contents": [{
        "parts": [{
            "text": "list the capital city of eveyr country in asia. "
        }]
    }],
    "generationConfig": {
        "responseMimeType": "application/json"
    }
}

print(f"   Endpoint: {VERTEX_AI_URL}")
print(f"   Model: {selected_model}")

# Make request
print("\n5. Making request to Vertex AI...")
try:
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json'
    }
    
    async def make_request():
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                VERTEX_AI_URL,
                json=payload,
                headers=headers
            )
            response.raise_for_status()
            return response.json()
    
    import asyncio
    result = asyncio.run(make_request())
    
    print("   ✓ Request successful!")
    
    # Extract and display response
    print("\n6. Response from Vertex AI:")
    print("   " + "-" * 76)
    
    if 'candidates' in result and len(result['candidates']) > 0:
        candidate = result['candidates'][0]
        if 'content' in candidate and 'parts' in candidate['content']:
            text = candidate['content']['parts'][0].get('text', '')
            print(f"   Raw response: {text[:200]}...")
            
            # Try to parse JSON
            try:
                parsed = json.loads(text)
                print("\n   Parsed JSON:")
                print(json.dumps(parsed, indent=2))
            except json.JSONDecodeError:
                print(f"\n   Full text response:\n{text}")
    
    print("\n" + "=" * 80)
    print("✅ Vertex AI connection test PASSED!")
    print("=" * 80)
    
except httpx.HTTPStatusError as e:
    print(f"   ❌ HTTP Error: {e.response.status_code}")
    response_data = e.response.json() if e.response.headers.get('content-type', '').startswith('application/json') else {}
    
    if e.response.status_code == 403:
        error_info = response_data.get('error', {})
        if error_info.get('status') == 'PERMISSION_DENIED':
            details = error_info.get('details', [])
            for detail in details:
                if detail.get('@type') == 'type.googleapis.com/google.rpc.ErrorInfo':
                    if detail.get('reason') == 'SERVICE_DISABLED':
                        activation_url = detail.get('metadata', {}).get('activationUrl', '')
                        print(f"\n   ⚠️  Generative Language API is not enabled in your project.")
                        print(f"   Please enable it by visiting:")
                        print(f"   {activation_url}")
                        print(f"\n   Or enable it manually:")
                        print(f"   1. Go to https://console.cloud.google.com/apis/library")
                        print(f"   2. Search for 'Generative Language API'")
                        print(f"   3. Click 'Enable'")
                        print(f"   4. Wait a few minutes for the change to propagate")
                        sys.exit(1)
                    elif detail.get('reason') == 'ACCESS_TOKEN_SCOPE_INSUFFICIENT':
                        print(f"\n   ⚠️  Service account has insufficient permissions.")
                        print(f"   Please ensure the service account has 'Vertex AI User' role")
                        print(f"   or 'Generative Language API User' role in IAM.")
                        sys.exit(1)
    
    print(f"   Response: {e.response.text}")
    sys.exit(1)
except httpx.RequestError as e:
    print(f"   ❌ Request Error: {e}")
    sys.exit(1)
except Exception as e:
    print(f"   ❌ Unexpected error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
