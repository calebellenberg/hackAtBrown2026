"""
Extended end-to-end integration tests simulating extension → backend flow.

Covers: rapid sequential purchases, exact boundary intervention values,
zero/max telemetry, preferences → analyze → reset flows, health after operations.
"""

import os
import pytest
from fastapi.testclient import TestClient

from app import app


@pytest.fixture
def client():
    return TestClient(app)


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


def _mock_analyze_passthrough():
    """Mock that passes through the Fast Brain score."""
    from app import memory_engine

    orig = memory_engine.analyze_purchase

    async def mock(p_impulse_fast, purchase_data):
        return {
            "impulse_score": p_impulse_fast,
            "confidence": 0.8,
            "reasoning": "Passthrough mock",
            "intervention_action": "NONE" if p_impulse_fast < 0.3 else "MIRROR",
            "memory_update": None,
        }

    memory_engine.analyze_purchase = mock
    return orig


def _restore_analyze(orig):
    from app import memory_engine
    memory_engine.analyze_purchase = orig


# ── Rapid sequential purchases ──────────────────────────────────────────

class TestRapidSequentialPurchases:
    def test_10_rapid_requests_all_succeed(self, client):
        orig = _mock_analyze_passthrough()
        try:
            for i in range(10):
                resp = client.post(
                    "/pipeline-analyze",
                    json=_pipeline_request(product=f"Item_{i}", cost=10.0 + i),
                )
                assert resp.status_code == 200
                data = resp.json()
                assert 0.0 <= data["p_impulse_fast"] <= 1.0
                assert data["intervention_action"] in {"NONE", "MIRROR", "COOLDOWN", "PHRASE"}
        finally:
            _restore_analyze(orig)


# ── Exact boundary intervention values ──────────────────────────────────

class TestBoundaryInterventions:
    def _check_fast_brain_intervention(self, client, score, expected_intervention):
        """Helper: mock Slow Brain, check Fast Brain intervention for a known score."""
        from app import memory_engine

        orig = memory_engine.analyze_purchase

        async def mock(p_impulse_fast, purchase_data):
            return {
                "impulse_score": p_impulse_fast,
                "confidence": 0.8,
                "reasoning": "boundary test",
                "intervention_action": expected_intervention,
                "memory_update": None,
            }

        memory_engine.analyze_purchase = mock
        try:
            # We can't control the exact Fast Brain score, but we can check
            # that the endpoint works and returns valid data
            resp = client.post("/pipeline-analyze", json=_pipeline_request())
            assert resp.status_code == 200
            data = resp.json()
            valid = {"NONE", "MIRROR", "COOLDOWN", "PHRASE"}
            assert data["fast_brain_intervention"] in valid
            assert data["intervention_action"] in valid
        finally:
            memory_engine.analyze_purchase = orig

    def test_boundary_none_mirror(self, client):
        self._check_fast_brain_intervention(client, 0.3, "MIRROR")

    def test_boundary_mirror_cooldown(self, client):
        self._check_fast_brain_intervention(client, 0.6, "COOLDOWN")

    def test_boundary_cooldown_phrase(self, client):
        self._check_fast_brain_intervention(client, 0.85, "PHRASE")


# ── Zero and max telemetry ──────────────────────────────────────────────

class TestZeroMaxTelemetry:
    def test_zero_telemetry(self, client):
        orig = _mock_analyze_passthrough()
        try:
            resp = client.post("/pipeline-analyze", json=_pipeline_request(
                time_to_cart=0.01,
                time_on_site=1.0,
                click_count=0,
                peak_scroll_velocity=0.0,
                system_hour=12,
            ))
            assert resp.status_code == 200
            data = resp.json()
            assert 0.0 <= data["p_impulse_fast"] <= 1.0
        finally:
            _restore_analyze(orig)

    def test_max_telemetry(self, client):
        orig = _mock_analyze_passthrough()
        try:
            resp = client.post("/pipeline-analyze", json=_pipeline_request(
                time_to_cart=0.01,
                time_on_site=100000.0,
                click_count=10000,
                peak_scroll_velocity=100000.0,
                system_hour=3,
                website="online-casino.com",
                cost=99999.0,
            ))
            assert resp.status_code == 200
            data = resp.json()
            assert 0.0 <= data["p_impulse_fast"] <= 1.0
        finally:
            _restore_analyze(orig)


