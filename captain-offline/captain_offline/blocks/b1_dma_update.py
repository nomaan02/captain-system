# region imports
try:
    from AlgorithmImports import *
except ImportError:
    pass
# endregion
"""DMA Meta-Weight Update — P3-PG-02 (Task 2.1b / OFF lines 101-157).

After each trade outcome, update AIM inclusion probabilities using
Dynamic Model Averaging with magnitude-weighted likelihood (SPEC-A9).

Forgetting factor: lambda = 0.99
Likelihood: z-score clamped to 3.0, mapped to [0, 1]
Normalisation: across all active AIMs after every update

Reads: P3-D03 (trade outcome), P3-D02 (current weights), P3-D05 (EWMA stats)
Writes: P3-D02 (updated weights)
"""

import json
import logging
from datetime import datetime

from shared.questdb_client import get_cursor

from captain_offline.blocks.version_snapshot import snapshot_before_update

logger = logging.getLogger(__name__)

# Default forgetting factor (configurable via P3-D17)
DEFAULT_LAMBDA = 0.99

# Default inclusion threshold
DEFAULT_INCLUSION_THRESHOLD = 0.02

# Z-score clamp
Z_CLAMP = 3.0


def _load_active_aims(asset_id: str) -> list[dict]:
    """Load all ACTIVE AIM weights from P3-D02."""
    with get_cursor() as cur:
        cur.execute(
            """SELECT aim_id, inclusion_probability, inclusion_flag,
                      recent_effectiveness, days_below_threshold
               FROM p3_d02_aim_meta_weights
               WHERE asset_id = %s
               LATEST ON last_updated PARTITION BY aim_id, asset_id
               ORDER BY aim_id""",
            (asset_id,),
        )
        rows = cur.fetchall()
    return [
        {
            "aim_id": r[0],
            "inclusion_probability": r[1],
            "inclusion_flag": r[2],
            "recent_effectiveness": r[3],
            "days_below_threshold": r[4],
        }
        for r in rows
    ]


def _load_ewma_regime(asset_id: str, regime: str) -> dict:
    """Load regime-level EWMA stats (weighted average across sessions).

    DMA uses regime-level aggregates, not per-session values.
    """
    with get_cursor() as cur:
        cur.execute(
            """SELECT session, win_rate, avg_win, avg_loss, n_trades
               FROM p3_d05_ewma_states
               WHERE asset_id = %s AND regime = %s
               LATEST ON last_updated PARTITION BY session
               ORDER BY session""",
            (asset_id, regime),
        )
        rows = cur.fetchall()

    if not rows:
        return {"avg_win": 0.01, "avg_loss": 0.01}

    # Weighted average across sessions by trade count
    total_trades = sum(r[4] for r in rows if r[4])
    if total_trades == 0:
        return {"avg_win": 0.01, "avg_loss": 0.01}

    avg_win = sum((r[2] or 0) * (r[4] or 0) for r in rows) / total_trades
    avg_loss = sum((r[3] or 0) * (r[4] or 0) for r in rows) / total_trades

    return {
        "avg_win": max(avg_win, 0.01),
        "avg_loss": max(avg_loss, 0.01),
    }


def _compute_likelihood(modifier: float, pnl_per_contract: float,
                         avg_win: float, avg_loss: float) -> float:
    """Compute magnitude-weighted likelihood (SPEC-A9).

    If modifier > 1.0 (AIM said size up):
        win  -> likelihood in [0.5, 1.0]
        loss -> likelihood in [0.0, 0.5]
    If modifier < 1.0 (AIM said size down):
        loss -> likelihood in [0.5, 1.0]
        win  -> likelihood in [0.0, 0.5]
    If modifier == 1.0 (neutral):
        likelihood = 0.5
    """
    if abs(modifier - 1.0) < 1e-6:
        return 0.5

    if modifier > 1.0:
        if pnl_per_contract > 0:
            z = min(pnl_per_contract / max(avg_win, 0.01), Z_CLAMP)
            return 0.5 + 0.5 * z / Z_CLAMP
        else:
            z = min(abs(pnl_per_contract) / max(avg_loss, 0.01), Z_CLAMP)
            return 0.5 - 0.5 * z / Z_CLAMP
    else:
        if pnl_per_contract < 0:
            z = min(abs(pnl_per_contract) / max(avg_loss, 0.01), Z_CLAMP)
            return 0.5 + 0.5 * z / Z_CLAMP
        else:
            z = min(pnl_per_contract / max(avg_win, 0.01), Z_CLAMP)
            return 0.5 - 0.5 * z / Z_CLAMP


