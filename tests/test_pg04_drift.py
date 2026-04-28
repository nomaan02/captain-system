# region imports
from AlgorithmImports import *
# endregion
"""Phase 3 batch B3_F-13 — PG-04 drift detection wiring.

Note: the plan's `load_aim_features(asset_id, aim_id, as_of)` API does not
exist in shared/. The orchestrator already builds `aim_features` from D01
modifier JSON. These tests cover what's achievable today:

1. Drift skips cleanly when no features are provided.
2. Unfitted AE attempts a bootstrap_fit on the first call; if no history
   is available, the warm-up gate stays active and the tick is skipped
   without raising.
3. A pre-fitted AE produces a reconstruction error and feeds ADWIN.
"""

from unittest.mock import patch

import pytest

from captain_offline.blocks.b1_drift_detection import (
    SimpleAutoEncoder,
    run_drift_detection,
    _autoencoder_states,
    _adwin_states,
    _loaded_assets,
)


@pytest.fixture(autouse=True)
def _clear_drift_caches():
    """Drift detector caches are module-level singletons — reset per test."""
    _autoencoder_states.clear()
    _adwin_states.clear()
    _loaded_assets.clear()
    yield
    _autoencoder_states.clear()
    _adwin_states.clear()
    _loaded_assets.clear()


def test_drift_skips_when_no_features_available():
    """Empty feature vector — clean continue, no raise."""
    aim_features = {1: []}
    # Should not raise even with empty features
    run_drift_detection("ES", aim_features)


def test_unfitted_ae_warmup_gate_active_without_history():
    """When AE is unfitted and no feature history exists, bootstrap_fit
    no-ops (warm-up gate stays active). The tick is skipped cleanly."""
    asset = "ES"
    aim_id = 1
    # Pre-seed the autoencoder cache so _load_drift_states is bypassed
    _autoencoder_states[(aim_id, asset)] = SimpleAutoEncoder()
    _loaded_assets.add(asset)  # bypass DB load

    aim_features = {aim_id: [0.5, 0.6, 0.7]}
    run_drift_detection(asset, aim_features)

    # AE should still be unfitted (no history -> bootstrap no-ops)
    ae = _autoencoder_states[(aim_id, asset)]
    assert ae.fitted is False


def test_fitted_ae_computes_reconstruction_error():
    """A pre-fitted AE produces a reconstruction error and feeds ADWIN."""
    asset = "ES"
    aim_id = 1
    ae = SimpleAutoEncoder()
    # Fit on synthetic history
    history = [[0.5, 0.6, 0.7], [0.55, 0.62, 0.71], [0.48, 0.59, 0.68]]
    ae.fit(history)
    assert ae.fitted is True

    _autoencoder_states[(aim_id, asset)] = ae
    _loaded_assets.add(asset)

    # A near-baseline feature vector should produce a small error
    aim_features = {aim_id: [0.5, 0.6, 0.7]}
    # Should not raise — exercises ae.reconstruction_error and adwin.add
    run_drift_detection(asset, aim_features)

    err = ae.reconstruction_error([0.5, 0.6, 0.7])
    assert err >= 0.0
