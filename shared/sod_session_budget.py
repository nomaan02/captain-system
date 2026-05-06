"""Per-session SOD budget helpers for the Captain System.

Implements time-partitioned daily exposure budgets per the spec in
``docs2/quick-fixes/circuit-breaker-nkd-issue/15_Topstep_Optimisation_Functions (1).md``
section 4.4.4 and ``16_HMM_Opportunity_Regime_Spec.md`` section 3.6.

Key concepts
------------
- **SOD-locked totals**: ``L_halt_total = c * e * A``, ``E_total = e * A``,
  computed by Command Block 8 at 19:00 EST and stored under
  ``p3_d08_tsm_state.topstep_state.computed_sod`` keys
  ``L_halt`` (legacy) / ``E_daily_exposure`` (legacy).

- **Per-session shares (alpha_w)**: HMM-derived weights from P3-D26
  (``opportunity_weights``) applied to NY/LON/APAC. Cold start (n_obs<20)
  defaults to equal 1/3 weights. Blended (n_obs<60) uses 50/50 of equal+HMM.
  Full HMM (n_obs>=60) uses pure HMM weights. Floor at 0.05 then renormalise.

- **SOD per-session shares**: persisted under
  ``computed_sod.session.{NY,LON,APAC}.{L_halt, E_daily_exposure, N_max_trades}``
  by Command Block 8 (Phase 2 of this work).

- **Effective per-session budget at session open**: derived at session-open time
  in Online by ``compute_session_carryover`` — combines the session's SOD share
  with a weighted slice of the unused-pool from earlier-completed sessions so
  parity-skipped sessions (where one tower took zero of a single-asset session)
  don't waste budget. Total daily budget is conserved.

- **Layer 1 / Layer 2 read site**: B5C circuit breaker reads
  ``effective_l_halt`` and ``effective_e_exposure`` directly from the open
  session's D23 row. Falls back to per-session computed_sod entry, then to
  the legacy flat top-level keys, on a partially-deployed system.

Backwards compatibility
-----------------------
All readers fall back to the flat ``computed_sod.L_halt`` / ``E_daily_exposure``
scalars when ``computed_sod.session`` is not yet populated. This means the
new code is safe to deploy before Phase 2 lands — behaviour matches today's
production until B8 starts writing the per-session map.
"""

from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal
from typing import Iterable

from shared.constants import SESSION_IDS

logger = logging.getLogger(__name__)


# Session keys are the canonical labels used in computed_sod and HMM weights.
SESSION_KEY = SESSION_IDS  # {1: "NY", 2: "LON", 3: "APAC", 4: "NY_PRE"}
SESSION_KEYS_TRADING = ("NY", "LON", "APAC", "NY_PRE")

# Equal cold-start share — explicit 4-decimal Decimal for arithmetic stability.
# Matches the floor logic in b5_trade_selection.apply_hmm_session_allocation.
EQUAL_SHARE = Decimal("1") / Decimal("3")

# Floor per session in HMM full-weight mode (matches existing 0.05 in b5).
SESSION_WEIGHT_FLOOR = Decimal("0.05")


def session_key_for(session_id: int) -> str:
    """Return the canonical session key for a session_id.

    Defaults to ``"NY"`` for unknown ids so callers always have a key to look
    up. Callers who care should use ``SESSION_IDS`` directly.
    """
    return SESSION_IDS.get(session_id, "NY")


def _to_decimal(value, default: Decimal = Decimal("0")) -> Decimal:
    """Coerce ``value`` to ``Decimal`` at the boundary; ``None`` -> ``default``."""
    if value is None:
        return default
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def session_budget_shares(hmm_state: dict | None) -> dict[str, Decimal]:
    """Return ``{NY, LON, APAC}`` budget shares summing to ``1.0`` as Decimals.

    Mirrors the cold-start semantics in
    ``b5_trade_selection.apply_hmm_session_allocation`` so Command B8 (SOD
    allocator) and Online B5/B5C (consumers) compute identical shares.

    Cold start (``n_observations < 20`` or ``cold_start=True``) -> equal 1/3 each.
    Blended (``20 <= n_observations < 60``) -> 50/50 mix of equal + HMM weights.
    Full (``n_observations >= 60``) -> pure HMM weights.

    A 0.05 floor is applied per session, then weights are renormalised so the
    sum stays exactly 1.0.
    """
    keys = ("NY", "LON", "APAC")

    if hmm_state is None:
        return {k: EQUAL_SHARE for k in keys}

    n_obs = int(hmm_state.get("n_observations", 0) or 0)
    cold = bool(hmm_state.get("cold_start", True))
    raw_weights = hmm_state.get("opportunity_weights", {}) or {}

    if cold or n_obs < 20:
        return {k: EQUAL_SHARE for k in keys}

    # Pull HMM weights with equal fallback per key.
    hmm_w: dict[str, Decimal] = {
        k: _to_decimal(raw_weights.get(k), default=EQUAL_SHARE) for k in keys
    }

    if n_obs < 60:
        # Blended: 50% equal + 50% HMM
        half = Decimal("0.5")
        weights = {
            k: half * EQUAL_SHARE + half * hmm_w[k] for k in keys
        }
    else:
        weights = hmm_w

    # Apply floor, then renormalise.
    floored = {k: max(weights[k], SESSION_WEIGHT_FLOOR) for k in keys}
    total = sum(floored.values()) or Decimal("1")
    normalised = {k: (v / total) for k, v in floored.items()}
    return normalised


