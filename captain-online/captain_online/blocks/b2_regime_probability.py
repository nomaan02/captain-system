# region imports
try:
    from AlgorithmImports import *
except ImportError:
    pass
# endregion
"""ON-B2: Regime Probability Computation — P3-PG-22 (Task 3.2 / ON lines 616-656).

Classifies current market regime using P2's locked regime classifier.

Two paths:
  C4 assets (BINARY_ONLY): Pettersson binary rule — sigma_t vs phi threshold
  C1-C3 assets: Trained XGBoost classifier from P2-D07

Outputs:
  regime_probs: {asset_id: {HIGH_VOL: p, LOW_VOL: 1-p}}
  regime_uncertain: {asset_id: bool} — True if max_prob < 0.6

Reads: P2-D07 (regime models via B1), features (from B1)
Writes: nothing (pure computation)
"""

import logging
import math
from typing import Optional

logger = logging.getLogger(__name__)


def run_regime_probability(
    active_assets: list[str],
    features: dict,
    regime_models: dict,
) -> dict:
    """P3-PG-22: Compute regime probabilities for all active assets.

    Args:
        active_assets: list of asset_id strings
        features: {asset_id: {feature_name: value}} from Block 1
        regime_models: {asset_id: {model_type, feature_list, pettersson_threshold, ...}}

    Returns:
        dict with:
          regime_probs: {asset_id: {HIGH_VOL: float, LOW_VOL: float}}
          regime_uncertain: {asset_id: bool}
    """
    regime_probs = {}
    regime_uncertain = {}

    for asset_id in active_assets:
        model = regime_models.get(asset_id)

        if model is None:
            # No regime model — default to REGIME_NEUTRAL (equal probs)
            regime_probs[asset_id] = {"HIGH_VOL": 0.5, "LOW_VOL": 0.5}
            regime_uncertain[asset_id] = True
            logger.warning("ON-B2: No regime model for %s — using neutral", asset_id)
            continue

        model_type = model.get("model_type", "BINARY_ONLY")

        if model_type == "BINARY_ONLY":
            # C4 asset: Pettersson binary rule
            probs = _binary_regime(asset_id, features, model)
        else:
            # C1-C3: trained classifier
            probs = _classifier_regime(asset_id, features, model)

        if probs is None:
            # Fallback on failure
            probs = {"HIGH_VOL": 0.5, "LOW_VOL": 0.5}
            regime_uncertain[asset_id] = True
            logger.warning("ON-B2: Regime computation failed for %s — using neutral", asset_id)
        else:
            regime_probs[asset_id] = probs
            max_prob = max(probs.values())
            regime_uncertain[asset_id] = (max_prob < 0.6)

            if regime_uncertain[asset_id]:
                logger.info("ON-B2: Regime uncertainty for %s: max_prob=%.3f — robust Kelly will be used",
                            asset_id, max_prob)

        regime_probs[asset_id] = probs

    logger.info("ON-B2: Regime probabilities computed for %d assets (%d uncertain)",
                len(regime_probs),
                sum(1 for v in regime_uncertain.values() if v))

    return {
        "regime_probs": regime_probs,
        "regime_uncertain": regime_uncertain,
    }


def _binary_regime(asset_id: str, features: dict, model: dict) -> Optional[dict]:
    """C4 Pettersson binary rule: sigma_t vs phi threshold.

    Per spec: sigma_today = compute_realised_vol(features[u])
    phi = classifier.pettersson_threshold (stored in P2-D07)
    """
    phi = model.get("pettersson_threshold")
    if phi is None:
        logger.warning("ON-B2: No pettersson_threshold for %s", asset_id)
        return None

    # sigma_t from realised vol (P2-D01 EWMA-based)
    sigma_today = _compute_realised_vol(asset_id, features)

    if sigma_today is None:
        logger.warning("ON-B2: Cannot compute realised vol for %s — no binary regime", asset_id)
        return None

    if sigma_today > phi:
        return {"HIGH_VOL": 1.0, "LOW_VOL": 0.0}
    else:
        return {"HIGH_VOL": 0.0, "LOW_VOL": 1.0}


def _compute_realised_vol(asset_id: str, features: dict) -> Optional[float]:
    """Compute realised volatility for Pettersson binary rule.

    Uses daily returns from the last 20 days to estimate annualised RV.
    Fallback to VRP-derived RV if available.
    """
    from captain_online.blocks.b1_features import _get_daily_returns
    import numpy as np

    returns = _get_daily_returns(asset_id, lookback=20)
    if returns is not None and len(returns) >= 10:
        return float(np.std(returns) * math.sqrt(252))

    # Fallback: if VRP was computed, rv = vrp + iv
    asset_features = features.get(asset_id, {})
    vrp = asset_features.get("vrp")
    if vrp is not None:
        # VRP = rv - iv, so rv = vrp + iv. We don't have iv separately,
        # but the sign of VRP tells us about relative vol.
        # Without iv, we cannot reconstruct rv exactly — return None
        pass

    return None


def _classifier_regime(asset_id: str, features: dict, model: dict) -> Optional[dict]:
    """C1-C3: Use trained classifier from P2-D07.

    The classifier object is stored as serialised bytes in the model.
    For V1, we use the locked regime label from P2 (REGIME_NEUTRAL).
    """
    regime_label = model.get("regime_label", "REGIME_NEUTRAL")

    # Attempt classifier inference first if a trained model is available
    classifier_obj = model.get("classifier_object")
    if classifier_obj is not None:
        from captain_online.blocks.b1_features import extract_classifier_features
        feature_vector = extract_classifier_features(asset_id, features, model)

        if any(v is None for v in feature_vector):
            missing = [model["feature_list"][i] for i, v in enumerate(feature_vector) if v is None]
            logger.warning("ON-B2: Missing classifier features for %s: %s — falling back to regime label", asset_id, missing)
        else:
            try:
                import numpy as np
                X = np.array([feature_vector])
                proba = classifier_obj.predict_proba(X)[0]
                # Class ordering: [LOW_VOL, HIGH_VOL]
                return {"LOW_VOL": float(proba[0]), "HIGH_VOL": float(proba[1])}
            except Exception as e:
                logger.error("ON-B2: Classifier failed for %s: %s — falling back to regime label", asset_id, e)

    # No classifier object or classifier failed — fall back to regime label from P2
    if regime_label == "HIGH_VOL":
        return {"HIGH_VOL": 1.0, "LOW_VOL": 0.0}
    elif regime_label == "LOW_VOL":
        return {"HIGH_VOL": 0.0, "LOW_VOL": 1.0}
    else:
        logger.info("ON-B2: No classifier for %s, regime=%s — equal probs", asset_id, regime_label)
        return {"HIGH_VOL": 0.5, "LOW_VOL": 0.5}


def argmax_regime(regime_probs: dict) -> str:
    """Return the regime with highest probability."""
    if not regime_probs:
        return "LOW_VOL"
    return max(regime_probs, key=regime_probs.get)
