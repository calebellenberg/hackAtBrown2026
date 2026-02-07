"""
Unit tests for the Fast Brain (ImpulseInferenceEngine).
"""

import pytest
from inference_engine import ImpulseInferenceEngine


# Valid baseline that satisfies the engine's required keys
VALID_BASELINE = {
    "scroll_velocity": {"mean": 600.0, "std": 5500.0},
    "click_rate": {"mean": 0.15, "std": 1.0},
    "time_on_site": {"mean": 180.0, "std": 110.0},
    "time_to_cart": {"mean": 2.5, "std": 32.0},
}


def _make_engine(baseline=None, prior_p=0.2):
    return ImpulseInferenceEngine(
        baseline_data=baseline or VALID_BASELINE, prior_p=prior_p
    )


# ── Initialization ──────────────────────────────────────────────────────

def test_init_with_valid_baselines():
    engine = _make_engine()
    assert engine.prior_p == 0.2
    assert engine.baseline_data == VALID_BASELINE


def test_init_missing_required_key():
    bad_baseline = {"scroll_velocity": {"mean": 1, "std": 1}}
    with pytest.raises(ValueError, match="Missing baseline data"):
        _make_engine(baseline=bad_baseline)


def test_init_missing_mean_or_std():
    bad_baseline = {
        "scroll_velocity": {"mean": 1},  # missing std
        "click_rate": {"mean": 0.15, "std": 1.0},
        "time_on_site": {"mean": 180.0, "std": 110.0},
    }
    with pytest.raises(ValueError, match="must contain 'mean' and 'std'"):
        _make_engine(baseline=bad_baseline)


# ── calculate_p_impulse ────────────────────────────────────────────────

def test_neutral_inputs_low_score():
    """Neutral telemetry (at baseline means) should produce a low score."""
    engine = _make_engine()
    data = {
        "emotion_arousal": 0.5,
        "click_rate": 0.15,
        "scroll_velocity_peak": 600.0,
        "time_to_cart": 300.0,
        "system_time": 12,
        "website_name": "bestbuy",
    }
    score = engine.calculate_p_impulse(data)
    assert score < 0.3, f"Neutral inputs should give <0.3, got {score}"


def test_high_impulse_inputs():
    """Extreme telemetry should push the score above 0.5."""
    engine = _make_engine()
    data = {
        "emotion_arousal": 0.95,
        "click_rate": 5.0,
        "scroll_velocity_peak": 20000.0,
        "time_to_cart": 2.0,
        "system_time": 3,
        "website_name": "amazon",
    }
    score = engine.calculate_p_impulse(data)
    assert score > 0.5, f"High-impulse inputs should give >0.5, got {score}"


def test_output_bounded_zero_one():
    """Score must always be in [0, 1] regardless of inputs."""
    engine = _make_engine()
    extreme_cases = [
        {"emotion_arousal": 0.0, "click_rate": 0.0, "scroll_velocity_peak": 0.0,
         "time_to_cart": 99999, "system_time": 12, "website_name": "educational"},
        {"emotion_arousal": 1.0, "click_rate": 100.0, "scroll_velocity_peak": 100000.0,
         "time_to_cart": 0.1, "system_time": 3, "website_name": "gambling"},
    ]
    for data in extreme_cases:
        score = engine.calculate_p_impulse(data)
        assert 0.0 <= score <= 1.0, f"Score out of bounds: {score}"


# ── Intervention thresholds ────────────────────────────────────────────

def test_intervention_none():
    engine = _make_engine()
    assert engine.get_intervention_level(0.1) == "NONE"
    assert engine.get_intervention_level(0.29) == "NONE"


def test_intervention_mirror():
    engine = _make_engine()
    assert engine.get_intervention_level(0.3) == "MIRROR"
    assert engine.get_intervention_level(0.59) == "MIRROR"