def get_session_l_halt(
    computed_sod: dict | None,
    session_id: int,
) -> Decimal:
    """Return per-session ``L_halt`` for ``session_id`` from D08.computed_sod.

    Lookup order (most-specific first):
      1. ``computed_sod.session.<KEY>.L_halt`` (Phase 2 nested format)
      2. ``computed_sod.L_halt`` (legacy flat scalar — represents the WHOLE
         day budget, NOT a per-session share, so this fallback is conservative
         pre-Phase-2 only and SHOULD be replaced once Phase 2 is live).
      3. ``Decimal("0")`` (no SOD computation — caller must handle).
    """
    if not computed_sod:
        return Decimal("0")
    session_key = session_key_for(session_id)
    sess_map = computed_sod.get("session", {}) or {}
    sess_entry = sess_map.get(session_key, {}) or {}
    val = sess_entry.get("L_halt")
    if val is not None:
        return _to_decimal(val)
    legacy = computed_sod.get("L_halt")
    if legacy is not None:
        logger.debug(
            "sod_session_budget: per-session L_halt missing for %s — falling "
            "back to legacy total. Re-run Command B8 to populate.",
            session_key,
        )
        return _to_decimal(legacy)
    return Decimal("0")


def get_session_e_exposure(
    computed_sod: dict | None,
    session_id: int,
) -> Decimal:
    """Return per-session ``E_daily_exposure`` for ``session_id``.

    Same lookup order as ``get_session_l_halt`` but for the dollar exposure
    budget that drives B4's ``_compute_topstep_daily_cap`` and B5C Layer 2.
    """
    if not computed_sod:
        return Decimal("0")
    session_key = session_key_for(session_id)
    sess_map = computed_sod.get("session", {}) or {}
    sess_entry = sess_map.get(session_key, {}) or {}
    val = sess_entry.get("E_daily_exposure")
    if val is not None:
        return _to_decimal(val)
    legacy = computed_sod.get("E_daily_exposure")
    if legacy is not None:
        logger.debug(
            "sod_session_budget: per-session E missing for %s — falling back "
            "to legacy total.",
            session_key,
        )
        return _to_decimal(legacy)
    return Decimal("0")


def get_session_n_max_trades(
    computed_sod: dict | None,
    session_id: int,
) -> int:
    """Return per-session ``N_max_trades`` for ``session_id``.

    Lookup order: nested ``session.<KEY>.N_max_trades`` -> legacy flat
    ``N_max_trades`` -> ``999`` (effectively unbounded).
    """
    if not computed_sod:
        return 999
    session_key = session_key_for(session_id)
    sess_map = computed_sod.get("session", {}) or {}
    sess_entry = sess_map.get(session_key, {}) or {}
    val = sess_entry.get("N_max_trades")
    if val is not None:
        return int(val)
    legacy = computed_sod.get("N_max_trades")
    if legacy is not None:
        return int(legacy)
    return 999


