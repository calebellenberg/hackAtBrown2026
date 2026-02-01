"""
ImpulseGuard Bayesian Inference Engine

A high-performance Python inference engine that calculates the probability
that a user is experiencing an "impulse buy" state by combining biometric
data with real-time browser telemetry using Bayesian inference.
"""

import numpy as np
from typing import Dict, Any, Optional
import json


class ImpulseInferenceEngine:
    """
    Bayesian Inference Engine for calculating impulse buy probability.
    
    Uses a weighted likelihood approach to combine noisy biometric and
    behavioral data, accounting for individual baseline differences.
    
    Supports two weight profiles:
    - BEHAVIOR_ONLY_WEIGHTS: Used when biometrics are placeholders (current state)
    - FULL_BIOMETRIC_WEIGHTS: For future use when Presage SDK provides real biometrics
    """
    
    # Flag to indicate whether we're using placeholder biometrics
    # Set to True when Presage SDK is not available or not providing real data
    USE_PLACEHOLDER_BIOMETRICS = True
    
    # Weight profile when biometrics are placeholders (behavior-focused)
    BEHAVIOR_ONLY_WEIGHTS = {
        'heart_rate': 0.03,
        'respiration_rate': 0.03,
        'scroll_velocity': 0.26,
        'emotion_arousal': 0.34,
        'click_rate': 0.17,
        'time_to_cart': 0.17
    }
    
    # Weight profile when real biometrics are available
    FULL_BIOMETRIC_WEIGHTS = {
        'heart_rate': 0.15,
        'respiration_rate': 0.15,
        'scroll_velocity': 0.20,
        'emotion_arousal': 0.20,
        'click_rate': 0.15,
        'time_to_cart': 0.15
    }
    
    # Feature weights for likelihood combination (persage stats weighted very low)
    WEIGHTS = {
        'heart_rate': 0.03,
        'respiration_rate': 0.03,
        'scroll_velocity': 0.26,
        'emotion_arousal': 0.34,
        'click_rate': 0.17,
        'time_to_cart': 0.17
    }
    
    # Dynamic weight selection based on biometric availability
    @classmethod
    def get_weights(cls) -> dict:
        """Get the appropriate weight profile based on biometric availability."""
        if cls.USE_PLACEHOLDER_BIOMETRICS:
            return cls.BEHAVIOR_ONLY_WEIGHTS
        return cls.FULL_BIOMETRIC_WEIGHTS
    
    # Legacy WEIGHTS property for backward compatibility
    @property
    def WEIGHTS(self) -> dict:
        """Get weights dynamically based on biometric availability."""
        return self.get_weights()
    
    # Sigmoid steepness parameter for Z-score to likelihood mapping
    SIGMOID_K = 2.0
    
    # Intervention level thresholds
    INTERVENTION_THRESHOLDS = {
        'NONE': 0.3,
        'NUDGE': 0.6,
        'CHALLENGE': 0.8,
        'LOCKOUT': 1.0
    }
    
    # Website risk factors
    WEBSITE_RISK_FACTORS = {
        # High risk (2.0x)
        'gambling': 2.0,
        'flash_sale': 2.0,
        # Medium-high risk (1.5x) - E-commerce
        'amazon': 1.5,
        'ebay': 1.5,
        'temu': 1.5,
        'shein': 1.5,
        'aliexpress': 1.5,
        # Medium risk (1.0x) - General retail
        'target': 1.0,
        'walmart': 1.0,
        'bestbuy': 1.0,
        'costco': 1.0,
        'wayfair': 1.0,
        'macys': 1.0,
        'kohls': 1.0,
        'newegg': 1.0,
        'zappos': 1.0,
        'nike': 1.0,
        'adidas': 1.0,
        'homedepot': 1.0,
        'lowes': 1.0,
        'ikea': 1.0,
        'etsy': 1.0,
        # Low risk (0.5x) - Educational, planned purchases
        'educational': 0.5,
        'nonprofit': 0.5
    }
    
    def __init__(self, baseline_data: Dict[str, Any], prior_p: float = 0.2):
        """
        Initialize the inference engine with user-specific baselines.
        
        Args:
            baseline_data: JSON-serializable dict with baseline statistics:
                {
                    "heart_rate": {"mean": float, "std": float},
                    "respiration_rate": {"mean": float, "std": float},
                    "scroll_velocity": {"mean": float, "std": float},
                    "click_rate": {"mean": float, "std": float},
                    "time_on_site": {"mean": float, "std": float}
                }
            prior_p: Prior probability of impulse state (default: 0.2)
        """
        self.baseline_data = baseline_data
        self.prior_p = prior_p
        
        # Validate baseline data structure
        required_keys = ['heart_rate', 'respiration_rate', 'scroll_velocity', 
                        'click_rate', 'time_on_site']
        for key in required_keys:
            if key not in baseline_data:
                raise ValueError(f"Missing baseline data for: {key}")
            if 'mean' not in baseline_data[key] or 'std' not in baseline_data[key]:
                raise ValueError(f"Baseline data for {key} must contain 'mean' and 'std'")
    
    def _calculate_z_score(self, value: float, mean: float, std: float) -> float:
        """
        Calculate Z-score for a value relative to baseline.
        
        Args:
            value: Current measurement
            mean: Baseline mean
            std: Baseline standard deviation
            
        Returns:
            Z-score (standard deviations from mean)
        """
        if std == 0:
            return 0.0  # Avoid division by zero
        return (value - mean) / std
    
    def _sigmoid_likelihood(self, z_score: float, k: Optional[float] = None) -> float:
        """
        Map Z-score to likelihood using sigmoid function.
        
        Args:
            z_score: Z-score (standard deviations from baseline)
            k: Steepness parameter (default: self.SIGMOID_K)
            
        Returns:
            Likelihood value in [0, 1]
        """
        if k is None:
            k = self.SIGMOID_K
        return 1.0 / (1.0 + np.exp(-k * z_score))
    
    def _get_late_night_multiplier(self, hour: int) -> float:
        """
        Calculate late night multiplier for hours 1-5 AM.
        
        Args:
            hour: Hour of day (0-23)
            
        Returns:
            Multiplier (1.0-1.5x), peaks at 3 AM
        """
        if 1 <= hour <= 5:
            # Linear interpolation: 1.0x at 1 AM, 1.5x at 3 AM, 1.0x at 5 AM
            return 1.0 + 0.5 * (1 - abs(hour - 3) / 2)
        return 1.0
    
    def _get_website_risk_factor(self, website_name: str) -> float:
        """
        Get risk factor multiplier based on website category.
        
        Args:
            website_name: Name or domain of the website
            
        Returns:
            Risk factor multiplier (0.5-2.0x)
        """
        website_lower = website_name.lower()
        
        # Check for exact matches first
        for key, factor in self.WEBSITE_RISK_FACTORS.items():
            if key in website_lower:
                return factor
        
        # Check for gambling indicators
        gambling_keywords = ['casino', 'bet', 'poker', 'gambling', 'lottery']
        if any(keyword in website_lower for keyword in gambling_keywords):
            return 2.0
        
        # Check for flash sale indicators
        flash_sale_keywords = ['flash', 'limited time', 'sale ends', 'countdown']
        if any(keyword in website_lower for keyword in flash_sale_keywords):
            return 2.0
        
        # Check for educational/non-profit indicators
        edu_keywords = ['edu', 'university', 'school', 'course', 'learn']
        if any(keyword in website_lower for keyword in edu_keywords):
            return 0.5
        
        # Default to medium risk
        return 1.0
    
    def _calculate_ttc_likelihood(self, time_to_cart: float) -> float:
        """
        Calculate likelihood based on Time-to-Cart (TTC).
        Lower TTC indicates higher impulse probability.
        
        Args:
            time_to_cart: Time in seconds from page load to cart addition
            
        Returns:
            Likelihood value in [0, 1]
        """
        # Very fast cart addition (< 60s) = high likelihood
        # Very slow cart addition (> 300s) = low likelihood
        # Use inverse sigmoid: shorter TTC = higher likelihood
        if time_to_cart <= 0:
            return 1.0
        
        # Normalize TTC: 0-60s maps to high likelihood, 300s+ maps to low
        normalized_ttc = min(time_to_cart / 300.0, 1.0)
        # Inverse: lower normalized TTC = higher likelihood
        return 1.0 - normalized_ttc
    
    def calculate_p_impulse(self, current_data: Dict[str, Any]) -> float:
        """
        Calculate the probability that user is in an impulse buy state.
        
        Args:
            current_data: Dictionary containing:
                - heart_rate: float (BPM)
                - respiration_rate: float (RR)
                - emotion_arousal: float (0.0-1.0)
                - click_rate: float (clicks/sec)
                - time_on_website: float (seconds)
                - system_time: int (hour 0-23)
                - scroll_velocity_peak: float (pixels/sec)
                - time_to_cart: float (seconds, TTC)
                - website_name: str
                
        Returns:
            Probability of impulse state [0.0, 1.0]
        """
        # Extract values with defaults
        hr = current_data.get('heart_rate', 0)
        rr = current_data.get('respiration_rate', 0)
        arousal = current_data.get('emotion_arousal', 0.0)
        click_rate = current_data.get('click_rate', 0.0)
        scroll_velocity = current_data.get('scroll_velocity_peak', 0.0)
        time_to_cart = current_data.get('time_to_cart', float('inf'))
        hour = current_data.get('system_time', 12)
        website_name = current_data.get('website_name', '')
        
        # Calculate Z-scores for HR, RR, Scroll Velocity
        hr_z = self._calculate_z_score(
            hr,
            self.baseline_data['heart_rate']['mean'],
            self.baseline_data['heart_rate']['std']
        )
        rr_z = self._calculate_z_score(
            rr,
            self.baseline_data['respiration_rate']['mean'],
            self.baseline_data['respiration_rate']['std']
        )
        scroll_z = self._calculate_z_score(
            scroll_velocity,
            self.baseline_data['scroll_velocity']['mean'],
            self.baseline_data['scroll_velocity']['std']
        )
        
        # Map Z-scores to likelihoods using sigmoid
        hr_likelihood = self._sigmoid_likelihood(hr_z)
        rr_likelihood = self._sigmoid_likelihood(rr_z)
        scroll_likelihood = self._sigmoid_likelihood(scroll_z)
        
        # Emotion arousal is already in [0, 1], use directly
        arousal_likelihood = arousal
        
        # Click rate: calculate Z-score and map to likelihood
        click_z = self._calculate_z_score(
            click_rate,
            self.baseline_data['click_rate']['mean'],
            self.baseline_data['click_rate']['std']
        )
        click_likelihood = self._sigmoid_likelihood(click_z)
        
        # TTC likelihood (inverse: lower TTC = higher likelihood)
        ttc_likelihood = self._calculate_ttc_likelihood(time_to_cart)
        
        # Weighted combination of likelihoods
        weighted_p = (
            self.WEIGHTS['heart_rate'] * hr_likelihood +
            self.WEIGHTS['respiration_rate'] * rr_likelihood +
            self.WEIGHTS['scroll_velocity'] * scroll_likelihood +
            self.WEIGHTS['emotion_arousal'] * arousal_likelihood +
            self.WEIGHTS['click_rate'] * click_likelihood +
            self.WEIGHTS['time_to_cart'] * ttc_likelihood
        )
        
        # Apply context multipliers
        late_night_mult = self._get_late_night_multiplier(hour)
        website_risk = self._get_website_risk_factor(website_name)
        
        # Apply multipliers
        adjusted_p = weighted_p * late_night_mult * website_risk
        
        # Clamp to [0, 1] before Bayesian update
        adjusted_p = max(0.0, min(1.0, adjusted_p))
        
        # Bayesian update: P(impulse | evidence) = P(evidence | impulse) * P(impulse) / P(evidence)
        # Simplified: P_final = (P * prior) / (P * prior + (1-P) * (1-prior))
        numerator = adjusted_p * self.prior_p
        denominator = adjusted_p * self.prior_p + (1 - adjusted_p) * (1 - self.prior_p)
        
        if denominator == 0:
            return 0.0
        
        p_final = numerator / denominator
        
        # Ensure result is in [0, 1]
        return max(0.0, min(1.0, p_final))
    
    def get_intervention_level(self, p_score: float) -> str:
        """
        Determine intervention level based on probability score.
        
        Args:
            p_score: Probability of impulse state [0.0, 1.0]
            
        Returns:
            Intervention level: "NONE", "NUDGE", "CHALLENGE", or "LOCKOUT"
        """
        if p_score < self.INTERVENTION_THRESHOLDS['NONE']:
            return "NONE"
        elif p_score < self.INTERVENTION_THRESHOLDS['NUDGE']:
            return "NUDGE"
        elif p_score < self.INTERVENTION_THRESHOLDS['CHALLENGE']:
            return "CHALLENGE"
        else:
            return "LOCKOUT"
    
    def validate_logic(self, current_data: Dict[str, Any], p_score: float) -> str:
        """
        Validate and explain the logic distinguishing "Happy Excitement"
        from "Impulsive Stress".
        
        Args:
            current_data: Current data dictionary
            p_score: Calculated probability score
            
        Returns:
            Explanation string describing the reasoning
        """
        ttc = current_data.get('time_to_cart', float('inf'))
        arousal = current_data.get('emotion_arousal', 0.0)
        website_name = current_data.get('website_name', '').lower()
        
        # Identify indicators
        happy_excitement_indicators = []
        impulsive_stress_indicators = []
        
        # TTC analysis
        if ttc > 300:
            happy_excitement_indicators.append(f"High TTC ({ttc:.1f}s) suggests planned purchase")
        elif ttc < 60:
            impulsive_stress_indicators.append(f"Low TTC ({ttc:.1f}s) indicates rapid decision-making")
        
        # Arousal analysis
        if arousal < 0.4:
            happy_excitement_indicators.append(f"Low arousal ({arousal:.2f}) suggests calm state")
        elif arousal > 0.7:
            impulsive_stress_indicators.append(f"High arousal ({arousal:.2f}) indicates stress/excitement")
        
        # Website risk analysis
        website_risk = self._get_website_risk_factor(website_name)
        if website_risk >= 1.5:
            impulsive_stress_indicators.append(f"High-risk website (factor: {website_risk:.1f}x)")
        elif website_risk <= 0.5:
            happy_excitement_indicators.append(f"Low-risk website (factor: {website_risk:.1f}x)")
        
        # Build explanation
        explanation_parts = [f"P_impulse = {p_score:.3f}"]
        
        if happy_excitement_indicators:
            explanation_parts.append("Happy Excitement indicators:")
            explanation_parts.extend([f"  - {ind}" for ind in happy_excitement_indicators])
        
        if impulsive_stress_indicators:
            explanation_parts.append("Impulsive Stress indicators:")
            explanation_parts.extend([f"  - {ind}" for ind in impulsive_stress_indicators])
        
        # Final assessment
        if len(impulsive_stress_indicators) > len(happy_excitement_indicators):
            explanation_parts.append("Assessment: Pattern suggests IMPULSIVE STRESS")
        elif len(happy_excitement_indicators) > len(impulsive_stress_indicators):
            explanation_parts.append("Assessment: Pattern suggests HAPPY EXCITEMENT")
        else:
            explanation_parts.append("Assessment: Mixed signals - contextual factors determine classification")
        
        return "\n".join(explanation_parts)
    
    def get_structured_output(self, current_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Get structured JSON output with detailed reasoning.
        
        Args:
            current_data: Current data dictionary
            
        Returns:
            JSON-serializable dict with p_impulse, dominant_trigger, and logic_summary
        """
        # Calculate probability
        p_impulse = self.calculate_p_impulse(current_data)
        
        # Calculate individual components to find dominant trigger
        hr = current_data.get('heart_rate', 0)
        rr = current_data.get('respiration_rate', 0)
        arousal = current_data.get('emotion_arousal', 0.0)
        click_rate = current_data.get('click_rate', 0.0)
        scroll_velocity = current_data.get('scroll_velocity_peak', 0.0)
        time_to_cart = current_data.get('time_to_cart', float('inf'))
        
        # Calculate Z-scores
        hr_z = self._calculate_z_score(
            hr, self.baseline_data['heart_rate']['mean'],
            self.baseline_data['heart_rate']['std']
        )
        rr_z = self._calculate_z_score(
            rr, self.baseline_data['respiration_rate']['mean'],
            self.baseline_data['respiration_rate']['std']
        )
        scroll_z = self._calculate_z_score(
            scroll_velocity, self.baseline_data['scroll_velocity']['mean'],
            self.baseline_data['scroll_velocity']['std']
        )
        click_z = self._calculate_z_score(
            click_rate, self.baseline_data['click_rate']['mean'],
            self.baseline_data['click_rate']['std']
        )
        
        # Calculate likelihoods
        hr_likelihood = self._sigmoid_likelihood(hr_z)
        rr_likelihood = self._sigmoid_likelihood(rr_z)
        scroll_likelihood = self._sigmoid_likelihood(scroll_z)
        arousal_likelihood = arousal
        click_likelihood = self._sigmoid_likelihood(click_z)
        ttc_likelihood = self._calculate_ttc_likelihood(time_to_cart)
        
        # Calculate weighted contributions
        contributions = {
            'heart_rate': self.WEIGHTS['heart_rate'] * hr_likelihood,
            'respiration_rate': self.WEIGHTS['respiration_rate'] * rr_likelihood,
            'scroll_velocity': self.WEIGHTS['scroll_velocity'] * scroll_likelihood,
            'emotion_arousal': self.WEIGHTS['emotion_arousal'] * arousal_likelihood,
            'click_rate': self.WEIGHTS['click_rate'] * click_likelihood,
            'time_to_cart': self.WEIGHTS['time_to_cart'] * ttc_likelihood
        }
        
        # Find dominant trigger
        dominant_trigger = max(contributions, key=contributions.get)
        
        # Get context factors
        hour = current_data.get('system_time', 12)
        website_name = current_data.get('website_name', '')
        late_night_mult = self._get_late_night_multiplier(hour)
        website_risk = self._get_website_risk_factor(website_name)
        
        # Get validation explanation
        validation = self.validate_logic(current_data, p_impulse)
        
        return {
            'p_impulse': float(p_impulse),
            'dominant_trigger': dominant_trigger,
            'logic_summary': {
                'z_scores': {
                    'heart_rate': float(hr_z),
                    'respiration_rate': float(rr_z),
                    'scroll_velocity': float(scroll_z),
                    'click_rate': float(click_z)
                },
                'likelihoods': {
                    'heart_rate': float(hr_likelihood),
                    'respiration_rate': float(rr_likelihood),
                    'scroll_velocity': float(scroll_likelihood),
                    'emotion_arousal': float(arousal_likelihood),
                    'click_rate': float(click_likelihood),
                    'time_to_cart': float(ttc_likelihood)
                },
                'weighted_contributions': {
                    k: float(v) for k, v in contributions.items()
                },
                'context_factors': {
                    'late_night_multiplier': float(late_night_mult),
                    'website_risk_factor': float(website_risk),
                    'system_time': hour,
                    'website_name': website_name
                },
                'validation': validation
            }
        }
