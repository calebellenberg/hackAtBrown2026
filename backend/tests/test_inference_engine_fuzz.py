"""
Fuzz tests for the Fast Brain (ImpulseInferenceEngine) using Hypothesis.

Property-based tests ensuring all math operations are bounded, monotonic,
and never produce NaN/infinity regardless of input.
"""

import math
import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from inference_engine import ImpulseInferenceEngine


VALID_BASELINE = {
    "scroll_velocity": {"mean": 600.0, "std": 5500.0},
    "click_rate": {"mean": 0.15, "std": 1.0},
    "time_on_site": {"mean": 180.0, "std": 110.0},
    "time_to_cart": {"mean": 2.5, "std": 32.0},
}


def _make_engine():
    return ImpulseInferenceEngine(baseline_data=VALID_BASELINE, prior_p=0.2)


# ── calculate_p_impulse always in [0, 1] ────────────────────────────────

@given(
    arousal=st.floats(min_value=0.0, max_value=1.0),
    click_rate=st.floats(min_value=0.0, max_value=100.0),
    scroll_vel=st.floats(min_value=0.0, max_value=100000.0),
    ttc=st.floats(min_value=0.01, max_value=10000.0),
    hour=st.integers(min_value=0, max_value=23),
)
@settings(max_examples=200)
def test_p_impulse_always_bounded(arousal, click_rate, scroll_vel, ttc, hour):
    engine = _make_engine()
    data = {
        "emotion_arousal": arousal,
        "click_rate": click_rate,
        "scroll_velocity_peak": scroll_vel,
        "time_to_cart": ttc,
        "system_time": hour,
        "website_name": "amazon",
    }
    score = engine.calculate_p_impulse(data)
    assert 0.0 <= score <= 1.0
    assert math.isfinite(score)


# ── get_intervention_level returns valid string for any score in [0, 1] ──

@given(score=st.floats(min_value=0.0, max_value=1.0))
@settings(max_examples=200)
def test_intervention_level_valid_for_any_score(score):
    engine = _make_engine()
    level = engine.get_intervention_level(score)
    assert level in {"NONE", "MIRROR", "COOLDOWN", "PHRASE"}


# ── _calculate_z_score handles zero std safely ──────────────────────────

@given(
    value=st.floats(min_value=-1e6, max_value=1e6, allow_nan=False, allow_infinity=False),
    mean=st.floats(min_value=-1e6, max_value=1e6, allow_nan=False, allow_infinity=False),
)
@settings(max_examples=100)
def test_z_score_zero_std_safe(value, mean):
    engine = _make_engine()
    z = engine._calculate_z_score(value, mean, 0.0)
    assert z == 0.0


@given(
    value=st.floats(min_value=-1e6, max_value=1e6, allow_nan=False, allow_infinity=False),
    mean=st.floats(min_value=-1e6, max_value=1e6, allow_nan=False, allow_infinity=False),
    std=st.floats(min_value=0.001, max_value=1e6, allow_nan=False, allow_infinity=False),
)
@settings(max_examples=100)
def test_z_score_always_finite(value, mean, std):
    engine = _make_engine()
    z = engine._calculate_z_score(value, mean, std)
    assert math.isfinite(z)


# ── _sigmoid_likelihood bounded for extreme z-scores ────────────────────

@given(z=st.floats(min_value=-100.0, max_value=100.0))
@settings(max_examples=200)
def test_sigmoid_bounded(z):
    engine = _make_engine()
    lik = engine._sigmoid_likelihood(z)
    assert engine.LIKELIHOOD_MIN <= lik <= engine.LIKELIHOOD_MAX
    assert math.isfinite(lik)


# ── _calculate_ttc_likelihood bounded for any positive float ────────────

@given(ttc=st.floats(min_value=0.0, max_value=100000.0))
@settings(max_examples=200)
def test_ttc_likelihood_bounded(ttc):
    engine = _make_engine()
    lik = engine._calculate_ttc_likelihood(ttc)
    assert 0.0 <= lik <= 1.0
    assert math.isfinite(lik)


def test_ttc_likelihood_zero():
    engine = _make_engine()
    assert engine._calculate_ttc_likelihood(0.0) == 1.0


def test_ttc_likelihood_negative():
    engine = _make_engine()
    assert engine._calculate_ttc_likelihood(-10.0) == 1.0


# ── _get_late_night_multiplier bounded [1.0, 1.5] for hours [0, 23] ────

