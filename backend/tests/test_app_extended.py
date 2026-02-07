"""
Extended unit and integration tests for app.py edge cases.

Covers: PipelineRequest boundary values, /gemini-analyze, build_gemini_prompt,
/update-preferences edge cases, /reset-memory, /health, /consolidate-memory,
and time_to_cart=null fallback behavior.
"""

import os
import json
import pytest
from unittest.mock import patch, Mock, AsyncMock
from fastapi.testclient import TestClient

from app import app, build_gemini_prompt, PurchaseAttempt, GeminiAnalyzeRequest


@pytest.fixture
def client():
    return TestClient(app)


def _mock_slow_brain(impulse_score=0.5, intervention="NONE"):
    """Helper to create a standard mock for memory_engine.analyze_purchase."""
    from app import memory_engine

    orig = memory_engine.analyze_purchase

    async def mock_analyze(p_impulse_fast, purchase_data):
        return {
            "impulse_score": impulse_score,
            "confidence": 0.7,
            "reasoning": "Mock reasoning",
            "intervention_action": intervention,
            "memory_update": None,
        }

    return orig, mock_analyze


# ── PipelineRequest boundary values ─────────────────────────────────────

class TestPipelineBoundaryValues:
    def test_system_hour_zero(self, client):
        orig, mock = _mock_slow_brain()
        from app import memory_engine
        memory_engine.analyze_purchase = mock
        try:
            resp = client.post("/pipeline-analyze", json={
                "product": "Test", "cost": 10.0, "website": "test.com",
                "time_to_cart": 30.0, "time_on_site": 60.0,
                "click_count": 1, "peak_scroll_velocity": 100.0, "system_hour": 0,
            })
            assert resp.status_code == 200
        finally:
            memory_engine.analyze_purchase = orig

    def test_system_hour_23(self, client):
        orig, mock = _mock_slow_brain()
        from app import memory_engine
        memory_engine.analyze_purchase = mock
        try:
            resp = client.post("/pipeline-analyze", json={
                "product": "Test", "cost": 10.0, "website": "test.com",
                "time_to_cart": 30.0, "time_on_site": 60.0,
                "click_count": 1, "peak_scroll_velocity": 100.0, "system_hour": 23,
            })
            assert resp.status_code == 200
        finally:
            memory_engine.analyze_purchase = orig

    def test_system_hour_24_rejected(self, client):
        resp = client.post("/pipeline-analyze", json={
            "product": "Test", "cost": 10.0, "website": "test.com",
            "time_to_cart": 30.0, "time_on_site": 60.0,
            "click_count": 1, "peak_scroll_velocity": 100.0, "system_hour": 24,
        })
        assert resp.status_code == 422

    def test_cost_zero(self, client):
        orig, mock = _mock_slow_brain()
        from app import memory_engine
        memory_engine.analyze_purchase = mock
        try:
            resp = client.post("/pipeline-analyze", json={
                "product": "Free Item", "cost": 0, "website": "test.com",
                "time_to_cart": 30.0, "time_on_site": 60.0,
                "click_count": 1, "peak_scroll_velocity": 100.0, "system_hour": 12,
            })
            assert resp.status_code == 200
        finally:
            memory_engine.analyze_purchase = orig

    def test_negative_cost_rejected(self, client):
        resp = client.post("/pipeline-analyze", json={
            "product": "Test", "cost": -1.0, "website": "test.com",
            "time_to_cart": 30.0, "time_on_site": 60.0,
            "click_count": 1, "peak_scroll_velocity": 100.0, "system_hour": 12,
        })
        assert resp.status_code == 422


# ── time_to_cart=null fallback behavior ─────────────────────────────────

