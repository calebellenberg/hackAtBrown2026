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


# ===================== /pipeline-analyze tests =====================


def test_pipeline_analyze_valid_request(client):
    """Test /pipeline-analyze with mocked Slow Brain."""
    from app import memory_engine
    original_method = memory_engine.analyze_purchase

    async def mock_analyze(*args, **kwargs):
        return {
            "impulse_score": 0.45,
            "confidence": 0.8,
            "reasoning": "Mock slow brain reasoning",
            "intervention_action": "MIRROR",
            "memory_update": None,
        }

    memory_engine.analyze_purchase = mock_analyze

    try:
        request_data = {
            "product": "Wireless Headphones",
            "cost": 79.99,
            "website": "amazon.com",
            "time_to_cart": 12.5,
            "time_on_site": 45.0,
            "click_count": 8,
            "peak_scroll_velocity": 1200.0,
            "system_hour": 14,
        }
        response = client.post("/pipeline-analyze", json=request_data)
        assert response.status_code == 200
        data = response.json()
        # Verify all PipelineResponse fields
        assert "p_impulse_fast" in data
        assert "fast_brain_intervention" in data
        assert "fast_brain_dominant_trigger" in data
        assert "impulse_score" in data
        assert "confidence" in data
        assert "reasoning" in data
        assert "intervention_action" in data
        assert "memory_update" in data
        assert 0.0 <= data["p_impulse_fast"] <= 1.0
        assert data["intervention_action"] in ("NONE", "MIRROR", "COOLDOWN", "PHRASE")
    finally:
        memory_engine.analyze_purchase = original_method


def test_pipeline_analyze_missing_fields(client):
    """Missing required fields should return 422."""
    request_data = {"product": "Test"}  # missing cost, website, etc.
    response = client.post("/pipeline-analyze", json=request_data)
    assert response.status_code == 422


def test_pipeline_analyze_slow_brain_error_fallback(client):
    """When Slow Brain errors, pipeline should fall back to Fast Brain score."""
    from app import memory_engine
    original_method = memory_engine.analyze_purchase

    async def mock_analyze(*args, **kwargs):
        raise RuntimeError("Slow Brain is down")

    memory_engine.analyze_purchase = mock_analyze

    try:
        request_data = {
            "product": "Widget",
            "cost": 25.0,
            "website": "bestbuy.com",
            "time_to_cart": 30.0,
            "time_on_site": 120.0,
            "click_count": 5,
            "peak_scroll_velocity": 500.0,
            "system_hour": 10,
        }
        response = client.post("/pipeline-analyze", json=request_data)
        assert response.status_code == 200
        data = response.json()
        # Should use Fast Brain score directly
        assert data["impulse_score"] == data["p_impulse_fast"]
        assert "Fast Brain" in data["reasoning"]
    finally:
        memory_engine.analyze_purchase = original_method


def test_pipeline_analyze_error_fallback_uses_mirror(client):
    """Complete error fallback should use MIRROR (not stale NUDGE)."""
    from app import fast_brain
    import app as app_module

    # Force a complete failure by temporarily breaking fast_brain
    original_fast_brain = app_module.fast_brain
    app_module.fast_brain = None  # This alone won't cause the outer except
    # Instead, mock calculate_p_impulse to raise
    original_calc = original_fast_brain.calculate_p_impulse
    original_fast_brain.calculate_p_impulse = lambda *a, **kw: (_ for _ in ()).throw(
        RuntimeError("Total failure")
    )
    app_module.fast_brain = original_fast_brain

    try:
        request_data = {
            "product": "Gadget",
            "cost": 50.0,
            "website": "test.com",
            "time_to_cart": 10.0,
            "time_on_site": 60.0,
            "click_count": 3,
            "peak_scroll_velocity": 200.0,
            "system_hour": 12,
        }
        response = client.post("/pipeline-analyze", json=request_data)
        assert response.status_code == 200
        data = response.json()
        # fast_brain_intervention must NOT be the stale "NUDGE"
        assert data["fast_brain_intervention"] == "MIRROR"
        assert data["intervention_action"] == "MIRROR"
    finally:
        original_fast_brain.calculate_p_impulse = original_calc
        app_module.fast_brain = original_fast_brain


def test_pipeline_analyze_intervention_names_valid(client):
    """All intervention names in the response must be from the allowed set."""
    from app import memory_engine
    original_method = memory_engine.analyze_purchase

    async def mock_analyze(*args, **kwargs):
        return {
            "impulse_score": 0.7,
            "confidence": 0.9,
            "reasoning": "Test",
            "intervention_action": "COOLDOWN",
            "memory_update": None,
        }

    memory_engine.analyze_purchase = mock_analyze

    try:
        request_data = {
            "product": "Laptop",
            "cost": 999.0,
            "website": "amazon.com",
            "time_to_cart": 5.0,
            "time_on_site": 30.0,
            "click_count": 2,
            "peak_scroll_velocity": 3000.0,
            "system_hour": 2,
        }
        response = client.post("/pipeline-analyze", json=request_data)
        assert response.status_code == 200
        data = response.json()
        valid_names = {"NONE", "MIRROR", "COOLDOWN", "PHRASE"}
        assert data["fast_brain_intervention"] in valid_names
        assert data["intervention_action"] in valid_names
    finally:
        memory_engine.analyze_purchase = original_method