@given(hour=st.integers(min_value=0, max_value=23))
@settings(max_examples=24)
def test_late_night_multiplier_bounded(hour):
    engine = _make_engine()
    mult = engine._get_late_night_multiplier(hour)
    assert 1.0 <= mult <= 1.5


def test_late_night_peak_at_3am():
    engine = _make_engine()
    assert engine._get_late_night_multiplier(3) == 1.5


def test_late_night_no_effect_at_noon():
    engine = _make_engine()
    assert engine._get_late_night_multiplier(12) == 1.0


# ── _get_website_risk_factor returns positive float for any string ──────

@given(name=st.text(min_size=0, max_size=200))
@settings(max_examples=200)
def test_website_risk_positive_for_any_string(name):
    engine = _make_engine()
    factor = engine._get_website_risk_factor(name)
    assert factor > 0.0
    assert math.isfinite(factor)


# ── Monotonicity: higher scroll velocity → higher or equal score ────────

@given(
    low_scroll=st.floats(min_value=0.0, max_value=500.0),
    high_scroll=st.floats(min_value=5000.0, max_value=50000.0),
)
@settings(max_examples=100)
def test_higher_scroll_higher_score(low_scroll, high_scroll):
    engine = _make_engine()
    base = {
        "emotion_arousal": 0.5,
        "click_rate": 0.15,
        "time_to_cart": 60.0,
        "system_time": 12,
        "website_name": "bestbuy",
    }
    score_low = engine.calculate_p_impulse({**base, "scroll_velocity_peak": low_scroll})
    score_high = engine.calculate_p_impulse({**base, "scroll_velocity_peak": high_scroll})
    assert score_high >= score_low


# ── Monotonicity: lower time_to_cart → higher or equal score ────────────

@given(
    fast_ttc=st.floats(min_value=0.01, max_value=10.0),
    slow_ttc=st.floats(min_value=200.0, max_value=1000.0),
)
@settings(max_examples=100)
def test_lower_ttc_higher_score(fast_ttc, slow_ttc):
    engine = _make_engine()
    base = {
        "emotion_arousal": 0.5,
        "click_rate": 0.15,
        "scroll_velocity_peak": 600.0,
        "system_time": 12,
        "website_name": "bestbuy",
    }
    score_fast = engine.calculate_p_impulse({**base, "time_to_cart": fast_ttc})
    score_slow = engine.calculate_p_impulse({**base, "time_to_cart": slow_ttc})
    assert score_fast >= score_slow


# ── get_structured_output returns all required keys ─────────────────────

@given(
    arousal=st.floats(min_value=0.0, max_value=1.0),
    click_rate=st.floats(min_value=0.0, max_value=10.0),
    scroll_vel=st.floats(min_value=0.0, max_value=50000.0),
    ttc=st.floats(min_value=0.01, max_value=5000.0),
    hour=st.integers(min_value=0, max_value=23),
)
@settings(max_examples=100)
def test_structured_output_always_has_required_keys(arousal, click_rate, scroll_vel, ttc, hour):
    engine = _make_engine()
    data = {
        "emotion_arousal": arousal,
        "click_rate": click_rate,
        "scroll_velocity_peak": scroll_vel,
        "time_to_cart": ttc,
        "system_time": hour,
        "website_name": "amazon",
    }
    output = engine.get_structured_output(data)
    assert "p_impulse" in output
    assert "dominant_trigger" in output
    assert "logic_summary" in output
    assert 0.0 <= output["p_impulse"] <= 1.0
    assert math.isfinite(output["p_impulse"])


# ── Extreme values never produce NaN/infinity ───────────────────────────

def test_extreme_max_values_no_nan():
    engine = _make_engine()
    data = {
        "emotion_arousal": 1.0,
        "click_rate": 1e6,
        "scroll_velocity_peak": 1e8,
        "time_to_cart": 0.001,
        "system_time": 3,
        "website_name": "gambling",
    }
    score = engine.calculate_p_impulse(data)
    assert math.isfinite(score)
    output = engine.get_structured_output(data)
    assert math.isfinite(output["p_impulse"])


def test_extreme_min_values_no_nan():
    engine = _make_engine()
    data = {
        "emotion_arousal": 0.0,
        "click_rate": 0.0,
        "scroll_velocity_peak": 0.0,
        "time_to_cart": 1e8,
        "system_time": 12,
        "website_name": "educational",
    }
    score = engine.calculate_p_impulse(data)
    assert math.isfinite(score)
    output = engine.get_structured_output(data)
    assert math.isfinite(output["p_impulse"])
