"""
Integration tests for FastAPI endpoints.
"""

import os
import json
import pytest
import tempfile
import shutil
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock, Mock

# Create a mock service account file before importing app
_temp_service_account = tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False)
service_account_data = {
    "type": "service_account",
    "project_id": "test-project",
    "private_key_id": "test-key-id",
    "private_key": "-----BEGIN PRIVATE KEY-----\nMOCK_KEY\n-----END PRIVATE KEY-----\n",
    "client_email": "test@test-project.iam.gserviceaccount.com",
    "client_id": "123456789",
    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
    "token_uri": "https://oauth2.googleapis.com/token",
    "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
    "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/test%40test-project.iam.gserviceaccount.com"
}
json.dump(service_account_data, _temp_service_account)
_temp_service_account.close()
_mock_service_account_path = _temp_service_account.name

# Set environment variable before importing app
os.environ["VERTEX_SERVICE_ACCOUNT_PATH"] = _mock_service_account_path

# Mock service account authentication before importing app
# Use patch.object to ensure the mock persists
_mock_credentials = Mock()
_mock_credentials.valid = True
_mock_credentials.token = "mock_access_token"

# Patch before import
_patcher = patch('google.oauth2.service_account.Credentials.from_service_account_file')
_mock_creds_func = _patcher.start()
_mock_creds_func.return_value = _mock_credentials

from app import app


@pytest.fixture
def temp_dirs():
    """Create temporary directories for testing."""
    memory_dir = tempfile.mkdtemp()
    chroma_dir = tempfile.mkdtemp()
    yield memory_dir, chroma_dir
    shutil.rmtree(memory_dir, ignore_errors=True)
    shutil.rmtree(chroma_dir, ignore_errors=True)


@pytest.fixture
def sample_markdown_files(temp_dirs):
    """Create sample Markdown files for testing."""
    memory_dir, _ = temp_dirs
    
    # Create all required files
    for filename in ["Goals.md", "Budget.md", "State.md", "Behavior.md"]:
        with open(os.path.join(memory_dir, filename), "w") as f:
            f.write(f"# {filename.replace('.md', '')}\n\nInitial content\n")
    
    return memory_dir


@pytest.fixture
def mock_env_vars(monkeypatch):
    """Mock environment variables."""
    monkeypatch.setenv("VERTEX_SERVICE_ACCOUNT_PATH", _mock_service_account_path)
    
    # Mock service account authentication
    with patch('google.oauth2.service_account.Credentials.from_service_account_file') as mock_creds:
        mock_credentials = Mock()
        mock_credentials.valid = True
        mock_credentials.token = "mock_access_token"
        mock_creds.return_value = mock_credentials
        yield


@pytest.fixture
def client(temp_dirs, sample_markdown_files, mock_env_vars):
    """Create test client."""
    client = TestClient(app)
    yield client


def test_root_endpoint(client):
    """Test root endpoint."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert "message" in data
    assert "endpoints" in data


def test_health_check(client):
    """Test health check endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data


def test_analyze_endpoint_valid_request(client):
    """Test /analyze endpoint with valid request."""
    request_data = {
        "p_impulse_fast": 0.75,
        "product": "Wireless Headphones",
        "cost": 129.99,
        "website": "amazon.com"
    }
    
    # Mock the memory engine's analyze_purchase method
    from app import memory_engine
    original_method = memory_engine.analyze_purchase
    
    async def mock_analyze(*args, **kwargs):
        return {
            "impulse_score": 0.68,
            "confidence": 0.85,
            "reasoning": "Test reasoning",
            "intervention_action": "COOLDOWN",
            "memory_update": "User is willing to spend $60 on quality apparel"
        }
    
    memory_engine.analyze_purchase = mock_analyze
    
    try:
        response = client.post("/analyze", json=request_data)
        
        assert response.status_code == 200
        data = response.json()
        assert "impulse_score" in data
        assert "confidence" in data
        assert "reasoning" in data
        assert "intervention_action" in data
        assert "memory_update" in data
        assert data["impulse_score"] == 0.68
        assert data["memory_update"] == "User is willing to spend $60 on quality apparel"
    finally:
        memory_engine.analyze_purchase = original_method


def test_analyze_endpoint_invalid_request(client):
    """Test /analyze endpoint with invalid request."""
    # Missing required fields
    request_data = {
        "p_impulse_fast": 0.75
        # Missing product, cost, website
    }
    
    response = client.post("/analyze", json=request_data)
    assert response.status_code == 422  # Validation error


def test_analyze_endpoint_invalid_score(client):
    """Test /analyze endpoint with invalid score."""
    request_data = {
        "p_impulse_fast": 1.5,  # Invalid: > 1.0
        "product": "Test",
        "cost": 10.0,
        "website": "test.com"
    }
    
    response = client.post("/analyze", json=request_data)
    assert response.status_code == 422  # Validation error


def test_analyze_endpoint_fallback_on_error(client):
    """Test /analyze endpoint fallback when Vertex AI fails."""
    request_data = {
        "p_impulse_fast": 0.75,
        "product": "Test Product",
        "cost": 50.0,
        "website": "test.com"
    }
    
    # Mock API failure
    from app import memory_engine
    original_method = memory_engine.analyze_purchase
    
    async def mock_analyze(*args, **kwargs):
        raise Exception("API Error")
    
    memory_engine.analyze_purchase = mock_analyze
    
    try:
        response = client.post("/analyze", json=request_data)
        
        # Should still return 200 with fallback
        assert response.status_code == 200
        data = response.json()
        assert data["impulse_score"] == 0.75  # Falls back to Fast Brain score
        assert data["confidence"] == 0.3  # Low confidence
        assert "Fast Brain" in data["reasoning"]
        assert data["memory_update"] is None  # No memory update on fallback
    finally:
        memory_engine.analyze_purchase = original_method


def test_analyze_endpoint_no_memory_update(client):
    """Test /analyze endpoint when no memory update is needed."""
    request_data = {
        "p_impulse_fast": 0.5,
        "product": "Test Product",
        "cost": 10.0,
        "website": "test.com"
    }
    
    from app import memory_engine
    original_method = memory_engine.analyze_purchase
    
    async def mock_analyze(*args, **kwargs):
        return {
            "impulse_score": 0.5,
            "confidence": 0.8,
            "reasoning": "No update needed",
            "intervention_action": "NONE",
            "memory_update": None
        }
    
    memory_engine.analyze_purchase = mock_analyze
    
    try:
        response = client.post("/analyze", json=request_data)
        
        assert response.status_code == 200
        data = response.json()
        assert data["memory_update"] is None
    finally:
        memory_engine.analyze_purchase = original_method


def test_sync_memory_endpoint(client):
    """Test /sync-memory endpoint."""
    from app import memory_engine
    original_method = memory_engine.reindex_memory
    
    async def mock_reindex(*args, **kwargs):
        return True
    
    memory_engine.reindex_memory = mock_reindex
    
    try:
        response = client.post("/sync-memory", json={})
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "files_indexed" in data
        assert data["files_indexed"] >= 0
    finally:
        memory_engine.reindex_memory = original_method


def test_sync_memory_endpoint_failure(client):
    """Test /sync-memory endpoint with failure."""
    from app import memory_engine
    original_method = memory_engine.reindex_memory
    
    async def mock_reindex(*args, **kwargs):
        return False
    
    memory_engine.reindex_memory = mock_reindex
    
    try:
        response = client.post("/sync-memory", json={})
        
        assert response.status_code == 500
    finally:
        memory_engine.reindex_memory = original_method


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
