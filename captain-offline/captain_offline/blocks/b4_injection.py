# region imports
try:
    from AlgorithmImports import *
except ImportError:
    pass
# endregion
"""Injection Comparison & Transition Phasing — P3-PG-10/11 (Tasks 2.4a, 2.4b).

P3-PG-10: AIM-adjusted comparison of new candidate vs current strategy.
  ADOPT if expected_new > expected_current * 1.2 AND pbo < 0.5
  PARALLEL_TRACK if 0.9x < ratio < 1.2x
  REJECT if expected_new <= 0.9x expected_current

P3-PG-11: Transition phasing (linear ramp over transition_days).
  weight_new(d) = d / transition_days
  blended_size = weight_new * size_new + weight_old * size_old
  Direction follows new strategy.

  Parallel tracking: 20 days, current executed, candidate logged.

Reads: P2-D06, P2-D07, P3-D00, P3-D02, P3-D03
Writes: P3-D00, P3-D06
"""

import json
import logging
from datetime import datetime

from shared.constants import now_et
from shared.questdb_client import get_cursor

from captain_offline.blocks.b3_pseudotrader import run_pseudotrader

logger = logging.getLogger(__name__)

# Decision thresholds
ADOPT_RATIO = 1.2       # new must be > 1.2x current
PARALLEL_RATIO = 0.9    # between 0.9x and 1.2x -> parallel track
PBO_THRESHOLD = 0.5

# Transition parameters
DEFAULT_TRANSITION_DAYS = 10
DEFAULT_TRACKING_DAYS = 20


def _compute_aim_adjusted_edge(strategy: dict, aim_weights: dict,
                                 historical_pnl: list[float]) -> float:
    """Compute AIM-adjusted expected edge for a strategy.

    Uses the DMA-weighted AIM modifiers retroactively applied to
    historical performance.

    Simplified: expected_edge = mean(pnl) * mean(modifier)
    """
    if not historical_pnl:
        return 0.0

    import numpy as np
    mean_pnl = float(np.mean(historical_pnl))

    # Average AIM modifier from weights
    total_weight = sum(aim_weights.values()) if aim_weights else 1.0
    mean_modifier = total_weight / max(len(aim_weights), 1) if aim_weights else 1.0

    return mean_pnl * max(mean_modifier, 0.5)


def _load_aim_weights(asset_id: str) -> dict:
    """Load current AIM inclusion probabilities from P3-D02."""
    with get_cursor() as cur:
        cur.execute(
            """SELECT aim_id, inclusion_probability FROM p3_d02_aim_meta_weights
               WHERE asset_id = %s ORDER BY aim_id""",
            (asset_id,),
        )
        rows = cur.fetchall()
    result = {}
    for r in rows:
        if r[0] not in result:
            result[r[0]] = r[1]
    return result


def _store_injection(asset_id: str, candidate: dict, current: dict,
                      expected_new: float, expected_current: float,
                      pseudo_results: dict, recommendation: str):
    """Store injection comparison to P3-D06."""
    with get_cursor() as cur:
        cur.execute(
            """INSERT INTO p3_d06_injection_history
               (injection_id, asset, candidate, current_strategy,
                expected_new, expected_current, pseudo_results,
                recommendation, status, injection_type, ts)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now())""",
            (
                f"INJ-{asset_id}-{now_et().strftime('%Y%m%d')}",
                asset_id,
                json.dumps(candidate, default=str),
                json.dumps(current, default=str),
                expected_new, expected_current,
                json.dumps(pseudo_results, default=str),
                recommendation,
                "COMPARISON_COMPLETE",
                "INJECTION",
            ),
        )


def run_injection_comparison(asset_id: str, new_candidate: dict,
                               current_strategy: dict,
                               candidate_pnl: list[float],
                               current_pnl: list[float]) -> dict:
    """Execute P3-PG-10: injection comparison.

    Args:
        asset_id: Asset being evaluated
        new_candidate: New strategy from P1/P2 rerun (P2-D06 format)
        current_strategy: Current locked strategy from P3-D00
        candidate_pnl: Historical P&L under new candidate
        current_pnl: Historical P&L under current strategy

    Returns:
        Dict with recommendation (ADOPT/PARALLEL_TRACK/REJECT)
    """
    aim_weights = _load_aim_weights(asset_id)

    # AIM-adjusted expected edges
    expected_new = _compute_aim_adjusted_edge(new_candidate, aim_weights, candidate_pnl)
    expected_current = _compute_aim_adjusted_edge(current_strategy, aim_weights, current_pnl)

    # Run pseudotrader comparison
    pseudo_results = run_pseudotrader(
        asset_id, "STRATEGY_INJECTION", current_pnl, candidate_pnl
    )

    # Decision logic
    if expected_current > 0:
        ratio = expected_new / expected_current
    else:
        ratio = 2.0 if expected_new > 0 else 0.0

    if ratio > ADOPT_RATIO and pseudo_results["pbo"] < PBO_THRESHOLD:
        recommendation = "ADOPT"
        transition_days = DEFAULT_TRANSITION_DAYS
    elif ratio > PARALLEL_RATIO and ratio <= ADOPT_RATIO:
        recommendation = "PARALLEL_TRACK"
        transition_days = DEFAULT_TRACKING_DAYS
    else:
        recommendation = "REJECT"
        transition_days = 0

    # Store
    _store_injection(asset_id, new_candidate, current_strategy,
                     expected_new, expected_current, pseudo_results, recommendation)

    result = {
        "asset_id": asset_id,
        "expected_new": expected_new,
        "expected_current": expected_current,
        "ratio": ratio,
        "recommendation": recommendation,
        "transition_days": transition_days,
        "pseudo_results": pseudo_results,
    }

    logger.info("Injection comparison %s: ratio=%.2f, pbo=%.3f -> %s (%d days)",
                asset_id, ratio, pseudo_results["pbo"], recommendation, transition_days)

    return result


