# region imports
from AlgorithmImports import *
# endregion
"""Scenarios 1-3: Regime Probability (ON-B2) regression tests."""

import math
from unittest.mock import patch, MagicMock

import pytest

from captain_online.blocks.b2_regime_probability import (
    run_regime_probability, _binary_regime, _classifier_regime, argmax_regime,
)
from tests.fixtures.synthetic_data import (
    make_features, make_regime_model_binary, make_regime_model_neutral,
)


class TestBinaryRegimeHighVol:
    """Scenario 1: sigma > phi -> HIGH_VOL."""

    def test_binary_high_vol(self):
        features = make_features("ES")
        model = {"model_type": "BINARY_ONLY", "pettersson_threshold": 0.20}

        # Mock realised vol to return sigma=0.25 (> phi=0.20)
        with patch(
            "captain_online.blocks.b2_regime_probability._compute_realised_vol",
            return_value=0.25,
        ):
            result = _binary_regime("ES", features, model)

        assert result == {"HIGH_VOL": 1.0, "LOW_VOL": 0.0}

    def test_full_run_binary_high_vol(self):
        features = make_features("ES")
        models = {"ES": {"model_type": "BINARY_ONLY", "pettersson_threshold": 0.20}}

        with patch(
            "captain_online.blocks.b2_regime_probability._compute_realised_vol",
            return_value=0.25,
        ):
            result = run_regime_probability(["ES"], features, models)

        assert result["regime_probs"]["ES"] == {"HIGH_VOL": 1.0, "LOW_VOL": 0.0}
        assert result["regime_uncertain"]["ES"] is False


class TestBinaryRegimeLowVol:
    """Scenario 2: sigma < phi -> LOW_VOL."""

    def test_binary_low_vol(self):
        features = make_features("ES")
        model = {"model_type": "BINARY_ONLY", "pettersson_threshold": 0.20}

        with patch(
            "captain_online.blocks.b2_regime_probability._compute_realised_vol",
            return_value=0.15,
        ):
            result = _binary_regime("ES", features, model)

        assert result == {"HIGH_VOL": 0.0, "LOW_VOL": 1.0}

    def test_full_run_binary_low_vol(self):
        features = make_features("ES")
        models = {"ES": {"model_type": "BINARY_ONLY", "pettersson_threshold": 0.20}}

        with patch(
            "captain_online.blocks.b2_regime_probability._compute_realised_vol",
            return_value=0.15,
        ):
            result = run_regime_probability(["ES"], features, models)

        assert result["regime_probs"]["ES"] == {"HIGH_VOL": 0.0, "LOW_VOL": 1.0}
        assert result["regime_uncertain"]["ES"] is False


class TestRegimeNeutralFallback:
    """Scenario 3: REGIME_NEUTRAL -> equal probs, uncertain=True."""

    def test_classifier_neutral(self):
        features = make_features("ES")
        model = {
            "model_type": "CLASSIFIER",
            "regime_label": "REGIME_NEUTRAL",
            "feature_list": [],
            "classifier_object": None,
        }

        result = _classifier_regime("ES", features, model)
        assert result == {"HIGH_VOL": 0.5, "LOW_VOL": 0.5}

    def test_full_run_neutral(self):
        models = make_regime_model_neutral("ES")
        features = make_features("ES")

        result = run_regime_probability(["ES"], features, models)

        assert result["regime_probs"]["ES"] == {"HIGH_VOL": 0.5, "LOW_VOL": 0.5}
        assert result["regime_uncertain"]["ES"] is True

    def test_no_model_fallback(self):
        """No model at all -> neutral + uncertain."""
        result = run_regime_probability(["ES"], make_features("ES"), {})

        assert result["regime_probs"]["ES"] == {"HIGH_VOL": 0.5, "LOW_VOL": 0.5}
        assert result["regime_uncertain"]["ES"] is True


class TestArgmaxRegime:
    """Helper function tests."""

    def test_high_vol_dominant(self):
        assert argmax_regime({"HIGH_VOL": 0.8, "LOW_VOL": 0.2}) == "HIGH_VOL"

    def test_equal_probs(self):
        # With equal probs, max returns first key in iteration order
        result = argmax_regime({"HIGH_VOL": 0.5, "LOW_VOL": 0.5})
        assert result in ("HIGH_VOL", "LOW_VOL")

    def test_empty_fallback(self):
        assert argmax_regime({}) == "LOW_VOL"