def test_intervention_cooldown():
    engine = _make_engine()
    assert engine.get_intervention_level(0.6) == "COOLDOWN"
    assert engine.get_intervention_level(0.84) == "COOLDOWN"


def test_intervention_phrase():
    engine = _make_engine()
    assert engine.get_intervention_level(0.85) == "PHRASE"
    assert engine.get_intervention_level(1.0) == "PHRASE"


# ── Late-night multiplier ─────────────────────────────────────────────

def test_late_night_higher_than_midday():
    engine = _make_engine()
    base_data = {
        "emotion_arousal": 0.7,
        "click_rate": 1.0,
        "scroll_velocity_peak": 3000.0,
        "time_to_cart": 15.0,
        "website_name": "amazon",
    }
    data_night = {**base_data, "system_time": 3}
    data_day = {**base_data, "system_time": 12}

    score_night = engine.calculate_p_impulse(data_night)
    score_day = engine.calculate_p_impulse(data_day)
    assert score_night > score_day, (
        f"Late-night score ({score_night}) should exceed midday ({score_day})"
    )


# ── Website risk factors ──────────────────────────────────────────────

def test_website_risk_amazon():
    engine = _make_engine()
    assert engine._get_website_risk_factor("amazon.com") == 1.5


def test_website_risk_gambling():
    engine = _make_engine()
    assert engine._get_website_risk_factor("online-casino.com") == 2.0


def test_website_risk_educational():
    engine = _make_engine()
    assert engine._get_website_risk_factor("coursera.edu") == 0.5


# ── TTC inverse relationship ──────────────────────────────────────────

def test_ttc_fast_cart_higher_score():
    """Faster time-to-cart should produce a higher impulse score."""
    engine = _make_engine()
    base = {
        "emotion_arousal": 0.5,
        "click_rate": 0.15,
        "scroll_velocity_peak": 600.0,
        "system_time": 12,
        "website_name": "bestbuy",
    }
    score_fast = engine.calculate_p_impulse({**base, "time_to_cart": 5.0})
    score_slow = engine.calculate_p_impulse({**base, "time_to_cart": 500.0})
    assert score_fast > score_slow, (
        f"Fast TTC score ({score_fast}) should exceed slow TTC ({score_slow})"
    )


# ── Z-score edge case ─────────────────────────────────────────────────

def test_z_score_zero_std():
    engine = _make_engine()
    assert engine._calculate_z_score(100.0, 50.0, 0.0) == 0.0


# ── Structured output ─────────────────────────────────────────────────

def test_structured_output_keys():
    engine = _make_engine()
    data = {
        "emotion_arousal": 0.5,
        "click_rate": 0.15,
        "scroll_velocity_peak": 600.0,
        "time_to_cart": 60.0,
        "system_time": 12,
        "website_name": "bestbuy",
    }
    output = engine.get_structured_output(data)
    assert "p_impulse" in output
    assert "dominant_trigger" in output
    assert "logic_summary" in output
    assert "z_scores" in output["logic_summary"]
    assert "likelihoods" in output["logic_summary"]
    assert "weighted_contributions" in output["logic_summary"]
    assert "context_factors" in output["logic_summary"]


def test_dominant_trigger_identification():
    """Dominant trigger must be a known feature key and come from weighted contributions."""
    engine = _make_engine()
    data = {
        "emotion_arousal": 0.9,       # high arousal → should dominate
        "click_rate": 0.15,
        "scroll_velocity_peak": 600.0,
        "time_to_cart": 300.0,
        "system_time": 12,
        "website_name": "bestbuy",
    }
    output = engine.get_structured_output(data)
    valid_triggers = {"scroll_velocity", "emotion_arousal", "click_rate", "time_to_cart"}
    assert output["dominant_trigger"] in valid_triggers
    # With arousal at 0.9 (weight 0.19 → contribution 0.171) it should dominate
    assert output["dominant_trigger"] == "emotion_arousal"
