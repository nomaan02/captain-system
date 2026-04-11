# region imports
try:
    from AlgorithmImports import *
except ImportError:
    pass
# endregion
"""Kelly Parameter Updates — P3-PG-15 (Tasks 2.8a, 2.8b / OFF lines 639-713).

After each trade outcome:
1. Normalise PnL to per-contract (remove sizing bias)
2. Adaptive EWMA decay (SPEC-A12: alpha scales with BOCPD cp_prob)
3. Update P3-D05[asset][regime][session] win_rate, avg_win, avg_loss
4. Recompute Kelly fraction per [asset][regime][session]
5. Update shrinkage factor based on estimation variance

Reads: P3-D03 (trade outcome), P3-D04 (BOCPD cp_prob), P3-D05, P3-D12
Writes: P3-D05 (EWMA), P3-D12 (Kelly)
"""

import json
import math
import logging

from shared.questdb_client import get_cursor

from captain_offline.blocks.version_snapshot import snapshot_before_update

logger = logging.getLogger(__name__)

# Adaptive span thresholds (SPEC-A12)
SPAN_THRESHOLDS = [
    (0.2, 30),   # cp_prob < 0.2 -> stable, slow learning
    (0.5, 20),   # cp_prob < 0.5 -> default
    (0.8, 12),   # cp_prob < 0.8 -> elevated instability
    (float("inf"), 8),  # cp_prob >= 0.8 -> near-changepoint
]

# Shrinkage floor (Paper 217)
SHRINKAGE_FLOOR = 0.3


def _get_cp_prob(asset_id: str) -> float:
    """Get current BOCPD changepoint probability from P3-D04."""
    with get_cursor() as cur:
        cur.execute(
            """SELECT current_changepoint_probability FROM p3_d04_decay_detector_states
               WHERE asset_id = %s
               LATEST ON last_updated PARTITION BY asset_id""",
            (asset_id,),
        )
        row = cur.fetchone()
    return row[0] if row and row[0] is not None else 0.1  # default low


def _compute_adaptive_alpha(cp_prob: float) -> float:
    """SPEC-A12: adaptive EWMA decay based on changepoint probability."""
    for threshold, span in SPAN_THRESHOLDS:
        if cp_prob < threshold:
            return 2.0 / (span + 1)
    return 2.0 / (8 + 1)  # fallback


def _load_ewma(asset_id: str, regime: str, session: int) -> dict:
    """Load current EWMA state for a specific cell."""
    with get_cursor() as cur:
        cur.execute(
            """SELECT win_rate, avg_win, avg_loss, n_trades
               FROM p3_d05_ewma_states
               WHERE asset_id = %s AND regime = %s AND session = %s
               LATEST ON last_updated PARTITION BY asset_id, regime, session""",
            (asset_id, regime, session),
        )
        row = cur.fetchone()
    if row:
        return {
            "win_rate": row[0] or 0.5,
            "avg_win": row[1] or 0.01,
            "avg_loss": row[2] or 0.01,
            "n_trades": row[3] or 0,
        }
    return {"win_rate": 0.5, "avg_win": 0.01, "avg_loss": 0.01, "n_trades": 0}


def _save_ewma(asset_id: str, regime: str, session: int, ewma: dict):
    """Save updated EWMA state to P3-D05."""
    with get_cursor() as cur:
        cur.execute(
            """INSERT INTO p3_d05_ewma_states
               (asset_id, regime, session, win_rate, avg_win, avg_loss, n_trades, last_updated)
               VALUES (%s, %s, %s, %s, %s, %s, %s, now())""",
            (asset_id, regime, session,
             ewma["win_rate"], ewma["avg_win"], ewma["avg_loss"], ewma["n_trades"]),
        )


def _compute_kelly(win_rate: float, avg_win: float, avg_loss: float) -> float:
    """Classic Kelly criterion: f* = p - (1-p)/b where b = W/L.

    Returns 0 if no edge (never negative).
    """
    if avg_loss <= 0 or win_rate <= 0:
        return 0.0
    b = avg_win / avg_loss
    kelly = win_rate - (1 - win_rate) / b
    return max(0.0, kelly)


def _compute_estimation_variance(asset_id: str) -> float:
    """Compute estimation variance from P3-D05 EWMA states (Doc 32 PG-15).

    Uses the standard error of the Kelly fraction estimate across all
    regime/session cells via delta-method propagation through f* = p - (1-p)/b.
    A volatile asset with uncertain EWMA estimates yields higher variance
    -> more shrinkage. Unlike 1/sqrt(N), this is data-dependent.
    """
    cells = []
    for r in ["LOW_VOL", "HIGH_VOL"]:
        for ss in [1, 2, 3]:
            ewma = _load_ewma(asset_id, r, ss)
            if ewma["n_trades"] > 0:
                cells.append(ewma)

    if not cells:
        return 1.0  # maximum uncertainty -> minimum shrinkage (floor)

    variances = []
    for cell in cells:
        n = cell["n_trades"]
        p = cell["win_rate"]
        W = cell["avg_win"]
        L = cell["avg_loss"]

        # Bernoulli variance of win_rate estimate
        var_p = p * (1 - p) / max(1, n)

        # Propagate through Kelly: f = p - (1-p)/(W/L)
        # df/dp = 1 + L/W, so var(f) ~ (1 + L/W)^2 * var(p)
        b = W / max(L, 0.001)
        df_dp = 1.0 + 1.0 / max(b, 0.001)
        var_f = df_dp ** 2 * var_p

        variances.append(var_f)

    # Mean estimation variance across cells, scaled to standard error
    avg_var = sum(variances) / len(variances)
    return min(1.0, math.sqrt(avg_var))


