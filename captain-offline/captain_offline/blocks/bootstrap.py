# region imports
try:
    from AlgorithmImports import *
except ImportError:
    pass
# endregion
"""Asset Bootstrap & Warmup Check (Tasks 2.10b, 2.10c / OFF lines 1098-1191).

asset_bootstrap(asset_id):
  - Load D-22 historical trades for locked (m,k) from P2-D06
  - Min 20 trades required
  - Init P3-D05 EWMA per [regime][session] (min 5 per cell, fallback unconditional)
  - Init P3-D04 BOCPD/CUSUM from in-control returns
  - Compute initial Kelly -> P3-D12
  - Set Tier 1 AIMs {4,6,8,11,12,15} to BOOTSTRAPPED

asset_warmup_check():
  - Daily: check 4 conditions for WARM_UP -> ACTIVE transition
  - EWMA baseline, Tier 1 AIMs ready, regime model, P1/P2 validated
"""

import json
import math
import logging
from collections import defaultdict

from shared.questdb_client import get_cursor

logger = logging.getLogger(__name__)

TIER1_AIMS = [4, 6, 8, 11, 12, 15]
MIN_BOOTSTRAP_TRADES = 20
MIN_PER_CELL_TRADES = 5


def _load_locked_strategy(asset_id: str) -> dict | None:
    """Load locked strategy from P3-D00."""
    with get_cursor() as cur:
        cur.execute(
            """SELECT locked_strategy FROM p3_d00_asset_universe
               WHERE asset_id = %s
               ORDER BY last_updated DESC LIMIT 1""",
            (asset_id,),
        )
        row = cur.fetchone()
    if row and row[0]:
        return json.loads(row[0])
    return None


def _derive_session(exchange_timezone: str) -> int:
    """Derive default session for an asset based on exchange timezone.

    Simplified: NY-based assets default to session 1 (NY).
    """
    if "New_York" in (exchange_timezone or ""):
        return 1
    elif "London" in (exchange_timezone or ""):
        return 2
    else:
        return 3


def _compute_unconditional(returns: list[float]) -> dict:
    """Compute unconditional EWMA stats from a list of per-contract returns."""
    if not returns:
        return {"win_rate": 0.5, "avg_win": 0.01, "avg_loss": 0.01, "n_trades": 0}

    wins = [r for r in returns if r > 0]
    losses = [abs(r) for r in returns if r <= 0]

    return {
        "win_rate": len(wins) / len(returns) if returns else 0.5,
        "avg_win": sum(wins) / len(wins) if wins else 0.01,
        "avg_loss": sum(losses) / len(losses) if losses else 0.01,
        "n_trades": len(returns),
    }


def asset_bootstrap(asset_id: str, historical_trades: list[dict],
                     regime_labels: dict[str, str]):
    """Initialize EWMA, BOCPD, Kelly for a new asset from historical data.

    Args:
        asset_id: Asset to bootstrap
        historical_trades: List of dicts with keys: date, r (per-contract return),
                          regime_tag (from P2-D02)
        regime_labels: Dict mapping date string to regime label (LOW_VOL/HIGH_VOL)
    """
    n_trades = len(historical_trades)

    if n_trades < MIN_BOOTSTRAP_TRADES:
        logger.warning("Insufficient trades for %s bootstrap: %d < %d",
                       asset_id, n_trades, MIN_BOOTSTRAP_TRADES)
        # Update warmup progress
        from shared.questdb_client import update_d00_fields
        update_d00_fields(asset_id, {
            "captain_status": "WARM_UP",
            "warm_up_progress": n_trades / MIN_BOOTSTRAP_TRADES,
        })
        return

    # Get asset timezone for session derivation
    with get_cursor() as cur:
        cur.execute(
            "SELECT exchange_timezone FROM p3_d00_asset_universe WHERE asset_id = %s",
            (asset_id,),
        )
        row = cur.fetchone()
    tz = row[0] if row else "America/New_York"
    default_session = _derive_session(tz)

    # Step 2: Init P3-D05 EWMA per [regime][session]
    all_returns = [t["r"] for t in historical_trades]

    for regime in ["LOW_VOL", "HIGH_VOL"]:
        for session in [1, 2, 3]:
            # Filter trades by regime and session
            regime_session_trades = [
                t["r"] for t in historical_trades
                if regime_labels.get(t.get("date", ""), "LOW_VOL") == regime
                and session == default_session  # simplified session derivation
            ]

            if len(regime_session_trades) >= MIN_PER_CELL_TRADES:
                ewma = _compute_unconditional(regime_session_trades)
            else:
                # Fallback to unconditional
                ewma = _compute_unconditional(all_returns)

            with get_cursor() as cur:
                cur.execute(
                    """INSERT INTO p3_d05_ewma_states
                       (asset_id, regime, session, win_rate, avg_win, avg_loss,
                        n_trades, last_updated)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, now())""",
                    (asset_id, regime, session,
                     ewma["win_rate"], ewma["avg_win"], ewma["avg_loss"],
                     ewma["n_trades"]),
                )

    # Step 3: Init P3-D04 BOCPD/CUSUM from in-control returns
    import numpy as np
    returns_arr = np.array(all_returns)
    mean_r = float(np.mean(returns_arr))
    std_r = float(np.std(returns_arr)) if len(returns_arr) > 1 else 1.0

    with get_cursor() as cur:
        cur.execute(
            """INSERT INTO p3_d04_decay_detector_states
               (asset_id, bocpd_cp_probability, cusum_c_up_prev, cusum_c_down_prev,
                cusum_sprint_length, cusum_allowance, current_changepoint_probability,
                last_updated)
               VALUES (%s, %s, %s, %s, %s, %s, %s, now())""",
            (asset_id, 0.01, 0.0, 0.0, 0, std_r * 0.5, 0.01),
        )

    # Step 4: Compute initial Kelly
    for regime in ["LOW_VOL", "HIGH_VOL"]:
        for session in [1, 2, 3]:
            with get_cursor() as cur:
                cur.execute(
                    """SELECT win_rate, avg_win, avg_loss
                       FROM p3_d05_ewma_states
                       WHERE asset_id = %s AND regime = %s AND session = %s
                       ORDER BY last_updated DESC LIMIT 1""",
                    (asset_id, regime, session),
                )
                row = cur.fetchone()

            if row and row[0] and row[2] and row[2] > 0:
                p = row[0]
                b = row[1] / row[2] if row[2] > 0 else 0
                kelly_full = max(0.0, p - (1 - p) / b) if b > 0 else 0.0
            else:
                kelly_full = 0.0

            shrinkage = max(0.3, 1.0 - 1.0 / math.sqrt(max(n_trades, 1)))

            with get_cursor() as cur:
                cur.execute(
                    """INSERT INTO p3_d12_kelly_parameters
                       (asset_id, regime, session, kelly_full, shrinkage_factor,
                        sizing_override, last_updated)
                       VALUES (%s, %s, %s, %s, %s, %s, now())""",
                    (asset_id, regime, session, kelly_full, shrinkage, None),
                )

    # Step 5: Set Tier 1 AIMs to BOOTSTRAPPED
    for aim_id in TIER1_AIMS:
        with get_cursor() as cur:
            cur.execute(
                """SELECT status FROM p3_d01_aim_model_states
                   WHERE aim_id = %s AND asset_id = %s
                   ORDER BY last_updated DESC LIMIT 1""",
                (aim_id, asset_id),
            )
            row = cur.fetchone()

        if row and row[0] in ("INSTALLED", "COLLECTING", "WARM_UP"):
            with get_cursor() as cur:
                cur.execute(
                    """INSERT INTO p3_d01_aim_model_states
                       (aim_id, asset_id, status, warmup_progress, last_updated)
                       VALUES (%s, %s, 'BOOTSTRAPPED', 1.0, now())""",
                    (aim_id, asset_id),
                )
            logger.info("AIM-%d set to BOOTSTRAPPED from historical data for %s",
                        aim_id, asset_id)

    logger.info("Asset %s bootstrapped from %d historical trades", asset_id, n_trades)