class TestTimeToCartNull:
    def test_null_ttc_uses_time_on_site(self, client):
        orig, mock = _mock_slow_brain()
        from app import memory_engine
        memory_engine.analyze_purchase = mock
        try:
            resp = client.post("/pipeline-analyze", json={
                "product": "Widget", "cost": 25.0, "website": "test.com",
                "time_to_cart": None, "time_on_site": 120.0,
                "click_count": 5, "peak_scroll_velocity": 500.0, "system_hour": 12,
            })
            assert resp.status_code == 200
            data = resp.json()
            assert 0.0 <= data["p_impulse_fast"] <= 1.0
        finally:
            memory_engine.analyze_purchase = orig

    def test_missing_ttc_field_uses_time_on_site(self, client):
        orig, mock = _mock_slow_brain()
        from app import memory_engine
        memory_engine.analyze_purchase = mock
        try:
            resp = client.post("/pipeline-analyze", json={
                "product": "Widget", "cost": 25.0, "website": "test.com",
                "time_on_site": 120.0,
                "click_count": 5, "peak_scroll_velocity": 500.0, "system_hour": 12,
            })
            assert resp.status_code == 200
        finally:
            memory_engine.analyze_purchase = orig


# ── /gemini-analyze ─────────────────────────────────────────────────────

class TestGeminiAnalyze:
    def test_without_client_returns_fallback(self, client):
        import app as app_module
        original_client = app_module.gemini_client
        app_module.gemini_client = None
        try:
            resp = client.post("/gemini-analyze", json={
                "current_purchase": {
                    "actionType": "add_to_cart",
                    "productName": "Test Shoes",
                    "priceValue": 99.99,
                    "timeToCart": 15.0,
                    "timeOnSite": 60.0,
                    "domain": "amazon.com",
                },
            })
            assert resp.status_code == 200
            data = resp.json()
            assert data["risk_level"] == "MEDIUM"
            assert data["should_intervene"] is True
            assert "unavailable" in data["reasoning"].lower() or "not configured" in data["personalized_message"].lower()
        finally:
            app_module.gemini_client = original_client


# ── build_gemini_prompt ─────────────────────────────────────────────────

class TestBuildGeminiPrompt:
    def test_output_contains_product_info(self):
        request = GeminiAnalyzeRequest(
            current_purchase=PurchaseAttempt(
                actionType="add_to_cart",
                productName="Wireless Headphones",
                priceValue=129.99,
                timeToCart=15.0,
                timeOnSite=120.0,
                domain="amazon.com",
                clickCount=5,
                peakScrollVelocity=800.0,
            ),
            purchase_history=[],
            preferences={"budget": 500, "threshold": 100, "sensitivity": "medium"},
        )
        prompt = build_gemini_prompt(request)
        assert "Wireless Headphones" in prompt
        assert "amazon.com" in prompt
        assert "15.0s" in prompt
        assert "$500" in prompt

    def test_output_contains_risk_format(self):
        request = GeminiAnalyzeRequest(
            current_purchase=PurchaseAttempt(
                actionType="buy_now",
                productName="Test",
                priceValue=10.0,
                timeToCart=5.0,
                timeOnSite=30.0,
            ),
        )
        prompt = build_gemini_prompt(request)
        assert "risk_level" in prompt
        assert "risk_score" in prompt
        assert "BUY NOW" in prompt

    def test_history_stats_calculated(self):
        request = GeminiAnalyzeRequest(
            current_purchase=PurchaseAttempt(
                actionType="add_to_cart",
                timeToCart=10.0,
                timeOnSite=60.0,
            ),
            purchase_history=[
                PurchaseAttempt(actionType="add_to_cart", priceValue=50.0, timeToCart=20.0, timeOnSite=60.0),
                PurchaseAttempt(actionType="add_to_cart", priceValue=30.0, timeToCart=40.0, timeOnSite=90.0),
            ],
        )
        prompt = build_gemini_prompt(request)
        assert "$80.00" in prompt  # total_spent = 50 + 30


# ── /update-preferences edge cases ──────────────────────────────────────