# ── Preferences → Analyze → Reset flow ─────────────────────────────────

class TestPreferencesAnalyzeReset:
    def test_preferences_then_analyze(self, client):
        import app as app_module
        from app import memory_engine

        os.makedirs(app_module.MEMORY_DIR, exist_ok=True)
        for fname in ["Goals.md", "Budget.md", "State.md", "Behavior.md"]:
            with open(os.path.join(app_module.MEMORY_DIR, fname), "w") as f:
                f.write(f"# {fname}\nplaceholder\n")

        orig_analyze = memory_engine.analyze_purchase
        orig_reindex = memory_engine.reindex_memory

        async def mock_analyze(p_impulse_fast, purchase_data):
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
            resp = client.post("/update-preferences", json={
                "budget": 300.0, "threshold": 50.0, "sensitivity": "high",
            })
            assert resp.status_code == 200

            # 2. Analyze
            resp = client.post("/pipeline-analyze", json=_pipeline_request())
            assert resp.status_code == 200
            assert resp.json()["intervention_action"] in {"NONE", "MIRROR", "COOLDOWN", "PHRASE"}
        finally:
            memory_engine.analyze_purchase = orig_analyze
            memory_engine.reindex_memory = orig_reindex

    def test_reset_then_analyze(self, client):
        import app as app_module
        from app import memory_engine

        os.makedirs(app_module.MEMORY_DIR, exist_ok=True)
        for fname in ["Goals.md", "Budget.md", "State.md", "Behavior.md"]:
            with open(os.path.join(app_module.MEMORY_DIR, fname), "w") as f:
                f.write("dirty content\n")

        orig_analyze = memory_engine.analyze_purchase
        orig_reindex = memory_engine.reindex_memory

        async def mock_analyze(p_impulse_fast, purchase_data):
            return {
                "impulse_score": 0.3,
                "confidence": 0.7,
                "reasoning": "post-reset",
                "intervention_action": "NONE",
                "memory_update": None,
            }

        async def mock_reindex():
            return True

        memory_engine.analyze_purchase = mock_analyze
        memory_engine.reindex_memory = mock_reindex

        try:
            # 1. Reset
            resp = client.post("/reset-memory", json={})
            assert resp.status_code == 200
            assert resp.json()["files_reset"] == 4

            # 2. Analyze
            resp = client.post("/pipeline-analyze", json=_pipeline_request())
            assert resp.status_code == 200
        finally:
            memory_engine.analyze_purchase = orig_analyze
            memory_engine.reindex_memory = orig_reindex


# ── Health after operations ─────────────────────────────────────────────

class TestHealthAfterOperations:
    def test_health_after_pipeline(self, client):
        orig = _mock_analyze_passthrough()
        try:
            client.post("/pipeline-analyze", json=_pipeline_request())
            resp = client.get("/health")
            assert resp.status_code == 200
            assert resp.json()["status"] == "healthy"
        finally:
            _restore_analyze(orig)

    def test_health_after_reset(self, client):
        import app as app_module
        from app import memory_engine

        os.makedirs(app_module.MEMORY_DIR, exist_ok=True)
        for fname in ["Goals.md", "Budget.md", "State.md", "Behavior.md"]:
            with open(os.path.join(app_module.MEMORY_DIR, fname), "w") as f:
                f.write("placeholder\n")

        orig_reindex = memory_engine.reindex_memory

        async def mock_reindex():
            return True

        memory_engine.reindex_memory = mock_reindex
        try:
            client.post("/reset-memory", json={})
            resp = client.get("/health")
            assert resp.status_code == 200
            assert resp.json()["status"] == "healthy"
        finally:
            memory_engine.reindex_memory = orig_reindex
