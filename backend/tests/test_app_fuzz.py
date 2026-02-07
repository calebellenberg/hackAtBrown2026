"""
Fuzz tests for FastAPI endpoints using Hypothesis.

Ensures API endpoints handle arbitrary valid inputs without crashing
and always return bounded, well-typed responses.
"""

import math
import pytest
from hypothesis import given, settings, assume, HealthCheck
from hypothesis import strategies as st
from fastapi.testclient import TestClient

from app import app


@pytest.fixture
def client():
    return TestClient(app)


# ── /pipeline-analyze: valid ranges always produce 200 with bounded score ──

@given(
    cost=st.floats(min_value=0.0, max_value=100000.0, allow_nan=False, allow_infinity=False),
    ttc=st.floats(min_value=0.1, max_value=10000.0, allow_nan=False, allow_infinity=False),
    time_on_site=st.floats(min_value=1.0, max_value=100000.0, allow_nan=False, allow_infinity=False),
    click_count=st.integers(min_value=0, max_value=10000),
    scroll_vel=st.floats(min_value=0.0, max_value=100000.0, allow_nan=False, allow_infinity=False),
    hour=st.integers(min_value=0, max_value=23),
)
@settings(max_examples=50, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_pipeline_valid_ranges_200(client, cost, ttc, time_on_site, click_count, scroll_vel, hour):
    """Valid PipelineRequest ranges always produce 200 with bounded impulse_score."""
    from app import memory_engine
    orig = memory_engine.analyze_purchase

    async def mock_analyze(p_impulse_fast, purchase_data):
        return {
            "impulse_score": min(max(p_impulse_fast, 0.0), 1.0),
            "confidence": 0.7,
            "reasoning": "fuzz test",
            "intervention_action": "MIRROR",
            "memory_update": None,
        }

    memory_engine.analyze_purchase = mock_analyze
    try:
        resp = client.post("/pipeline-analyze", json={
            "product": "Fuzz Widget",
            "cost": cost,
            "website": "test.com",
            "time_to_cart": ttc,
            "time_on_site": time_on_site,
            "click_count": click_count,
            "peak_scroll_velocity": scroll_vel,
            "system_hour": hour,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert 0.0 <= data["p_impulse_fast"] <= 1.0
        assert 0.0 <= data["impulse_score"] <= 1.0
        assert math.isfinite(data["p_impulse_fast"])
    finally:
        memory_engine.analyze_purchase = orig


# ── Invalid system_hour produces 422 ────────────────────────────────────

@given(hour=st.integers(min_value=24, max_value=1000))
@settings(max_examples=20, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_pipeline_invalid_hour_422(client, hour):
    resp = client.post("/pipeline-analyze", json={
        "product": "Test",
        "cost": 10.0,
        "website": "test.com",
        "time_to_cart": 10.0,
        "time_on_site": 60.0,
        "click_count": 1,
        "peak_scroll_velocity": 100.0,
        "system_hour": hour,
    })
    assert resp.status_code == 422


@given(hour=st.integers(min_value=-1000, max_value=-1))
@settings(max_examples=20, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_pipeline_negative_hour_422(client, hour):
    resp = client.post("/pipeline-analyze", json={
        "product": "Test",
        "cost": 10.0,
        "website": "test.com",
        "time_to_cart": 10.0,
        "time_on_site": 60.0,
        "click_count": 1,
        "peak_scroll_velocity": 100.0,
        "system_hour": hour,
    })
    assert resp.status_code == 422


# ── Unicode/emoji product names don't crash ─────────────────────────────

@given(product=st.text(min_size=1, max_size=200))
@settings(max_examples=50, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_pipeline_unicode_product_names(client, product):
    from app import memory_engine
    orig = memory_engine.analyze_purchase

    async def mock_analyze(p_impulse_fast, purchase_data):
        return {
            "impulse_score": 0.5,
            "confidence": 0.7,
            "reasoning": "ok",
            "intervention_action": "NONE",
            "memory_update": None,
        }

    memory_engine.analyze_purchase = mock_analyze
    try:
        resp = client.post("/pipeline-analyze", json={
            "product": product,
            "cost": 10.0,
            "website": "test.com",
            "time_to_cart": 30.0,
            "time_on_site": 60.0,
            "click_count": 1,
            "peak_scroll_velocity": 100.0,
            "system_hour": 12,
        })
        assert resp.status_code == 200
    finally:
        memory_engine.analyze_purchase = orig


# ── Extreme cost values don't crash ─────────────────────────────────────

@given(cost=st.floats(min_value=0.0, max_value=1e9, allow_nan=False, allow_infinity=False))
@settings(max_examples=30, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_pipeline_extreme_cost(client, cost):
    from app import memory_engine
    orig = memory_engine.analyze_purchase

    async def mock_analyze(p_impulse_fast, purchase_data):
        return {
            "impulse_score": 0.5,
            "confidence": 0.7,
            "reasoning": "ok",
            "intervention_action": "NONE",
            "memory_update": None,
        }

    memory_engine.analyze_purchase = mock_analyze
    try:
        resp = client.post("/pipeline-analyze", json={
            "product": "Expensive Item",
            "cost": cost,
            "website": "luxury.com",
            "time_to_cart": 30.0,
            "time_on_site": 60.0,
            "click_count": 1,
            "peak_scroll_velocity": 100.0,
            "system_hour": 12,
        })
        assert resp.status_code == 200
    finally:
        memory_engine.analyze_purchase = orig


# ── Response intervention_action is always one of 4 valid values ────────

@given(hour=st.integers(min_value=0, max_value=23))
@settings(max_examples=24, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_pipeline_intervention_always_valid(client, hour):
    from app import memory_engine
    orig = memory_engine.analyze_purchase

    async def mock_analyze(p_impulse_fast, purchase_data):
        return {
            "impulse_score": p_impulse_fast,
            "confidence": 0.7,
            "reasoning": "ok",
            "intervention_action": "MIRROR",
            "memory_update": None,
        }

    memory_engine.analyze_purchase = mock_analyze
    try:
        resp = client.post("/pipeline-analyze", json={
            "product": "Test",
            "cost": 50.0,
            "website": "amazon.com",
            "time_to_cart": 15.0,
            "time_on_site": 60.0,
            "click_count": 5,
            "peak_scroll_velocity": 1000.0,
            "system_hour": hour,
        })
        assert resp.status_code == 200
        data = resp.json()
        valid_actions = {"NONE", "MIRROR", "COOLDOWN", "PHRASE"}
        assert data["fast_brain_intervention"] in valid_actions
        assert data["intervention_action"] in valid_actions
    finally:
        memory_engine.analyze_purchase = orig


# ── /analyze: valid score + data returns 200 ────────────────────────────

@given(
    score=st.floats(min_value=0.0, max_value=1.0),
    cost=st.floats(min_value=0.0, max_value=100000.0, allow_nan=False, allow_infinity=False),
)
@settings(max_examples=30, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_analyze_valid_inputs(client, score, cost):
    from app import memory_engine
    orig = memory_engine.analyze_purchase

    async def mock_analyze(p_impulse_fast, purchase_data):
        return {
            "impulse_score": p_impulse_fast,
            "confidence": 0.7,
            "reasoning": "ok",
            "intervention_action": "NONE",
            "memory_update": None,
        }

    memory_engine.analyze_purchase = mock_analyze
    try:
        resp = client.post("/analyze", json={
            "p_impulse_fast": score,
            "product": "Test",
            "cost": cost,
            "website": "test.com",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert 0.0 <= data["impulse_score"] <= 1.0
    finally:
        memory_engine.analyze_purchase = orig


# ── /analyze: invalid score rejected ────────────────────────────────────

@given(score=st.floats(min_value=1.01, max_value=1000.0))
@settings(max_examples=20, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_analyze_score_above_one_rejected(client, score):
    resp = client.post("/analyze", json={
        "p_impulse_fast": score,
        "product": "Test",
        "cost": 10.0,
        "website": "test.com",
    })
    assert resp.status_code == 422


@given(score=st.floats(max_value=-0.01, min_value=-1000.0))
@settings(max_examples=20, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_analyze_negative_score_rejected(client, score):
    resp = client.post("/analyze", json={
        "p_impulse_fast": score,
        "product": "Test",
        "cost": 10.0,
        "website": "test.com",
    })
    assert resp.status_code == 422