def compute_session_carryover(
    *,
    sod_l_halt_total: Decimal,
    sod_e_total: Decimal,
    shares: dict[str, Decimal],
    completed_sessions_state: dict[str, dict],
    target_session_id: int,
    remaining_session_ids: Iterable[int],
) -> tuple[Decimal, Decimal]:
    """Compute the effective per-session L_halt and E_daily_exposure at session open.

    Implements Isaac's "available × share / remaining" allocation formula
    (HMM Opportunity Regime Spec §3.6), which conserves total daily budget
    across the day and correctly handles nested carryovers (where each
    session's effective_L_halt may already reflect carryover from sessions
    earlier than it):

        consumed_so_far  = Σ |L_t_w_final|  for w in completed earlier sessions
        available        = max(0, sod_total - consumed_so_far)
        remaining_sum    = Σ shares[r]      for r in remaining_session_ids
        effective[target] = available × shares[target] / remaining_sum

    The formula tracks REALIZED consumption (|L_t_w_final|) rather than the
    effective allocations of completed sessions. This avoids double-counting
    when a completed session itself absorbed carryover from a session before
    it (e.g., NY_PRE opens with LON's carryover; if NY_PRE is treated as
    "completed with effective=667", a sum-of-unused formula double-counts
    LON's 500 once in LON's row and once embedded in NY_PRE's 667).

    Parity-skip property (Nomaan's intent): if LON closes with l_t_final=0
    (parity-skipped), NY's available pool is unchanged from SOD total, and NY's
    share-of-remaining is now larger (LON is no longer in remaining), so NY
    receives more budget than its bare SOD share would give.

    Parameters
    ----------
    sod_l_halt_total / sod_e_total
        Day totals from ``computed_sod.L_halt`` / ``E_daily_exposure``.
    shares
        Per-session HMM shares ``{NY, LON, APAC}`` summing to 1.
    completed_sessions_state
        ``{session_key: {"effective_l_halt": Decimal,
                         "effective_e_exposure": Decimal,
                         "l_t_final": Decimal}}`` for sessions that have
        already CLOSED today. Only ``l_t_final`` is read (REALIZED consumption);
        ``effective_l_halt`` and ``effective_e_exposure`` are kept in the
        signature for forward-compat / observability but are NOT used in the
        carryover math (see docstring above on why).
    target_session_id
        The session being opened now.
    remaining_session_ids
        Session_ids not yet ended today, INCLUDING the target.

    Returns
    -------
    (effective_l_halt, effective_e_exposure) as Decimals.
    """
    target_key = session_key_for(target_session_id)
    target_share = shares.get(target_key, EQUAL_SHARE)

    # Total realized consumption across all completed earlier sessions today.
    # Spec convention: abs(L_t) — both wins and losses count toward consumption
    # (matches B5C L1's `abs(l_t) + rho_j >= L_halt` formula).
    consumed = Decimal("0")
    for _w_key, w_state in completed_sessions_state.items():
        l_t_final = _to_decimal(w_state.get("l_t_final"))
        consumed += abs(l_t_final)

    available_l_halt = max(Decimal("0"), sod_l_halt_total - consumed)
    available_e = max(Decimal("0"), sod_e_total - consumed)

    # Sum of remaining shares — denominator for normalisation.
    remaining_share_sum = Decimal("0")
    for sid in remaining_session_ids:
        remaining_share_sum += shares.get(session_key_for(sid), EQUAL_SHARE)

    if remaining_share_sum > 0:
        effective_l_halt = available_l_halt * (target_share / remaining_share_sum)
        effective_e = available_e * (target_share / remaining_share_sum)
    else:
        effective_l_halt = available_l_halt
        effective_e = available_e
    return effective_l_halt, effective_e


# ---------------------------------------------------------------------------
# Trading-day session ordering
# ---------------------------------------------------------------------------

# Ordered list of session_ids from earliest open-time to latest within a single
# trading day in America/New_York. The trading day runs 19:00 ET (SOD reset) →
# 19:00 ET (next SOD reset). Within that window the canonical HMM-session order
# is:
#   LON     03:00 ET   (session_id=2)
#   NY      09:30 ET   (session_id=1)
#   APAC    18:00 ET   (session_id=3)  -- last session before next SOD reset
#
# v1 NOTE: NY_PRE (session_id=4, 06:00 ET) is INTENTIONALLY excluded from the
# per-session budget machinery in v1. The HMM (`probs_to_ny_lon_apac` in
# shared/hmm_online_inference.py) produces weights for only 3 sessions (NY/LON/
# APAC); NY_PRE has no HMM weight. Including it with a default share would
# break the budget-conservation property (shares would sum > 1).
# Practical impact: assets that trade only NY_PRE (currently MCL, ZT) fall
# through to the legacy flat L_halt/E behaviour. Future iteration: extend HMM
# observation panel to produce 4-session weights, then add 4 to this tuple.
# Source of truth: config/session_registry.json or_start times.
TRADING_DAY_SESSION_ORDER: tuple[int, ...] = (2, 1, 3)
# = (LON, NY, APAC) by session_id


def sessions_earlier_in_day(session_id: int) -> tuple[int, ...]:
    """Return session_ids that open earlier than ``session_id`` in a trading day.

    Used by the carryover compute path to find sessions whose budgets may
    already have been (partially) consumed.
    """
    try:
        idx = TRADING_DAY_SESSION_ORDER.index(session_id)
    except ValueError:
        return ()
    return TRADING_DAY_SESSION_ORDER[:idx]


def sessions_remaining_in_day(session_id: int) -> tuple[int, ...]:
    """Return session_ids from ``session_id`` (inclusive) to end-of-day.

    Used as the denominator weight pool for distributing unused budget.
    """
    try:
        idx = TRADING_DAY_SESSION_ORDER.index(session_id)
    except ValueError:
        return (session_id,)
    return TRADING_DAY_SESSION_ORDER[idx:]