def run_dma_update(trade_outcome: dict, forgetting_factor: float = DEFAULT_LAMBDA,
                    inclusion_threshold: float = DEFAULT_INCLUSION_THRESHOLD):
    """Execute P3-PG-02 after a trade outcome.

    Args:
        trade_outcome: Dict with keys from P3-D03:
            asset, pnl, contracts, regime_at_entry, aim_breakdown_at_entry
        forgetting_factor: Lambda (default 0.99)
        inclusion_threshold: Below this, inclusion_flag = False (default 0.02)
    """
    asset_id = trade_outcome["asset"]
    pnl = trade_outcome["pnl"]
    contracts = trade_outcome.get("contracts", 1)
    regime = trade_outcome.get("regime_at_entry", "LOW_VOL")
    aim_breakdown = trade_outcome.get("aim_breakdown_at_entry", {})

    if contracts <= 0:
        logger.warning("DMA update skipped: invalid contract count %d", contracts)
        return

    pnl_per_contract = pnl / contracts

    # Load current AIM weights
    aims = _load_active_aims(asset_id)
    if not aims:
        logger.warning("DMA update skipped: no active AIMs for %s", asset_id)
        return

    # Snapshot before update
    snapshot_state = {a["aim_id"]: a["inclusion_probability"] for a in aims}
    snapshot_before_update("P3-D02", "DMA_UPDATE", snapshot_state)

    # Load regime-level EWMA stats
    ewma = _load_ewma_regime(asset_id, regime)

    # Step 1: Compute raw probabilities
    raw_probs = {}
    for aim in aims:
        aid = aim["aim_id"]
        # Use trade-time modifier from aim_breakdown (NOT current modifier)
        breakdown = aim_breakdown.get(str(aid), {})
        modifier = breakdown.get("modifier", 1.0) if isinstance(breakdown, dict) else 1.0

        likelihood = _compute_likelihood(modifier, pnl_per_contract,
                                          ewma["avg_win"], ewma["avg_loss"])

        # DMA update: raw_prob = inclusion_probability^lambda * likelihood
        raw_probs[aid] = (aim["inclusion_probability"] ** forgetting_factor) * likelihood

    # Step 2: Normalise
    total = sum(raw_probs.values())
    if total <= 0:
        logger.warning("DMA normalisation: total raw prob is zero, resetting to uniform")
        n = len(raw_probs)
        for aid in raw_probs:
            raw_probs[aid] = 1.0 / n
        total = 1.0

    # Step 3: Write updated weights to P3-D02
    with get_cursor() as cur:
        for aim in aims:
            aid = aim["aim_id"]
            new_prob = raw_probs[aid] / total
            new_flag = new_prob > inclusion_threshold

            # Track days_below_threshold for suppression
            if new_prob < inclusion_threshold:
                days_below = aim.get("days_below_threshold", 0) + 1
            else:
                days_below = 0

            cur.execute(
                """INSERT INTO p3_d02_aim_meta_weights
                   (aim_id, asset_id, inclusion_probability, inclusion_flag,
                    recent_effectiveness, days_below_threshold, last_updated)
                   VALUES (%s, %s, %s, %s, %s, %s, now())""",
                (aid, asset_id, new_prob, new_flag,
                 aim.get("recent_effectiveness", 0.0), days_below),
            )

    logger.info("DMA update for %s: %d AIMs updated (lambda=%.3f)",
                asset_id, len(aims), forgetting_factor)
