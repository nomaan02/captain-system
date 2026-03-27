# region imports
try:
    from AlgorithmImports import *
except ImportError:
    pass
# endregion
"""Two-Sided CUSUM Decay Monitor — P3-PG-06 + P3-PG-07 (Tasks 2.2b, 2.2c).

Distribution-free CUSUM for persistent mean shift detection.
Complementary to BOCPD (simpler, only detects mean changes).

P3-PG-06: Per-trade CUSUM update with sequential control limits.
P3-PG-07: Bootstrap calibration (B=2000, ARL_0=200), run quarterly.

Reads: P3-D03 (trade outcomes), P3-D04 (prior CUSUM state)
Writes: P3-D04 (updated CUSUM state)
"""

import json
import logging
import random

import numpy as np

from shared.questdb_client import get_cursor

logger = logging.getLogger(__name__)

# Calibration parameters
BOOTSTRAP_B = 2000
ARL_0 = 200
MAX_SPRINT = 100


class CUSUMDetector:
    """Two-sided CUSUM with sequential control limits."""

    def __init__(self, allowance: float = 0.0, default_limit: float = 5.0):
        self.c_up: float = 0.0
        self.c_down: float = 0.0
        self.sprint_length: int = 0
        self.allowance: float = allowance  # k = delta/2
        self.sequential_limits: dict[int, float] = {}
        self.default_limit: float = default_limit

    def initialize(self, in_control_returns: list[float]):
        """Set allowance from in-control data variance."""
        if len(in_control_returns) < 2:
            return
        std = float(np.std(in_control_returns))
        self.allowance = std / 2.0  # k = delta/2 where delta ≈ std

    def update(self, x: float) -> str:
        """Process one observation. Returns 'BREACH' or 'OK'.

        Two-sided CUSUM:
          C_up   = max(0, C_up_prev + x - k)
          C_down = max(0, C_down_prev - x - k)
        """
        self.c_up = max(0.0, self.c_up + x - self.allowance)
        self.c_down = max(0.0, self.c_down - x - self.allowance)

        # Sprint length tracking
        if self.c_up == 0.0 and self.c_down == 0.0:
            self.sprint_length = 0
        else:
            self.sprint_length += 1

        # Check against sequential control limit
        h = self.sequential_limits.get(self.sprint_length, self.default_limit)

        if self.c_up > h or self.c_down > h:
            # Reset after breach
            self.c_up = 0.0
            self.c_down = 0.0
            self.sprint_length = 0
            return "BREACH"

        return "OK"

    def to_dict(self) -> dict:
        return {
            "c_up": self.c_up,
            "c_down": self.c_down,
            "sprint_length": self.sprint_length,
            "allowance": self.allowance,
            "sequential_limits": {str(k): v for k, v in self.sequential_limits.items()},
        }

    @classmethod
    def from_dict(cls, data: dict) -> "CUSUMDetector":
        det = cls(allowance=data.get("allowance", 0.0))
        det.c_up = data.get("c_up", 0.0)
        det.c_down = data.get("c_down", 0.0)
        det.sprint_length = data.get("sprint_length", 0)
        det.sequential_limits = {int(k): v for k, v in data.get("sequential_limits", {}).items()}
        return det


def calibrate_cusum_limits(in_control_pnl: list[float],
                            B: int = BOOTSTRAP_B,
                            arl_0: int = ARL_0) -> dict[int, float]:
    """P3-PG-07: Bootstrap calibration of sequential control limits.

    For each sprint length j, determine control limit h(j) such that
    the average run length under the null is ARL_0.

    Args:
        in_control_pnl: P&L values from the in-control period
        B: Number of bootstrap resamples
        arl_0: Target average run length under null

    Returns:
        Dict mapping sprint_length -> control_limit
    """
    n = len(in_control_pnl)
    if n < 20:
        logger.warning("CUSUM calibration: insufficient data (%d < 20)", n)
        return {}

    allowance = float(np.std(in_control_pnl)) / 2.0
    percentile = 100.0 * (1.0 - 1.0 / arl_0)

    # Collect CUSUM values at each sprint length across bootstrap resamples
    cusum_by_sprint: dict[int, list[float]] = {}

    for _ in range(B):
        resample = random.choices(in_control_pnl, k=n)
        c_up = 0.0
        c_down = 0.0
        sprint = 0

        for x in resample:
            c_up = max(0.0, c_up + x - allowance)
            c_down = max(0.0, c_down - x - allowance)

            if c_up == 0.0 and c_down == 0.0:
                sprint = 0
            else:
                sprint += 1

            if sprint > 0 and sprint <= MAX_SPRINT:
                cusum_by_sprint.setdefault(sprint, []).append(max(c_up, c_down))

    # For each sprint length, compute control limit at target percentile
    sequential_limits = {}
    for j in range(1, MAX_SPRINT + 1):
        values = cusum_by_sprint.get(j, [])
        if len(values) >= 10:
            sequential_limits[j] = float(np.percentile(values, percentile))

    logger.info("CUSUM calibration: %d sprint lengths calibrated (B=%d, ARL_0=%d)",
                len(sequential_limits), B, arl_0)
    return sequential_limits


def calibrate_and_persist(asset_id: str, in_control_pnl: list[float],
                           B: int = BOOTSTRAP_B, arl_0: int = ARL_0):
    """Calibrate CUSUM limits and persist to P3-D04. Run quarterly.

    Args:
        asset_id: Asset to calibrate
        in_control_pnl: In-control P&L values
        B: Bootstrap resamples
        arl_0: Target ARL under null
    """
    limits = calibrate_cusum_limits(in_control_pnl, B, arl_0)
    if not limits:
        return

    with get_cursor() as cur:
        cur.execute(
            """INSERT INTO p3_d04_decay_detector_states
               (asset_id, cusum_sequential_limits, cusum_allowance, last_updated)
               VALUES (%s, %s, %s, now())""",
            (asset_id, json.dumps({str(k): v for k, v in limits.items()}),
             float(np.std(in_control_pnl)) / 2.0),
        )
    logger.info("CUSUM limits persisted to P3-D04 for %s (%d limits)", asset_id, len(limits))


def run_cusum_update(asset_id: str, pnl_per_contract: float,
                      detector: CUSUMDetector | None = None) -> tuple[str, CUSUMDetector]:
    """Execute P3-PG-06 for one trade.

    Args:
        asset_id: Asset being monitored
        pnl_per_contract: Per-contract P&L
        detector: Existing detector state (or None to create)

    Returns:
        ("BREACH" or "OK", detector)
    """
    if detector is None:
        detector = CUSUMDetector()

    signal = detector.update(pnl_per_contract)

    # Store to P3-D04
    with get_cursor() as cur:
        cur.execute(
            """INSERT INTO p3_d04_decay_detector_states
               (asset_id, cusum_c_up_prev, cusum_c_down_prev,
                cusum_sprint_length, cusum_allowance,
                cusum_sequential_limits, last_updated)
               VALUES (%s, %s, %s, %s, %s, %s, now())""",
            (asset_id, detector.c_up, detector.c_down,
             detector.sprint_length, detector.allowance,
             json.dumps(detector.to_dict()["sequential_limits"])),
        )

    if signal == "BREACH":
        logger.warning("CUSUM BREACH for %s", asset_id)

    return signal, detector
