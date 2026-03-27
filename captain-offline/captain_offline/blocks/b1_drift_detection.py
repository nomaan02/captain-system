# region imports
try:
    from AlgorithmImports import *
except ImportError:
    pass
# endregion
"""Per-AIM Drift Detection — P3-PG-04 (Task 2.1d / OFF lines 254-276).

Daily check: for each ACTIVE AIM, use AutoEncoder reconstruction error
monitored by ADWIN to detect concept drift in input features.

On drift detected:
  1. Flag AIM for retraining
  2. Reduce inclusion_probability by 50%
  3. Renormalise all DMA weights
"""

import json
import logging
from collections import deque

from shared.questdb_client import get_cursor

from captain_offline.blocks.version_snapshot import snapshot_before_update

logger = logging.getLogger(__name__)

# Drift reduction factor: multiply inclusion_probability by this on drift
DRIFT_REDUCTION_FACTOR = 0.5

# ADWIN parameters
ADWIN_DELTA = 0.002  # confidence parameter for change detection


class ADWINDetector:
    """Adaptive Windowing (ADWIN) change detector.

    Wraps river.drift.ADWIN (Bifet & Gavalda, 2007) which maintains a
    variable-length window of recent values and detects distributional
    change by comparing sub-windows with Hoeffding-style bounds.

    The river implementation handles adaptive bucket compression, so it's
    both more accurate and more memory-efficient than a naive two-window test.
    """

    def __init__(self, delta: float = ADWIN_DELTA):
        self.delta = delta
        try:
            from river.drift import ADWIN as _RiverADWIN
            self._detector = _RiverADWIN(delta=delta)
            self._use_river = True
        except ImportError:
            # Fallback: simple two-window comparison if river not available
            self._detector = None
            self._use_river = False
            self._window = deque(maxlen=500)
            self._count = 0
            logger.warning("river.drift.ADWIN not available, using fallback detector")

    def add(self, value: float) -> bool:
        """Add a value and return True if change detected."""
        if self._use_river:
            self._detector.update(value)
            return self._detector.drift_detected
        else:
            # Fallback: simplified two-window Hoeffding test
            self._window.append(value)
            self._count += 1
            if self._count < 30:
                return False
            n = len(self._window)
            mid = n // 2
            left = list(self._window)[:mid]
            right = list(self._window)[mid:]
            if not left or not right:
                return False
            mean_left = sum(left) / len(left)
            mean_right = sum(right) / len(right)
            eps = ((1.0 / (2.0 * len(left))) + (1.0 / (2.0 * len(right)))) ** 0.5
            eps *= (4.0 / self.delta) ** 0.5
            return abs(mean_left - mean_right) > eps


class SimpleAutoEncoder:
    """Simplified AutoEncoder for feature drift detection.

    Stores mean/std of training features. Reconstruction error = sum of
    squared z-scores. In production, replace with a trained neural autoencoder.
    """

    def __init__(self):
        self.mean = None
        self.std = None
        self.fitted = False

    def fit(self, features: list[list[float]]):
        """Fit on historical feature values."""
        import numpy as np
        arr = np.array(features)
        self.mean = np.mean(arr, axis=0)
        self.std = np.std(arr, axis=0) + 1e-8
        self.fitted = True

    def reconstruction_error(self, features: list[float]) -> float:
        """Compute reconstruction error (sum of squared z-scores)."""
        if not self.fitted:
            return 0.0
        import numpy as np
        z = (np.array(features) - self.mean) / self.std
        return float(np.sum(z ** 2))


# In-memory storage for detector states (per AIM per asset)
# In production, these are persisted in P3-D04.adwin_states
_adwin_states: dict[tuple[int, str], ADWINDetector] = {}
_autoencoder_states: dict[tuple[int, str], SimpleAutoEncoder] = {}


def _get_adwin(aim_id: int, asset_id: str) -> ADWINDetector:
    key = (aim_id, asset_id)
    if key not in _adwin_states:
        _adwin_states[key] = ADWINDetector()
    return _adwin_states[key]


def _get_autoencoder(aim_id: int, asset_id: str) -> SimpleAutoEncoder:
    key = (aim_id, asset_id)
    if key not in _autoencoder_states:
        _autoencoder_states[key] = SimpleAutoEncoder()
    return _autoencoder_states[key]


def _renormalise_weights(asset_id: str):
    """Renormalise all AIM weights for an asset to sum to 1.0."""
    with get_cursor() as cur:
        cur.execute(
            """SELECT aim_id, inclusion_probability FROM p3_d02_aim_meta_weights
               WHERE asset_id = %s ORDER BY aim_id""",
            (asset_id,),
        )
        rows = cur.fetchall()

    if not rows:
        return

    # Deduplicate by aim_id (take first = latest due to QuestDB ordering)
    by_aim = {}
    for r in rows:
        if r[0] not in by_aim:
            by_aim[r[0]] = r[1]

    total = sum(by_aim.values())
    if total <= 0:
        return

    with get_cursor() as cur:
        for aid, prob in by_aim.items():
            new_prob = prob / total
            cur.execute(
                """INSERT INTO p3_d02_aim_meta_weights
                   (aim_id, asset_id, inclusion_probability, inclusion_flag,
                    recent_effectiveness, days_below_threshold, last_updated)
                   VALUES (%s, %s, %s, %s, 0.0, 0, now())""",
                (aid, asset_id, new_prob, new_prob > 0.02),
            )


def run_drift_detection(asset_id: str, aim_features: dict[int, list[float]]):
    """Execute P3-PG-04: daily drift detection for all active AIMs.

    Args:
        asset_id: Asset being checked
        aim_features: Dict mapping aim_id -> current feature vector
    """
    drifted_aims = []

    for aim_id, features in aim_features.items():
        ae = _get_autoencoder(aim_id, asset_id)
        adwin = _get_adwin(aim_id, asset_id)

        if not ae.fitted:
            continue  # no baseline yet — skip

        error = ae.reconstruction_error(features)
        change_detected = adwin.add(error)

        if change_detected:
            drifted_aims.append(aim_id)
            logger.warning("Concept drift detected in AIM-%d [%s]", aim_id, asset_id)

            # Snapshot before modifying weights
            snapshot_before_update("P3-D02", "DMA_UPDATE",
                                   {"aim_id": aim_id, "reason": "drift_detected"})

            # Reduce inclusion_probability by 50%
            with get_cursor() as cur:
                cur.execute(
                    """SELECT inclusion_probability FROM p3_d02_aim_meta_weights
                       WHERE aim_id = %s AND asset_id = %s
                       ORDER BY last_updated DESC LIMIT 1""",
                    (aim_id, asset_id),
                )
                row = cur.fetchone()
                if row:
                    new_prob = row[0] * DRIFT_REDUCTION_FACTOR
                    cur.execute(
                        """INSERT INTO p3_d02_aim_meta_weights
                           (aim_id, asset_id, inclusion_probability, inclusion_flag,
                            recent_effectiveness, days_below_threshold, last_updated)
                           VALUES (%s, %s, %s, %s, 0.0, 0, now())""",
                        (aim_id, asset_id, new_prob, new_prob > 0.02),
                    )

    if drifted_aims:
        # Renormalise all weights after drift reductions
        _renormalise_weights(asset_id)
        logger.info("Drift detection for %s: %d AIMs flagged, weights renormalised",
                     asset_id, len(drifted_aims))