class TestUpdatePreferencesEdge:
    def test_missing_budget_file_returns_error(self, client):
        import app as app_module
        original_dir = app_module.MEMORY_DIR

        # Point to empty temp dir
        import tempfile
        empty_dir = tempfile.mkdtemp()
        app_module.MEMORY_DIR = empty_dir

        try:
            resp = client.post("/update-preferences", json={
                "budget": 500.0, "threshold": 50.0, "sensitivity": "medium",
            })
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "error"
            assert data["budget_updated"] is False
        finally:
            app_module.MEMORY_DIR = original_dir
            import shutil
            shutil.rmtree(empty_dir, ignore_errors=True)

    def test_zero_budget_zero_threshold_rejects(self, client):
        """Zero budget + zero threshold should still be accepted by API (validation is in popup.js)."""
        import app as app_module
        os.makedirs(app_module.MEMORY_DIR, exist_ok=True)
        budget_path = os.path.join(app_module.MEMORY_DIR, "Budget.md")
        with open(budget_path, "w") as f:
            f.write("# Budget\nplaceholder\n")

        resp = client.post("/update-preferences", json={
            "budget": 0.0, "threshold": 0.0, "sensitivity": "low",
        })
        # API accepts 0 budget (validation is client-side)
        assert resp.status_code == 200


# ── /reset-memory ───────────────────────────────────────────────────────

class TestResetMemory:
    def test_writes_all_templates(self, client):
        import app as app_module
        from app import memory_engine

        os.makedirs(app_module.MEMORY_DIR, exist_ok=True)
        for fname in ["Goals.md", "Budget.md", "State.md", "Behavior.md"]:
            with open(os.path.join(app_module.MEMORY_DIR, fname), "w") as f:
                f.write("dirty content\n")

        orig_reindex = memory_engine.reindex_memory

        async def mock_reindex():
            return True

        memory_engine.reindex_memory = mock_reindex
        try:
            resp = client.post("/reset-memory", json={})
            assert resp.status_code == 200
            data = resp.json()
            assert data["files_reset"] == 4

            # Verify each template was written
            goals = open(os.path.join(app_module.MEMORY_DIR, "Goals.md")).read()
            assert "Financial Goals" in goals

            budget = open(os.path.join(app_module.MEMORY_DIR, "Budget.md")).read()
            assert "Monthly Spending Limits" in budget

            state = open(os.path.join(app_module.MEMORY_DIR, "State.md")).read()
            assert "Financial Overview" in state

            behavior = open(os.path.join(app_module.MEMORY_DIR, "Behavior.md")).read()
            assert "Observed Behaviors" in behavior
        finally:
            memory_engine.reindex_memory = orig_reindex


# ── /health ─────────────────────────────────────────────────────────────

class TestHealth:
    def test_health_fields(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert "status" in data
        assert data["status"] == "healthy"
        assert "memory_indexed" in data
        assert "fast_brain_available" in data
        assert "gemini_available" in data


# ── /consolidate-memory ─────────────────────────────────────────────────

class TestConsolidateMemory:
    def test_no_engine_returns_error(self, client):
        import app as app_module
        original_engine = app_module.memory_engine
        app_module.memory_engine = None
        try:
            resp = client.post("/consolidate-memory", json={})
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "error"
        finally:
            app_module.memory_engine = original_engine

    def test_success_path(self, client):
        import app as app_module
        from app import memory_engine

        orig = memory_engine.consolidate_memory

        async def mock_consolidate():
            return {
                "Goals.md": {"status": "skipped", "reason": "below thresholds"},
                "Budget.md": {"status": "skipped", "reason": "below thresholds"},
                "State.md": {"status": "skipped", "reason": "below thresholds"},
                "Behavior.md": {"status": "consolidated", "old_size": 3000, "new_size": 1000},
            }

        memory_engine.consolidate_memory = mock_consolidate
        try:
            resp = client.post("/consolidate-memory", json={})
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "success"
            assert "Consolidated 1" in data["message"]
        finally:
            memory_engine.consolidate_memory = orig


# ── Root endpoint ───────────────────────────────────────────────────────

class TestRootEndpoint:
    def test_root_returns_version(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["version"] == "2.1.0"
        assert "endpoints" in data
        assert "/pipeline-analyze" in data["endpoints"]

    def test_root_shows_brain_availability(self, client):
        resp = client.get("/")
        data = resp.json()
        assert "fast_brain_available" in data
        assert "slow_brain_available" in data
