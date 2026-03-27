# region imports
from AlgorithmImports import *
# endregion
"""Synthetic market data, features, and strategy fixtures for regression tests."""


def make_features(asset_id="ES", **overrides):
    """Synthetic feature dict for one asset."""
    base = {
        "or_range": 5.0,
        "entry_price": 5000.0,
        "vrp": 0.02,
        "pcr": 1.1,
        "gex": -500_000,
        "ivts": 0.85,
        "cot_smi": 0.3,
        "cross_corr_z": 0.5,
        "cross_momentum": 0.6,
        "opex_window": False,
        "spread_z": -0.2,
        "volume_ratio": 1.15,
        "vix_z": 0.8,
        "econ_tier": 0,
        "econ_minutes": 999,
    }
    base.update(overrides)
    return {asset_id: base}


def make_regime_model_binary(asset_id="ES", phi=0.20):
    """Regime model for C4 binary (Pettersson) asset."""
    return {
        asset_id: {
            "model_type": "BINARY_ONLY",
            "pettersson_threshold": phi,
        }
    }


def make_regime_model_neutral(asset_id="ES"):
    """Regime model for REGIME_NEUTRAL asset (P2 locked)."""
    return {
        asset_id: {
            "model_type": "CLASSIFIER",
            "regime_label": "REGIME_NEUTRAL",
            "feature_list": [],
            "classifier_object": None,
        }
    }


def make_locked_strategy(asset_id="ES", **overrides):
    """Locked strategy from P2."""
    base = {
        "threshold": 1.25,  # SL distance in points (P1 median stop_distance=1.31)
        "sl_multiple": 1.0,
        "tp_multiple": 2.0,
        "default_direction": 1,
        "sl_method": "OR_RANGE",
        "entry_conditions": {"breakout": True},
    }
    base.update(overrides)
    return {asset_id: base}


def make_ewma_states(asset_id="ES", win_rate=0.55, avg_win=200.0, avg_loss=100.0,
                     n_trades=50, regime="LOW_VOL", session=1):
    """EWMA states keyed by (asset, regime, session)."""
    return {
        (asset_id, regime, session): {
            "win_rate": win_rate,
            "avg_win": avg_win,
            "avg_loss": avg_loss,
            "n_trades": n_trades,
        }
    }


def make_kelly_params(asset_id="ES", kelly_full=0.10, shrinkage=0.85,
                      regime="LOW_VOL", session=1):
    """Kelly params keyed by (asset, regime, session)."""
    return {
        (asset_id, regime, session): {
            "kelly_full": kelly_full,
            "shrinkage_factor": shrinkage,
        }
    }


def make_assets_detail(asset_id="ES", point_value=50.0, tick_size=0.25):
    """Asset detail dict."""
    return {
        asset_id: {
            "point_value": point_value,
            "tick_size": tick_size,
            "margin_per_contract": 500.0,
        }
    }
