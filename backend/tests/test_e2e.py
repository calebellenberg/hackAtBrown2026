"""
End-to-end integration tests simulating extension → backend flow.

Gemini API is mocked; everything else (Fast Brain, FastAPI routing,
Pydantic validation) runs for real.
"""

import os
import json
import asyncio
import tempfile
import shutil
import pytest
from unittest.mock import patch, Mock
from fastapi.testclient import TestClient

# ── Setup: mock credentials before app import ─────────────────────────

_temp_sa = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
json.dump(
    {
        "type": "service_account",
        "project_id": "e2e-project",
        "private_key_id": "k",
        "private_key": "-----BEGIN PRIVATE KEY-----\nMOCK\n-----END PRIVATE KEY-----\n",
        "client_email": "e2e@e2e.iam.gserviceaccount.com",
        "client_id": "1",
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
        "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/e2e",
    },
    _temp_sa,
)
_temp_sa.close()

os.environ["VERTEX_SERVICE_ACCOUNT_PATH"] = _temp_sa.name

_mock_creds = Mock()
_mock_creds.valid = True
_mock_creds.token = "mock_token"
_patcher = patch("google.oauth2.service_account.Credentials.from_service_account_file")
_mock_fn = _patcher.start()
_mock_fn.return_value = _mock_creds

from app import app  # noqa: E402


@pytest.fixture
def client():
    return TestClient(app)


# ── Helpers ────────────────────────────────────────────────────────────

def _pipeline_request(**overrides):
    """Build a valid /pipeline-analyze request body with sensible defaults."""
    base = {
        "product": "Test Widget",
        "cost": 49.99,
        "website": "amazon.com",
        "time_to_cart": 20.0,
        "time_on_site": 90.0,
        "click_count": 6,
        "peak_scroll_velocity": 800.0,
        "system_hour": 14,
    }
    base.update(overrides)
    return base


# ── Tests ──────────────────────────────────────────────────────────────

def test_full_pipeline_realistic_telemetry(client):
    """Realistic telemetry → valid response matching content.js expectations."""
    from app import memory_engine
    original = memory_engine.analyze_purchase

    async def mock_analyze(p_impulse_fast, purchase_data):
        return {
            "impulse_score": 0.55,
            "confidence": 0.75,
            "reasoning": "Mock slow brain: moderate impulse detected.",
            "intervention_action": "MIRROR",
            "memory_update": None,
        }

    memory_engine.analyze_purchase = mock_analyze
    try:
        resp = client.post("/pipeline-analyze", json=_pipeline_request())
        assert resp.status_code == 200
        data = resp.json()
        # Keys that content.js / tracker.js destructure
        for key in (
            "p_impulse_fast",
            "fast_brain_intervention",
            "fast_brain_dominant_trigger",
            "impulse_score",
            "confidence",
            "reasoning",
            "intervention_action",
            "memory_update",
        ):
            assert key in data, f"Missing key expected by extension: {key}"
    finally:
        memory_engine.analyze_purchase = original


def test_preferences_sync_analyze_reset_cycle(client):
    """Full lifecycle: preferences → sync → analyze → reset."""
    import app as app_module

    os.makedirs(app_module.MEMORY_DIR, exist_ok=True)
    for fname in ["Goals.md", "Budget.md", "State.md", "Behavior.md"]:
        with open(os.path.join(app_module.MEMORY_DIR, fname), "w") as f:
            f.write(f"# {fname}\nplaceholder\n")

    from app import memory_engine
    orig_analyze = memory_engine.analyze_purchase
    orig_reindex = memory_engine.reindex_memory

    async def mock_analyze(*a, **kw):
        return {
            "impulse_score": 0.4,
            "confidence": 0.7,
            "reasoning": "ok",
            "intervention_action": "MIRROR",
            "memory_update": None,
        }

    async def mock_reindex():
        return True

    memory_engine.analyze_purchase = mock_analyze
    memory_engine.reindex_memory = mock_reindex

    try:
        # 1. Update preferences
        resp = client.post(
            "/update-preferences",
            json={"budget": 200, "threshold": 40, "sensitivity": "high"},
        )
        assert resp.status_code == 200
        assert resp.json()["budget_updated"]

        # 2. Sync memory
        resp = client.post("/sync-memory", json={})
        assert resp.status_code == 200

        # 3. Analyze
        resp = client.post("/pipeline-analyze", json=_pipeline_request())
        assert resp.status_code == 200
        assert resp.json()["intervention_action"] in {"NONE", "MIRROR", "COOLDOWN", "PHRASE"}

        # 4. Reset
        resp = client.post("/reset-memory", json={})
        assert resp.status_code == 200
        assert resp.json()["files_reset"] == 4
    finally:
        memory_engine.analyze_purchase = orig_analyze
        memory_engine.reindex_memory = orig_reindex