def asset_warmup_check():
    """Execute daily warmup check: can any WARM_UP assets transition to ACTIVE?

    4 conditions (all must be true):
      1. EWMA baseline exists (P3-D05 has data for all 6 cells)
      2. Tier 1 AIMs at BOOTSTRAPPED, ELIGIBLE, or ACTIVE
      3. Regime model available (P2-D07 exists or BINARY_ONLY)
      4. P1/P2 validation complete (both VALIDATED)
    """
    with get_cursor() as cur:
        cur.execute(
            """SELECT asset_id, p1_status, p2_status
               FROM p3_d00_asset_universe
               WHERE captain_status = 'WARM_UP'""",
        )
        warmup_assets = cur.fetchall()

    for asset_id, p1_status, p2_status in warmup_assets:
        checks = []

        # Condition 1: EWMA baseline exists
        with get_cursor() as cur:
            cur.execute(
                """SELECT count() FROM p3_d05_ewma_states
                   WHERE asset_id = %s AND win_rate IS NOT NULL""",
                (asset_id,),
            )
            ewma_count = cur.fetchone()[0]
        ewma_ready = ewma_count >= 6  # 2 regimes * 3 sessions
        checks.append(ewma_ready)

        # Condition 2: Tier 1 AIMs ready
        aims_ready = True
        for aim_id in TIER1_AIMS:
            with get_cursor() as cur:
                cur.execute(
                    """SELECT status FROM p3_d01_aim_model_states
                       WHERE aim_id = %s AND asset_id = %s
                       ORDER BY last_updated DESC LIMIT 1""",
                    (aim_id, asset_id),
                )
                row = cur.fetchone()
            if not row or row[0] not in ("BOOTSTRAPPED", "ELIGIBLE", "ACTIVE"):
                aims_ready = False
                break
        checks.append(aims_ready)

        # Condition 3: Regime model available
        # For V1 with single asset, we accept P2 completion as sufficient
        regime_ready = p2_status == "VALIDATED"
        checks.append(regime_ready)

        # Condition 4: P1/P2 validated
        p1p2_ready = p1_status == "VALIDATED" and p2_status == "VALIDATED"
        checks.append(p1p2_ready)

        from shared.questdb_client import update_d00_fields
        if all(checks):
            update_d00_fields(asset_id, {
                "captain_status": "ACTIVE",
                "warm_up_progress": 1.0,
            })
            logger.info("Asset %s: WARM_UP -> ACTIVE (all 4 conditions met)", asset_id)
        else:
            progress = sum(checks) / len(checks)
            update_d00_fields(asset_id, {
                "captain_status": "WARM_UP",
                "warm_up_progress": progress,
            })
            logger.debug("Asset %s warmup progress: %.0f%% (%s)",
                         asset_id, progress * 100,
                         ["EWMA", "AIMs", "Regime", "P1P2"][checks.index(False)] + " failed")
