"""C12 — NKD Pivot Intervention A: D26 opportunity_weights override.

OPERATOR APPROVAL REQUIRED. This script performs a data-only mutation that
materially shifts live capital allocation:

    NY:   33.3%  -->  10%
    LON:  33.3%  -->  10%
    APAC: 33.3%  -->  80%

It does this by INSERTing a new row into ``p3_d26_hmm_opportunity_state``
with:
    opportunity_weights = {"NY": 0.10, "LON": 0.10, "APAC": 0.80}
    cold_start          = false
    n_observations      = 60   (>= 60 threshold for full-HMM mode)

The threshold of 60 in ``shared/sod_session_budget.session_budget_shares``
makes the override use the pure HMM weights branch (lines 121-122), which
then survives the 0.05 floor (all weights >= 0.05) and the renormalisation
(weights sum to 1.0 exactly).

Reversibility:
    Re-run with --revert to write a cold-start row that restores equal 1/3
    shares at the next session-open. Or wait for the offline HMM trainer to
    overwrite this row organically once it's wired.

Downstream effects (per PLAN.md §6 - all read via LATEST ON last_updated,
no captain-{online,offline,command} restart strictly required, but a
``dco restart captain-online`` ensures the next session-open reads fresh
SOD shares):

    captain-online/b4_kelly_sizing.py:226-238   -- per-session E_daily_exposure
    captain-online/b4_kelly_sizing.py:416-457   -- per-session topstep_daily_cap
    captain-command/b8_reconciliation.py        -- per-session L_halt (SOD locked)

Refs:
    NKD_PIVOT_AUDIT.md §4.2, §11.2
    PLAN.md §C12, §6, DEC-5
"""

from __future__ import annotations

import argparse
import json
import logging
import sys

from shared.questdb_client import get_cursor, qexecute

logger = logging.getLogger("nkd_pivot_d26_override")
logging.basicConfig(
    level=logging.INFO,
    format="[D26-OVERRIDE] %(asctime)s %(levelname)s: %(message)s",
)

# Locked per PLAN.md §1 DEC-5 + §6.
NKD_PIVOT_WEIGHTS = {"NY": 0.10, "LON": 0.10, "APAC": 0.80}
COLD_START_WEIGHTS: dict[str, float] = {}

# n_observations >= 60 routes session_budget_shares to the pure-HMM branch.
NKD_PIVOT_N_OBS = 60
NKD_PIVOT_TRAINING_WINDOW = 60


def _read_latest_d26() -> dict | None:
    """Read the LATEST D26 row and return a parsed snapshot, or None if empty."""
    with get_cursor() as cur:
        cur.execute(
            """SELECT hmm_params, current_state_probs, opportunity_weights,
                      prior_alpha, last_trained, training_window,
                      n_observations, cold_start, last_updated
               FROM p3_d26_hmm_opportunity_state
               ORDER BY last_updated DESC LIMIT 1"""
        )
        row = cur.fetchone()
    if not row:
        return None
    return {
        "hmm_params": row[0],
        "current_state_probs": row[1],
        "opportunity_weights": row[2],
        "prior_alpha": row[3],
        "last_trained": row[4],
        "training_window": row[5],
        "n_observations": row[6],
        "cold_start": row[7],
        "last_updated": row[8],
    }


def apply_override(revert: bool = False) -> dict:
    """Apply the NKD-pivot D26 override (or revert it).

    Returns a dict with the values written so callers/tests can assert.
    """
    if revert:
        weights = COLD_START_WEIGHTS
        n_obs = 0
        cold_start = True
        mode = "REVERT (cold-start, equal 1/3)"
    else:
        weights = NKD_PIVOT_WEIGHTS
        n_obs = NKD_PIVOT_N_OBS
        cold_start = False
        mode = "APPLY (NY=10%, LON=10%, APAC=80%)"

    logger.info("Mode: %s", mode)
    prior = _read_latest_d26()
    if prior is None:
        logger.info("No prior D26 row found — INSERTing fresh override row")
    else:
        logger.info(
            "Prior D26: cold_start=%s n_observations=%s opportunity_weights=%s",
            prior["cold_start"], prior["n_observations"], prior["opportunity_weights"],
        )

    weights_json = json.dumps(weights)
    csp_carry = prior["current_state_probs"] if prior else "{}"
    pa_carry = prior["prior_alpha"] if prior else "{}"

    with get_cursor() as cur:
        qexecute(
            cur,
            """INSERT INTO p3_d26_hmm_opportunity_state
               (hmm_params, current_state_probs, opportunity_weights,
                prior_alpha, last_trained, training_window, n_observations,
                cold_start, last_updated)
               VALUES (%s, %s, %s, %s, now(), %s, %s, %s, now())""",
            (
                "{}",
                csp_carry,
                weights_json,
                pa_carry,
                NKD_PIVOT_TRAINING_WINDOW,
                n_obs,
                cold_start,
            ),
        )

    logger.info("D26 INSERT complete — opportunity_weights=%s", weights_json)

    written = _read_latest_d26()
    if written:
        logger.info(
            "Verified LATEST D26: cold_start=%s n_observations=%s opportunity_weights=%s",
            written["cold_start"], written["n_observations"], written["opportunity_weights"],
        )

    return {
        "opportunity_weights": weights,
        "n_observations": n_obs,
        "cold_start": cold_start,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--revert", action="store_true",
        help="Write a cold-start row to revert the override (equal 1/3 shares).",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show prior D26 state and the values that would be written, but do not INSERT.",
    )
    args = parser.parse_args(argv)

    if args.dry_run:
        prior = _read_latest_d26()
        logger.info("DRY-RUN: prior D26 = %s", prior)
        target = COLD_START_WEIGHTS if args.revert else NKD_PIVOT_WEIGHTS
        logger.info("DRY-RUN: would write opportunity_weights=%s n_observations=%s cold_start=%s",
                    json.dumps(target), 0 if args.revert else NKD_PIVOT_N_OBS, args.revert)
        return 0

    apply_override(revert=args.revert)
    return 0


if __name__ == "__main__":
    sys.exit(main())