class TransitionPhaser:
    """P3-PG-11: Linear ramp transition from old to new strategy.

    For ADOPT: 10-day linear ramp.
      weight_new(d) = d / transition_days
      blended_size = weight_new * size_new + weight_old * size_old
      Direction follows NEW strategy.

    For PARALLEL_TRACK: 20-day tracking.
      Current strategy is executed.
      Candidate strategy is logged but not executed.
    """

    def __init__(self, asset_id: str, new_strategy: dict, old_strategy: dict,
                 mode: str, total_days: int):
        self.asset_id = asset_id
        self.new_strategy = new_strategy
        self.old_strategy = old_strategy
        self.mode = mode  # "ADOPT" or "PARALLEL_TRACK"
        self.total_days = total_days
        self.current_day = 0
        self.completed = False

    def get_weights(self, day: int) -> tuple[float, float]:
        """Get (weight_new, weight_old) for a given day.

        Day 1: (1/T, 1-1/T)
        Day T: (1.0, 0.0)
        """
        if self.mode != "ADOPT":
            return (0.0, 1.0)  # parallel track: only old executes
        weight_new = day / self.total_days
        weight_old = 1.0 - weight_new
        return (weight_new, weight_old)

    def blend_signal(self, day: int, signal_new: dict, signal_old: dict) -> dict:
        """Produce blended signal for transition day.

        Direction follows new strategy. Size is blended.
        """
        w_new, w_old = self.get_weights(day)

        if self.mode == "ADOPT":
            blended_size = w_new * signal_new.get("size", 0) + w_old * signal_old.get("size", 0)
            return {
                "direction": signal_new.get("direction", 0),
                "size": blended_size,
                "weight_new": w_new,
                "weight_old": w_old,
                "transition_day": day,
                "transition_total": self.total_days,
            }
        else:
            # Parallel track: execute old, log new
            return {
                "execute": signal_old,
                "logged_candidate": signal_new,
                "tracking_day": day,
                "tracking_total": self.total_days,
            }

    def advance_day(self) -> bool:
        """Advance to next day. Returns True if transition complete."""
        self.current_day += 1
        if self.current_day >= self.total_days:
            self.completed = True
            return True
        self.save()
        return False

    def finalize(self):
        """Complete the transition: update P3-D00 locked strategy."""
        if self.mode == "ADOPT":
            from shared.questdb_client import update_d00_fields
            update_d00_fields(self.asset_id, {
                "locked_strategy": json.dumps(self.new_strategy, default=str),
                "captain_status": "ACTIVE",
            })
            logger.info("Transition complete for %s: new strategy adopted", self.asset_id)

        elif self.mode == "PARALLEL_TRACK":
            # Log completion, await final review
            logger.info("Parallel tracking complete for %s: final review required",
                        self.asset_id)

        # Mark transition as completed in persistence
        self.completed = True
        self.save()

    def save(self):
        """Persist transition state to p3_d06b_active_transitions."""
        with get_cursor() as cur:
            cur.execute(
                """INSERT INTO p3_d06b_active_transitions
                   (asset_id, mode, new_strategy, old_strategy, current_day,
                    total_days, completed, started_at, last_updated)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, now(), now())""",
                (self.asset_id, self.mode,
                 json.dumps(self.new_strategy, default=str),
                 json.dumps(self.old_strategy, default=str),
                 self.current_day, self.total_days, self.completed),
            )

    @classmethod
    def load_active(cls) -> list["TransitionPhaser"]:
        """Load all non-completed transitions from QuestDB.

        Used by the orchestrator on startup and daily to resume transitions.
        """
        with get_cursor() as cur:
            cur.execute(
                """SELECT asset_id, mode, new_strategy, old_strategy,
                          current_day, total_days
                   FROM p3_d06b_active_transitions
                   WHERE completed = false
                   ORDER BY asset_id, last_updated DESC"""
            )
            rows = cur.fetchall()

        # Deduplicate by asset_id (latest row per asset)
        seen = set()
        active = []
        for r in rows:
            if r[0] in seen:
                continue
            seen.add(r[0])
            phaser = cls(
                asset_id=r[0],
                new_strategy=json.loads(r[2]) if r[2] else {},
                old_strategy=json.loads(r[3]) if r[3] else {},
                mode=r[1],
                total_days=r[5],
            )
            phaser.current_day = r[4]
            active.append(phaser)

        return active