def test_high_impulse_scenario(client):
    """Late-night fast cart on gambling site → high score, COOLDOWN+."""
    from app import memory_engine
    orig = memory_engine.analyze_purchase

    async def mock_analyze(p_impulse_fast, purchase_data):
        # Slow brain amplifies Fast Brain's high score
        return {
            "impulse_score": min(p_impulse_fast + 0.15, 1.0),
            "confidence": 0.9,
            "reasoning": "High risk: late night gambling.",
            "intervention_action": "PHRASE" if p_impulse_fast > 0.7 else "COOLDOWN",
            "memory_update": None,
        }

    memory_engine.analyze_purchase = mock_analyze
    try:
        resp = client.post(
            "/pipeline-analyze",
            json=_pipeline_request(
                website="online-casino.com",
                time_to_cart=3.0,
                system_hour=3,
                peak_scroll_velocity=15000.0,
                cost=500.0,
            ),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["p_impulse_fast"] > 0.5, f"Expected >0.5, got {data['p_impulse_fast']}"
        assert data["fast_brain_intervention"] in ("COOLDOWN", "PHRASE")
    finally:
        memory_engine.analyze_purchase = orig


def test_low_impulse_scenario(client):
    """Midday slow cart on bestbuy → low score, NONE."""
    from app import memory_engine
    orig = memory_engine.analyze_purchase

    async def mock_analyze(p_impulse_fast, purchase_data):
        return {
            "impulse_score": p_impulse_fast,
            "confidence": 0.8,
            "reasoning": "Low risk: planned purchase.",
            "intervention_action": "NONE",
            "memory_update": None,
        }

    memory_engine.analyze_purchase = mock_analyze
    try:
        resp = client.post(
            "/pipeline-analyze",
            json=_pipeline_request(
                website="bestbuy.com",
                time_to_cart=600.0,
                time_on_site=900.0,
                system_hour=12,
                peak_scroll_velocity=200.0,
                cost=25.0,
            ),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["p_impulse_fast"] < 0.3, f"Expected <0.3, got {data['p_impulse_fast']}"
        assert data["fast_brain_intervention"] == "NONE"
    finally:
        memory_engine.analyze_purchase = orig


def test_concurrent_requests(client):
    """5 concurrent requests should all return valid responses."""
    from app import memory_engine
    orig = memory_engine.analyze_purchase

    async def mock_analyze(p_impulse_fast, purchase_data):
        return {
            "impulse_score": p_impulse_fast,
            "confidence": 0.7,
            "reasoning": "concurrent test",
            "intervention_action": "MIRROR",
            "memory_update": None,
        }

    memory_engine.analyze_purchase = mock_analyze

    import concurrent.futures

    try:
        def send_request(i):
            return client.post(
                "/pipeline-analyze",
                json=_pipeline_request(product=f"Item_{i}"),
            )

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
            futures = [pool.submit(send_request, i) for i in range(5)]
            results = [f.result() for f in futures]

        for resp in results:
            assert resp.status_code == 200
            data = resp.json()
            assert 0.0 <= data["p_impulse_fast"] <= 1.0
            assert data["intervention_action"] in {"NONE", "MIRROR", "COOLDOWN", "PHRASE"}
    finally:
        memory_engine.analyze_purchase = orig