def _compute_shrinkage(asset_id: str) -> float:
    """Shrinkage factor: max(0.3, 1.0 - estimation_variance).

    Uses compute_estimation_variance(P3-D05[u]) per spec Doc 32 PG-15.
    Approaches 1.0 as data accumulates and estimates stabilise. Floor at 0.3.
    """
    estimation_variance = _compute_estimation_variance(asset_id)
    return max(SHRINKAGE_FLOOR, 1.0 - estimation_variance)


def run_kelly_update(trade_outcome: dict):
    """Execute P3-PG-15 after a trade outcome.

    Args:
        trade_outcome: Dict with keys: asset, pnl, contracts,
                      regime_at_entry, session

    D12 Join Strategy (offline writer <-> online consumer):
        This function writes two types of rows to p3_d12_kelly_parameters:

        1. Per-cell rows: (asset_id, regime, session) -> kelly_full
           - regime in {LOW_VOL, HIGH_VOL}, session in {1, 2, 3}
           - 6 rows per asset, one for each regime x session combination

        2. Shrinkage row: (asset_id, "ALL", 0) -> shrinkage_factor
           - One per asset, derived from estimation variance of D05 EWMA states
           - shrinkage = max(0.3, 1 - compute_estimation_variance(D05[asset]))

        Online consumer (b4_kelly_sizing) reads D12 keyed by (asset_id, regime, session):
        - _get_kelly_for_regime() matches exact (asset, regime, session) for kelly_full
        - _get_shrinkage() matches (asset, "ALL", *) for shrinkage_factor
        - Final position size fraction = kelly_full * shrinkage_factor
    """
    asset_id = trade_outcome["asset"]
    pnl = trade_outcome["pnl"]
    contracts = trade_outcome.get("contracts", 1)
    regime = trade_outcome.get("regime_at_entry", "LOW_VOL")
    session = trade_outcome.get("session", 1)

    if contracts <= 0:
        logger.warning("Kelly update skipped: invalid contracts=%d", contracts)
        return

    # Per-contract normalisation (removes sizing bias)
    pnl_per_contract = pnl / contracts

    # Get adaptive alpha from BOCPD
    cp_prob = _get_cp_prob(asset_id)
    alpha = _compute_adaptive_alpha(cp_prob)

    # Load current EWMA for this [asset][regime][session]
    ewma = _load_ewma(asset_id, regime, session)

    # Snapshot before update
    snapshot_before_update("P3-D05", "EWMA_UPDATE", {
        "asset_id": asset_id, "regime": regime, "session": session, **ewma
    })

    # Update EWMA
    if pnl_per_contract > 0:
        ewma["win_rate"] = (1 - alpha) * ewma["win_rate"] + alpha * 1.0
        ewma["avg_win"] = (1 - alpha) * ewma["avg_win"] + alpha * pnl_per_contract
    else:
        ewma["win_rate"] = (1 - alpha) * ewma["win_rate"] + alpha * 0.0
        ewma["avg_loss"] = (1 - alpha) * ewma["avg_loss"] + alpha * abs(pnl_per_contract)

    ewma["n_trades"] = ewma["n_trades"] + 1

    _save_ewma(asset_id, regime, session, ewma)

    # Recompute Kelly for ALL regime/session combinations
    snapshot_before_update("P3-D12", "KELLY_UPDATE", {
        "asset_id": asset_id, "trigger_regime": regime, "trigger_session": session
    })

    for r in ["LOW_VOL", "HIGH_VOL"]:
        for ss in [1, 2, 3]:
            e = _load_ewma(asset_id, r, ss)
            kelly_full = _compute_kelly(e["win_rate"], e["avg_win"], e["avg_loss"])

            with get_cursor() as cur:
                cur.execute(
                    """INSERT INTO p3_d12_kelly_parameters
                       (asset_id, regime, session, kelly_full, shrinkage_factor,
                        sizing_override, last_updated)
                       VALUES (%s, %s, %s, %s, %s, %s, now())""",
                    (asset_id, r, ss, kelly_full, None, None),
                )

    # Update shrinkage factor (asset-level, data-dependent per PG-15)
    shrinkage = _compute_shrinkage(asset_id)

    with get_cursor() as cur:
        # Store shrinkage as a separate row (regime=ALL, session=0)
        cur.execute(
            """INSERT INTO p3_d12_kelly_parameters
               (asset_id, regime, session, kelly_full, shrinkage_factor,
                sizing_override, last_updated)
               VALUES (%s, %s, %s, %s, %s, %s, now())""",
            (asset_id, "ALL", 0, 0.0, shrinkage, None),
        )

    # SQLite WAL checkpoint per spec P3-PG-15: ensures crash recovery
    # can restore last known good EWMA/Kelly state
    from shared.journal import write_checkpoint
    write_checkpoint("OFFLINE", "KELLY_UPDATE_COMPLETE", "kelly_updated",
                     "waiting", {"asset": asset_id, "regime": regime,
                                 "session": session, "shrinkage": shrinkage})

    logger.info("Kelly update for %s [%s][s%d]: alpha=%.3f, cp_prob=%.3f, "
                "wr=%.3f, W=%.1f, L=%.1f, shrinkage=%.3f",
                asset_id, regime, session, alpha, cp_prob,
                ewma["win_rate"], ewma["avg_win"], ewma["avg_loss"], shrinkage)
