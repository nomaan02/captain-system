# region imports
try:
    from AlgorithmImports import *
except ImportError:
    pass
# endregion
"""BOCPD Decay Monitor — P3-PG-05 (Task 2.2a / OFF lines 300-351).

Bayesian Online Changepoint Detection (Adams & MacKay 2007).
Maintains posterior over run length r_t (trades since last changepoint).

Predictive: Student-t from Normal-Inverse-Gamma conjugate prior.
Hazard rate: 1/200 (configurable).
Max run length: 500.

cp_probability = posterior[0] = mass at r=0 (probability of changepoint NOW).

Reads: P3-D03 (trade outcomes), P3-D04 (prior state)
Writes: P3-D04 (updated BOCPD state)
"""

import json
import math
import logging
from dataclasses import dataclass, field

import numpy as np
from scipy import stats as sp_stats

from shared.questdb_client import get_cursor

logger = logging.getLogger(__name__)

# BOCPD parameters
DEFAULT_HAZARD_RATE = 1.0 / 200
MAX_RUN_LENGTH = 500


@dataclass
class NIGPrior:
    """Normal-Inverse-Gamma sufficient statistics."""
    mu: float = 0.0
    kappa: float = 1.0
    alpha: float = 1.0
    beta: float = 1.0


def _student_t_pdf(x: float, prior: NIGPrior) -> float:
    """Compute Student-t predictive probability P(x | NIG prior).

    df = 2 * alpha
    loc = mu
    scale = sqrt(beta * (kappa + 1) / (alpha * kappa))
    """
    df = 2.0 * prior.alpha
    loc = prior.mu
    scale_sq = prior.beta * (prior.kappa + 1.0) / (prior.alpha * prior.kappa)
    scale = math.sqrt(max(scale_sq, 1e-10))
    return float(sp_stats.t.pdf(x, df=df, loc=loc, scale=scale))


def _update_nig(prior: NIGPrior, x: float) -> NIGPrior:
    """Update NIG sufficient statistics with new observation."""
    kappa_new = prior.kappa + 1.0
    mu_new = (prior.kappa * prior.mu + x) / kappa_new
    alpha_new = prior.alpha + 0.5
    beta_new = prior.beta + 0.5 * prior.kappa * (x - prior.mu) ** 2 / kappa_new
    return NIGPrior(mu=mu_new, kappa=kappa_new, alpha=alpha_new, beta=beta_new)


class BOCPDDetector:
    """Online Bayesian Changepoint Detection."""

    def __init__(self, hazard_rate: float = DEFAULT_HAZARD_RATE,
                 max_run_length: int = MAX_RUN_LENGTH):
        self.hazard_rate = hazard_rate
        self.max_run_length = max_run_length
        self.run_length_posterior = np.zeros(max_run_length + 1)
        self.run_length_posterior[0] = 1.0
        self.priors: list[NIGPrior] = [NIGPrior() for _ in range(max_run_length + 1)]
        self.cp_probability = 0.0
        self.cp_history: list[float] = []

    def initialize(self, in_control_returns: list[float]):
        """Initialize from in-control data."""
        if len(in_control_returns) < 2:
            return
        mu_0 = float(np.mean(in_control_returns))
        var_0 = float(np.var(in_control_returns))
        for i in range(len(self.priors)):
            self.priors[i] = NIGPrior(mu=mu_0, kappa=1.0, alpha=1.0, beta=max(var_0, 0.01))

    def update(self, x: float) -> float:
        """Process one observation, return changepoint probability.

        Core recursion (Adams & MacKay 2007):
        1. Compute predictive prob for each run length
        2. Growth: P(r+1) = P(r) * pred * (1-H)
        3. Changepoint: P(0) = sum(P(r) * pred * H)
        4. Normalise
        5. Update sufficient stats
        """
        T = min(len(self.run_length_posterior), self.max_run_length + 1)
        new_joint = np.zeros(T + 1)

        # Step 1-2: Growth probabilities
        for r in range(T):
            if self.run_length_posterior[r] < 1e-300:
                continue
            pred = _student_t_pdf(x, self.priors[r])
            pred = max(pred, 1e-300)
            new_joint[r + 1] += self.run_length_posterior[r] * pred * (1 - self.hazard_rate)
            new_joint[0] += self.run_length_posterior[r] * pred * self.hazard_rate

        # Step 3: Normalise
        evidence = new_joint.sum()
        if evidence > 0:
            new_joint /= evidence

        # Truncate to max_run_length
        if len(new_joint) > self.max_run_length + 1:
            new_joint = new_joint[: self.max_run_length + 1]
            s = new_joint.sum()
            if s > 0:
                new_joint /= s

        # Step 4: Update sufficient stats (shift forward)
        new_priors = [NIGPrior(mu=x, kappa=1.0, alpha=1.0, beta=0.01)]
        for r in range(min(T, self.max_run_length)):
            new_priors.append(_update_nig(self.priors[r], x))
        # Pad if needed
        while len(new_priors) < self.max_run_length + 1:
            new_priors.append(NIGPrior())

        self.priors = new_priors
        self.run_length_posterior = new_joint
        self.cp_probability = float(new_joint[0])
        self.cp_history.append(self.cp_probability)

        return self.cp_probability

    def to_dict(self) -> dict:
        """Serialize state for storage."""
        return {
            "cp_probability": self.cp_probability,
            "cp_history": self.cp_history[-100:],  # keep last 100
            "hazard_rate": self.hazard_rate,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "BOCPDDetector":
        """Deserialize from stored state."""
        det = cls(hazard_rate=data.get("hazard_rate", DEFAULT_HAZARD_RATE))
        det.cp_probability = data.get("cp_probability", 0.0)
        det.cp_history = data.get("cp_history", [])
        return det


def run_bocpd_update(asset_id: str, pnl_per_contract: float,
                      detector: BOCPDDetector | None = None) -> tuple[float, BOCPDDetector]:
    """Execute P3-PG-05 for one trade.

    Args:
        asset_id: Asset being monitored
        pnl_per_contract: Per-contract P&L (removes sizing bias)
        detector: Existing detector state (or None to load from DB)

    Returns:
        (cp_probability, detector)
    """
    if detector is None:
        detector = BOCPDDetector()

    cp_prob = detector.update(pnl_per_contract)

    # Store to P3-D04
    with get_cursor() as cur:
        cur.execute(
            """INSERT INTO p3_d04_decay_detector_states
               (asset_id, bocpd_cp_probability, bocpd_cp_history,
                current_changepoint_probability, last_updated)
               VALUES (%s, %s, %s, %s, now())""",
            (asset_id, cp_prob, json.dumps(detector.cp_history[-100:]), cp_prob),
        )

    logger.debug("BOCPD %s: cp_prob=%.4f", asset_id, cp_prob)
    return cp_prob, detector