# ===================== /update-preferences tests =====================


def test_update_preferences_valid(client):
    """Valid budget/threshold/sensitivity should succeed."""
    import app as app_module

    # Ensure MEMORY_DIR has Budget.md
    budget_path = os.path.join(app_module.MEMORY_DIR, "Budget.md")
    os.makedirs(app_module.MEMORY_DIR, exist_ok=True)
    with open(budget_path, "w") as f:
        f.write("# Budget\nplaceholder\n")

    request_data = {
        "budget": 300.0,
        "threshold": 50.0,
        "sensitivity": "high",
    }
    response = client.post("/update-preferences", json=request_data)
    assert response.status_code == 200
    data = response.json()
    assert data["budget_updated"] is True
    assert data["status"] == "success"


def test_update_preferences_with_goals(client):
    """Financial goals with mocked Gemini should mark goals_updated."""
    import app as app_module

    budget_path = os.path.join(app_module.MEMORY_DIR, "Budget.md")
    goals_path = os.path.join(app_module.MEMORY_DIR, "Goals.md")
    os.makedirs(app_module.MEMORY_DIR, exist_ok=True)
    with open(budget_path, "w") as f:
        f.write("# Budget\nplaceholder\n")
    with open(goals_path, "w") as f:
        f.write("# Long-term Goals\n\n## Financial Goals\n- placeholder\n")

    # Mock the Gemini call that processes financial goals
    from app import memory_engine
    original_call = memory_engine._call_gemini_api

    async def mock_gemini_call(*args, **kwargs):
        return {"Goals.md": "## Financial Goals\n- Save $1000 by December"}

    memory_engine._call_gemini_api = mock_gemini_call

    try:
        request_data = {
            "budget": 500.0,
            "threshold": 100.0,
            "sensitivity": "medium",
            "financial_goals": "I want to save $1000 by December for vacation.",
        }
        response = client.post("/update-preferences", json=request_data)
        assert response.status_code == 200
        data = response.json()
        assert data["budget_updated"] is True
        assert data["goals_updated"] is True
    finally:
        memory_engine._call_gemini_api = original_call


def test_update_preferences_negative_budget(client):
    """Negative budget should fail validation."""
    request_data = {
        "budget": -100.0,
        "threshold": 50.0,
        "sensitivity": "medium",
    }
    response = client.post("/update-preferences", json=request_data)
    assert response.status_code == 422


# ===================== /reset-memory tests =====================


def test_reset_memory_success(client):
    """Reset should return files_reset=4 and write template content."""
    import app as app_module

    os.makedirs(app_module.MEMORY_DIR, exist_ok=True)
    # Write some non-template content
    for fname in ["Goals.md", "Budget.md", "State.md", "Behavior.md"]:
        with open(os.path.join(app_module.MEMORY_DIR, fname), "w") as f:
            f.write("dirty content that should be overwritten\n")

    # Mock reindex so we don't hit ChromaDB
    from app import memory_engine
    original_reindex = memory_engine.reindex_memory

    async def mock_reindex():
        return True

    memory_engine.reindex_memory = mock_reindex

    try:
        response = client.post("/reset-memory", json={})
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["files_reset"] == 4
    finally:
        memory_engine.reindex_memory = original_reindex


def test_reset_memory_files_contain_template(client):
    """After reset, files should contain their template markers."""
    import app as app_module

    os.makedirs(app_module.MEMORY_DIR, exist_ok=True)
    for fname in ["Goals.md", "Budget.md", "State.md", "Behavior.md"]:
        with open(os.path.join(app_module.MEMORY_DIR, fname), "w") as f:
            f.write("dirty\n")

    from app import memory_engine
    original_reindex = memory_engine.reindex_memory

    async def mock_reindex():
        return True

    memory_engine.reindex_memory = mock_reindex

    try:
        client.post("/reset-memory", json={})

        # Verify template structure
        goals = open(os.path.join(app_module.MEMORY_DIR, "Goals.md")).read()
        assert "Financial Goals" in goals

        budget = open(os.path.join(app_module.MEMORY_DIR, "Budget.md")).read()
        assert "Monthly Spending Limits" in budget
    finally:
        memory_engine.reindex_memory = original_reindex


# ===================== /consolidate-memory tests =====================


def test_consolidate_memory_no_engine(client):
    """When memory_engine is None, should return status='error'."""
    import app as app_module

    original_engine = app_module.memory_engine
    app_module.memory_engine = None

    try:
        response = client.post("/consolidate-memory", json={})
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "error"
    finally:
        app_module.memory_engine = original_engine


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
