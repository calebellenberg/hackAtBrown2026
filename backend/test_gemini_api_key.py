#!/usr/bin/env python3
"""
Test script for Gemini API using service account authentication.

This script tests the connection to Google's Gemini API via Vertex AI Platform
using OAuth2 authentication with a service account.

Prerequisites:
    - Service account JSON file (key.json in this directory)

Usage:
    python test_gemini_api_key.py
"""

import os
import sys
import json

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


# Vertex AI configuration
PROJECT_ID = "vertex-key-test"
LOCATION = "us-central1"
MODEL = "gemini-2.5-pro"

# Service account file path (relative to this script)
SERVICE_ACCOUNT_FILE = os.path.join(os.path.dirname(__file__), "key.json")


def get_access_token():
    """Get OAuth2 access token using service account credentials."""
    try:
        if not os.path.exists(SERVICE_ACCOUNT_FILE):
            print(f"❌ Error: Service account file not found: {SERVICE_ACCOUNT_FILE}")
            return None
        
        credentials = service_account.Credentials.from_service_account_file(
            SERVICE_ACCOUNT_FILE,
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        credentials.refresh(google.auth.transport.requests.Request())
        return credentials.token
    except Exception as e:
        print(f"❌ Error getting credentials: {e}")
        return None


def test_gemini_api(token: str):
    """
    Test the Gemini API with a simple request.
    
    Args:
        token: OAuth2 access token
    """
    print("=" * 60)
    print("Testing Gemini API with Vertex AI Platform (OAuth2)")
    print("=" * 60)
    
    # Build the API URL
    url = (
        f"https://aiplatform.googleapis.com/v1/projects/{PROJECT_ID}/"
        f"locations/{LOCATION}/publishers/google/models/"
        f"{MODEL}:generateContent"
    )
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    
    # Simple test request
    request_body = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {
                        "text": "Write a detailed 1500-word academic-style analysis of the economic systems of Japan, China, and India, including historical context, policy mechanisms, labor markets, industrial strategy, and future challenges."
                    }
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.7,
            "maxOutputTokens": 2048
        }
    }
    
    print(f"\n📡 Making request to Vertex AI Platform...")
    print(f"   Project: {PROJECT_ID}")
    print(f"   Location: {LOCATION}")
    print(f"   Model: {MODEL}")
    
    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.post(url, headers=headers, json=request_body)
            
            print(f"\n📬 Response Status: {response.status_code}")
            
            if response.status_code == 200:
                result = response.json()
                
                # Handle response
                if "candidates" in result and len(result["candidates"]) > 0:
                    candidate = result["candidates"][0]
                    if "content" in candidate and "parts" in candidate["content"]:
                        full_text = ""
                        for part in candidate["content"]["parts"]:
                            full_text += part.get("text", "")
                        
                        print(f"\n✅ SUCCESS! Gemini responded:")
                        print("-" * 40)
                        print(full_text)
                        print("-" * 40)
                        
                        # Print usage statistics if available
                        if "usageMetadata" in result:
                            usage = result["usageMetadata"]
                            print(f"\n📊 Token Usage:")
                            print(f"   Prompt tokens: {usage.get('promptTokenCount', 'N/A')}")
                            print(f"   Response tokens: {usage.get('candidatesTokenCount', 'N/A')}")
                            print(f"   Total tokens: {usage.get('totalTokenCount', 'N/A')}")
                        
                        return True
                    else:
                        print("⚠️  Unexpected response structure (no content/parts)")
                        print(json.dumps(result, indent=2))
                else:
                    print("⚠️  Unexpected response structure (no candidates)")
                    print(json.dumps(result, indent=2))
                    
            elif response.status_code == 400:
                error = response.json()
                print(f"\n❌ Bad Request Error:")
                print(json.dumps(error, indent=2))
                
            elif response.status_code == 401 or response.status_code == 403:
                print(f"\n❌ Authentication Error:")
                print("   Your credentials may be invalid or don't have access.")
                print("   Try: gcloud auth application-default login")
                error = response.json()
                print(json.dumps(error, indent=2))
                
            elif response.status_code == 429:
                print(f"\n❌ Rate Limit Error:")
                print("   Too many requests. Please wait and try again.")
                error = response.json()
                print(json.dumps(error, indent=2))
                
            else:
                print(f"\n❌ Error Response:")
                try:
                    error = response.json()
                    print(json.dumps(error, indent=2))
                except:
                    print(response.text)
                    
    except httpx.TimeoutException:
        print("\n❌ Request timed out. Please check your internet connection.")
        return False
    except httpx.RequestError as e:
        print(f"\n❌ Request error: {e}")
        return False
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        return False
    
    return False


def main():
    """Main entry point."""
    print("\n🔑 Gemini API Test (Vertex AI Platform)")
    print("=" * 60)
    
    # Get access token
    print("\n🔐 Getting OAuth2 access token...")
    token = get_access_token()
    
    if not token:
        sys.exit(1)
    
    print("   ✅ Token acquired successfully")
    
    # Run test
    success = test_gemini_api(token)
    
    # Summary
    print("\n" + "=" * 60)
    if success:
        print("✅ All tests passed! Vertex AI connection is working correctly.")
    else:
        print("❌ Some tests failed. Please check the errors above.")
    print("=" * 60 + "\n")
    
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
