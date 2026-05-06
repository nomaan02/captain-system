# region imports
try:
    from AlgorithmImports import *
except ImportError:
    pass
# endregion
"""ON-B5C: Circuit Breaker Screen — P3-PG-27B (Task 3.6b / V3 Amendment).

Composite decision: D_{j+1} = H(L_t, rho_j) * B(n_t) * C_b(L_b) * Q(L_b, n_t)

7-layer circuit breaker per Topstep_Optimisation_Functions.md Part 4-6:
  Layer 0: Scaling cap (XFA only) — simultaneous open position limit
  Layer 1: Preemptive hard halt — abs(L_t) + rho_j >= c * e * A
  Layer 2: Budget — n_t >= N (total trades today, NOT consecutive losses)
  Layer 3: Per-basket conditional expectancy — mu_b = r_bar_b + beta_b * L_b
  Layer 4: Correlation-adjusted Sharpe — S = mu_b / (sigma * sqrt(1 + 2*n_t*rho_bar))
  Layer 5: Session-level regime halt (VIX spike, DATA_HOLD)   [V3 amendment]
  Layer 6: Manual override (ADMIN halt)                       [V3 amendment]

V3 amendment (DEC-03): Original spec defines 5 layers (L0-L4). L5/L6 are
defensive safety layers added post-spec — kept per reconciliation decision.

Runtime position: AFTER Block 5B quality gate, BEFORE Block 6 signal output.
Non-Topstep accounts bypass CB entirely.

beta_b errata: beta_b > 0 -> positive serial correlation (losses predict losses -> shut down)
               beta_b < 0 -> mean reversion (losses predict recovery -> keep open)

Reads: P3-D23 (intraday state), P3-D25 (CB params), P3-D08 (topstep_state)
Writes: nothing (filter only — D23 updated by B7 on trade outcomes)
"""

import json
import logging
import math
from decimal import Decimal
from typing import Optional

from shared.questdb_client import get_cursor
from shared.json_helpers import parse_json, parse_json_decimal
from shared.sizing_helpers import resolve_sizing_sl


# Phase 7 — replay reset hook surface.
#
# B5C currently holds no per-session module-level state across calls
# (the local ``seen`` set in ``_load_cb_params`` is a per-invocation
# de-dup), but ``default_reset_hooks`` registers ``_reset_seen`` so the
# replay driver has an API to extend later (Stage 1B §2.2 D4).
_replay_seen: set = set()


def _get_seen() -> set:
    """Phase 7: module accessor for the replay-reset hook surface.

    See ``shared.online_replay.default_reset_hooks``.
    """
    return _replay_seen


def _reset_seen() -> None:
    """Phase 7: replay reset hook for B5C state."""
    _replay_seen.clear()

logger = logging.getLogger(__name__)

# Default thresholds (overridable via topstep_params in TSM)
DEFAULT_VIX_CB_THRESHOLD = 50.0
DEFAULT_LAMBDA = 0.0  # Minimum conditional Sharpe threshold


def run_circuit_breaker_screen(
    recommended_trades: list[str],
    final_contracts: dict,
    account_recommendation: dict,
    account_skip_reason: dict,
    accounts: list[str],
    tsm_configs: dict,
    session_id: int,
    proposed_contracts: dict | None = None,
    sl_distance: float = 4.0,
    point_value: float | Decimal = 50.0,
    fee_per_trade: float = 0.0,
    model_m: str | None = None,
    locked_strategies: dict | None = None,
    assets_detail: dict | None = None,
    open_positions: list | None = None,
) -> dict:
    """P3-PG-27B: 7-layer circuit breaker screen (spec Layers 0-4 + safety L5/L6).

    Filters recommended_trades per-account. Non-Topstep accounts bypass.

    Args:
        recommended_trades: Asset IDs recommended for trading.
        final_contracts: {asset: {account: contracts}} from Kelly sizing.
        account_recommendation: {asset: {account: "TRADE"|"BLOCKED"|...}}.
        account_skip_reason: {asset: {account: reason_str}}.
        accounts: List of account IDs to evaluate.
        tsm_configs: {account_id: tsm_dict} with topstep_optimisation, topstep_params, etc.
        session_id: Current session identifier.
        proposed_contracts: {asset: {account: contracts}} — contracts proposed for this signal.
            Falls back to final_contracts if not provided.
        sl_distance: SL distance in points (default fallback for all assets).
        point_value: Dollar value per point (default fallback for all assets).
        fee_per_trade: Expected round-turn fee per contract in dollars (phi).
        model_m: Model identifier (basket) for per-model CB param lookup.
        locked_strategies: {asset_id: strategy_dict} for per-asset SL resolution.
        assets_detail: {asset_id: detail_dict} for per-asset point_value resolution.
        open_positions: Live open position snapshot from orchestrator. List of dicts with
            "account" and "contracts" keys. Used by Layer 0 to compute current open micros
            per account. Pass [] in replay (no live positions). Defaults to None (treated as []).

    Returns:
        dict with updated recommended_trades, final_contracts, account_recommendation,
        account_skip_reason.
    """
    if proposed_contracts is None:
        proposed_contracts = final_contracts

    cb_params = _load_cb_params(accounts, model_m=model_m)
    intraday_state = _load_intraday_state(accounts, session_id=int(session_id))

    blocked_count = 0

    for u in recommended_trades:
        # Per-asset point value (fall back to scalar default).
        asset_pv = point_value
        if assets_detail:
            asset_pv = assets_detail.get(u, {}).get("point_value", point_value)

        # Phase 2 (F-04): per-asset SL distance via shared helper so B4 and
        # B5C agree on rho_j. Primary = sl_multiple × historical OR range avg
        # (P3-D29); fallbacks: strategy.threshold → DEFAULT_SL_POINTS=4.0.
        if locked_strategies and u in locked_strategies:
            asset_sl = resolve_sizing_sl(u, locked_strategies[u], asset_pv)
        else:
            asset_sl = sl_distance

        for ac_id in accounts:
            tsm = tsm_configs.get(ac_id)
            if tsm is None:
                continue

            # Non-Topstep accounts bypass CB entirely
            if not tsm.get("topstep_optimisation", False):
                continue

            if account_recommendation.get(u, {}).get(ac_id) != "TRADE":
                continue

            # Resolve per-trade contracts for rho_j computation
            contracts = proposed_contracts.get(u, {}).get(ac_id, 0)
            if contracts <= 0:
                contracts = final_contracts.get(u, {}).get(ac_id, 0)

            # Resolve per-account fee from fee_schedule if available
            ac_fee = _resolve_fee(tsm, u, fee_per_trade)

            # Run all layers
            block_result = _check_all_layers(
                ac_id=ac_id,
                asset_id=u,
                cb_param=cb_params.get(ac_id),
                intraday=intraday_state.get(ac_id),
                tsm=tsm,
                session_id=session_id,
                contracts=contracts,
                sl_distance=asset_sl,
                point_value=asset_pv,
                fee_per_trade=ac_fee,
                model_m=model_m,
                open_positions=open_positions,
            )

            if block_result:
                final_contracts.setdefault(u, {})[ac_id] = 0
                account_recommendation.setdefault(u, {})[ac_id] = "BLOCKED"
                account_skip_reason.setdefault(u, {})[ac_id] = f"Circuit breaker: {block_result}"
                blocked_count += 1
                logger.info("ON-B5C: CB blocked %s for account %s: %s", u, ac_id, block_result)

    # Re-evaluate recommended trades (remove if all accounts blocked)
    updated_recommended = []
    for u in recommended_trades:
        has_trade = any(
            account_recommendation.get(u, {}).get(ac) == "TRADE"
            for ac in accounts
        )
        if has_trade:
            updated_recommended.append(u)

    if blocked_count > 0:
        logger.info("ON-B5C: Circuit breaker blocked %d account-asset pairs", blocked_count)

    return {
        "recommended_trades": updated_recommended,
        "final_contracts": final_contracts,
        "account_recommendation": account_recommendation,
        "account_skip_reason": account_skip_reason,
    }


def _check_all_layers(
    ac_id: str,
    asset_id: str,
    cb_param: dict | None,
    intraday: dict | None,
    tsm: dict,
    session_id: int,
    contracts: int = 0,
    sl_distance: float = 4.0,
    point_value: float | Decimal = 50.0,
    fee_per_trade: float = 0.0,
    model_m: str | None = None,
    open_positions: list | None = None,
) -> str | None:
    """Check all 7 CB layers (L0-L6). Returns block reason string or None if OK.

    Composite decision per spec:
        D_{j+1} = H(L_t, rho_j) * B(n_t) * C_b(L_b) * Q(L_b, n_t)
    Plus safety layers L5 (VIX/DATA_HOLD) and L6 (manual override).
    """
    if intraday is None:
        intraday = {}

    # Layer 0: Scaling cap (XFA only — Live accounts skip)
    reason = _layer0_scaling_cap(tsm, contracts, open_positions=open_positions, ac_id=ac_id)
    if reason:
        return reason

    # Compute worst-case risk for this trade: rho_j = contracts * (SL * pv + fee)
    # D00 point_value is DECIMAL — use directly when already Decimal (Phase C).
    _pv = point_value if isinstance(point_value, Decimal) else Decimal(str(point_value))
    rho_j = Decimal(contracts) * (
        Decimal(str(sl_distance)) * _pv + Decimal(str(fee_per_trade))
    )

    # Layer 1: Preemptive hard halt — abs(L_t) + rho_j >= L_halt (per session)
    reason = _layer1_preemptive_halt(intraday, tsm, rho_j, session_id=session_id)
    if reason:
        return reason

    # Layer 2: Dollar budget — remaining < rho_j (per session)
    reason = _layer2_budget(intraday, tsm, rho_j, session_id=session_id)
    if reason:
        return reason

    # Layer 3: Per-basket conditional expectancy — mu_b = r_bar + beta_b * L_b
    # (basket keyed by (session_id, model_m) per Phase 3)
    reason = _layer3_basket_expectancy(
        cb_param, intraday, model_m, session_id=session_id,
    )
    if reason:
        return reason

    # Layer 4: Rolling basket Sharpe (60d lookback)
    reason = _layer4_correlation_sharpe(cb_param, intraday, tsm, model_m)
    if reason:
        return reason

    # Layer 5: Session-level regime halt (VIX spike, DATA_HOLD)
    reason = _layer5_session_halt(session_id)
    if reason:
        return reason

    # Layer 6: Manual override
    reason = _layer6_manual_override(ac_id)
    if reason:
        return reason

    return None


# ---------------------------------------------------------------------------
# Layer implementations
# ---------------------------------------------------------------------------

def _layer0_scaling_cap(tsm: dict, proposed_contracts: int, open_positions: list | None = None, ac_id: str = "") -> str | None:
    """Layer 0: Simultaneous open position limit (XFA only).

    XFA accounts have a scaling plan that limits max contracts held open
    simultaneously. Live accounts skip this layer entirely.

    Check: current_open_micros + proposed_micros > scaling_tier_micros -> BLOCKED.
    """
    if not tsm.get("scaling_plan_active", False):
        return None  # Live accounts or no scaling plan — skip

    scaling_tier_micros = tsm.get("scaling_tier_micros", 0)
    if scaling_tier_micros <= 0:
        return None  # No cap configured

    # Derive current open contracts from live position snapshot (passed by orchestrator).
    # Only count positions for this account — do NOT sum across accounts.
    current_open_micros = sum(
        p.get("contracts", 0)
        for p in (open_positions or [])
        if p.get("account") == ac_id
    )
    proposed_micros = proposed_contracts  # Already in micro-equivalent units

    if current_open_micros + proposed_micros > scaling_tier_micros:
        return (
            f"L0: scaling cap exceeded — open {current_open_micros} + "
            f"proposed {proposed_micros} > tier cap {scaling_tier_micros}"
        )

    return None


def _layer1_preemptive_halt(
    intraday: dict, tsm: dict, rho_j: Decimal, session_id: int = 0,
) -> str | None:
    """Layer 1: Preemptive hard halt (account survival).

    Formula: abs(L_t) + rho_j >= L_halt
    Where rho_j = contracts * (SL_distance * point_value + fee).

    PER-SESSION (2026-05-06): the relevant ``L_halt`` and ``L_t`` are now
    SCOPED TO THE CURRENT SESSION. NY's accumulated L_t no longer pollutes
    APAC's gate — each session has its own SOD-allocated L_halt and its own
    independent intraday L_t ledger. Lookup chain:

      1. intraday["effective_l_halt"] — written by the orchestrator's
         session-open hook (Phase 3a) with carryover from earlier sessions.
      2. computed_sod.session.<KEY>.L_halt — written by Command B8 at SOD
         (Phase 2). Used when the session-open hook hasn't fired yet OR
         when intraday entry is missing.
      3. computed_sod.L_halt — legacy flat scalar for backwards-compat.
      4. live c * e * A — final fallback when SOD has never run.

    This is PREEMPTIVE: blocks trades whose worst-case SL outcome would breach
    the halt threshold, not just trades where L_t has already breached it.
    """
    from shared.sod_session_budget import get_session_l_halt

    A = Decimal(str(tsm.get("current_balance", 0)))

    if A <= 0:
        return None

    rho = rho_j if isinstance(rho_j, Decimal) else Decimal(str(rho_j))

    topstep_state = parse_json_decimal(tsm.get("topstep_state"), {})
    computed_sod = topstep_state.get("computed_sod", {})

    # Per-session L_halt lookup chain.
    l_halt: Decimal | None = None
    eff_from_intraday = intraday.get("effective_l_halt")
    if eff_from_intraday is not None:
        l_halt = (
            eff_from_intraday if isinstance(eff_from_intraday, Decimal)
            else Decimal(str(eff_from_intraday))
        )
    elif session_id and session_id > 0:
        sess_halt = get_session_l_halt(computed_sod, session_id)
        if sess_halt > 0:
            l_halt = sess_halt
    if l_halt is None or l_halt <= 0:
        # Final fallback: live c * e * A (cold-start, SOD never ran).
        topstep_params = parse_json(tsm.get("topstep_params"), {})
        c = Decimal(str(topstep_params.get("c", 0.5)))
        e = Decimal(str(topstep_params.get("e", 0.01)))
        l_halt = c * e * A
        logger.warning(
            "ON-B5C: L1 falling back to live L_halt=%s for %s session=%s "
            "(no SOD per-session value)",
            l_halt, tsm.get("account_id"), session_id,
        )

    l_t_raw = intraday.get("l_t", 0)
    l_t = l_t_raw if isinstance(l_t_raw, Decimal) else Decimal(str(l_t_raw))

    projected = abs(l_t) + rho

    if projected >= l_halt:
        return (
            f"L1: preemptive halt session={session_id} — "
            f"|L_t|={abs(l_t):.0f} + rho_j={rho:.0f} = {projected:.0f} "
            f">= L_halt={l_halt:.0f}"
        )

    return None


def _layer2_budget(
    intraday: dict, tsm: dict, rho_j: Decimal, session_id: int = 0,
) -> str | None:
    """Layer 2: Remaining dollar budget — IF remaining < rho_j -> BLOCKED.

    Spec: remaining_budget = E - |L_t|; IF remaining < rho_j -> BLOCK
    where E = E_daily_exposure (daily exposure budget in dollars).

    PER-SESSION (2026-05-06): same lookup chain as ``_layer1_preemptive_halt``.
    The relevant ``E`` is the session's SOD share + carryover; the relevant
    ``L_t`` is the session's intraday cumulative.

    Blocks when worst-case signal risk exceeds the remaining session budget.
    """
    from shared.sod_session_budget import get_session_e_exposure

    A = Decimal(str(tsm.get("current_balance", 0)))

    if A <= 0:
        return None

    rho = rho_j if isinstance(rho_j, Decimal) else Decimal(str(rho_j))

    topstep_state = parse_json_decimal(tsm.get("topstep_state"), {})
    computed_sod = topstep_state.get("computed_sod", {})

    # Per-session E lookup chain.
    E: Decimal | None = None
    eff_from_intraday = intraday.get("effective_e_exposure")
    if eff_from_intraday is not None:
        E = (
            eff_from_intraday if isinstance(eff_from_intraday, Decimal)
            else Decimal(str(eff_from_intraday))
        )
    elif session_id and session_id > 0:
        sess_e = get_session_e_exposure(computed_sod, session_id)
        if sess_e > 0:
            E = sess_e
    if E is None or E <= 0:
        topstep_params = parse_json(tsm.get("topstep_params"), {})
        e = Decimal(str(topstep_params.get("e", 0.01)))
        E = e * A
        logger.warning(
            "ON-B5C: L2 falling back to live E=%s for %s session=%s "
            "(no SOD per-session value)",
            E, tsm.get("account_id"), session_id,
        )

    l_t_raw = intraday.get("l_t", 0)
    l_t = l_t_raw if isinstance(l_t_raw, Decimal) else Decimal(str(l_t_raw))
    remaining = E - abs(l_t)

    if remaining < rho:
        return (
            f"L2: dollar budget exhausted session={session_id} — "
            f"remaining={remaining:.0f} < rho_j={rho:.0f} "
            f"(E={E:.0f}, |L_t|={abs(l_t):.0f})"
        )

    return None


def _layer3_basket_expectancy(
    cb_param: dict | None,
    intraday: dict,
    model_m: str | None,
    session_id: int = 0,
) -> str | None:
    """Layer 3: Per-basket conditional expectancy filter.

    mu_b = r_bar_b + beta_b * L_b
    If mu_b <= 0 -> BLOCKED (negative expected return for this basket).

    PER-SESSION (2026-05-06): basket key is now ``"<session_id>:<model_m>"``
    so a strategy m=6 running in both NY and APAC keeps two independent
    basket P&L tallies (Isaac's spec answer Q-2). Backwards-compat: if the
    session-scoped key is absent, fall back to the legacy bare ``model_m``
    key — handles intraday state from rows written before Phase 3.

    Cold start: beta_b = 0 -> mu_b = r_bar_b > 0 (assuming positive-expectancy
    strategy). Filter never triggers until Offline Block 8 produces significant
    beta_b estimates (n >= 100, p < 0.05).
    """
    if cb_param is None:
        return None

    r_bar = Decimal(str(cb_param.get("r_bar", 0.0)))
    beta_b = Decimal(str(cb_param.get("beta_b", 0.0)))
    p_value = cb_param.get("p_value", 1.0)
    n_obs = cb_param.get("n_observations", 0)

    if n_obs == 0:
        return None

    if p_value > 0.05 or n_obs < 100:
        beta_b = Decimal("0")

    l_b_dict = intraday.get("l_b", {})
    basket_key = None
    if model_m is not None:
        # Phase 3 namespacing: prefer "<session>:<m>" if present.
        if session_id and session_id > 0:
            scoped = f"{int(session_id)}:{model_m}"
            if scoped in l_b_dict:
                basket_key = scoped
        # Fallback to bare model_m for rows written pre-Phase-3.
        if basket_key is None and str(model_m) in l_b_dict:
            basket_key = str(model_m)
    lb_raw = l_b_dict.get(basket_key, 0.0) if basket_key else 0.0
    l_b = lb_raw if isinstance(lb_raw, Decimal) else Decimal(str(lb_raw))

    mu_b = r_bar + beta_b * l_b

    if mu_b <= 0:
        return (
            f"L3: negative basket expectancy session={session_id} basket={basket_key} "
            f"— mu_b={mu_b:.2f} (r_bar={r_bar:.2f}, beta_b={beta_b:.4f}, L_b={l_b:.0f})"
        )

    return None


def _layer4_correlation_sharpe(
    cb_param: dict | None,
    intraday: dict,
    tsm: dict,
    model_m: str | None,
) -> str | None:
    """Layer 4: Rolling basket Sharpe gate.

    Spec: rolling_basket_sharpe(lookback=60d) from D03 trade history.
    If S <= lambda -> BLOCKED.

    Cold start: fewer than 10 trades in lookback -> skip (insufficient data).
    """
    topstep_params = parse_json(tsm.get("topstep_params"), {})
    lambda_threshold = topstep_params.get("lambda", DEFAULT_LAMBDA)

    returns = _get_rolling_trade_returns(lookback_days=60)

    if len(returns) < 10:
        return None  # Insufficient data for rolling Sharpe

    mean_r = sum(returns) / len(returns)
    variance = sum((r - mean_r) ** 2 for r in returns) / (len(returns) - 1)
    sigma = math.sqrt(variance) if variance > 0 else 0.0

    if sigma <= 0:
        return None  # Zero variance — skip

    S = mean_r / sigma

    if S <= lambda_threshold:
        return (
            f"L4: rolling basket Sharpe below threshold — S={S:.4f} <= "
            f"lambda={lambda_threshold} (mean={mean_r:.2f}, sigma={sigma:.2f}, "
            f"n_trades={len(returns)})"
        )

    return None


def _layer5_session_halt(session_id: int) -> str | None:
    """Layer 5: Session-level regime halt (VIX spike, DATA_HOLD count).

    Per Arch 19.6: DATA_HOLD >= 3 OR VIX > threshold -> skip session.
    """
    vix = _get_current_vix()
    if vix is None:
        logger.info("ON-B5C: VIX unavailable — Layer 5 VIX check skipped")
    if vix is not None and vix > DEFAULT_VIX_CB_THRESHOLD:
        return f"L5: VIX {vix:.1f} exceeds threshold {DEFAULT_VIX_CB_THRESHOLD}"

    data_hold_count = _get_data_hold_count()
    if data_hold_count >= 3:
        return f"L5: {data_hold_count} assets in DATA_HOLD (threshold: 3)"

    return None


def _layer6_manual_override(ac_id: str) -> str | None:
    """Layer 6: Manual override — ADMIN halt via P3-D17."""
    halted = _check_manual_halt(ac_id)
    if halted:
        return "L6: Manual halt active"
    return None


# ---------------------------------------------------------------------------
# Data loaders
# ---------------------------------------------------------------------------

def _load_cb_params(accounts: list[str], model_m: str | None = None) -> dict:
    """Load circuit breaker params from P3-D25, keyed by account_id.

    If model_m is provided, filter to that model's params.
    P3-D25 is per-account per-model: (account_id, model_m) -> params.
    """
    with get_cursor() as cur:
        if model_m is not None:
            cur.execute(
                """SELECT account_id, r_bar, beta_b, sigma, rho_bar,
                          n_observations, p_value, model_m
                   FROM p3_d25_circuit_breaker_params
                   WHERE model_m = %s
                   ORDER BY last_updated DESC""",
                (str(model_m),),
            )
        else:
            cur.execute(
                """SELECT account_id, r_bar, beta_b, sigma, rho_bar,
                          n_observations, p_value, model_m
                   FROM p3_d25_circuit_breaker_params
                   ORDER BY last_updated DESC"""
            )
        rows = cur.fetchall()

    seen = set()
    result = {}
    for r in rows:
        if r[0] in seen:
            continue
        seen.add(r[0])
        result[r[0]] = {
            "r_bar": r[1] or 0.0,
            "beta_b": r[2] or 0.0,
            "sigma": r[3] or 0.0,
            "rho_bar": r[4] or 0.0,
            "n_observations": r[5] or 0,
            "p_value": r[6] or 1.0,
            "model_m": r[7] if len(r) > 7 else None,
        }
    return result


def _load_intraday_state(accounts: list[str], session_id: int = 0) -> dict:
    """Load intraday CB state from P3-D23 for a specific session, keyed by account_id.

    Per-session-budget semantics (2026-05-06): D23 is now keyed by
    ``(account_id, session_id)`` so every session has its own L_t / n_t /
    l_b / n_b ledger, plus the SOD-locked effective_l_halt /
    effective_e_exposure / session_opened_at fields written by the
    orchestrator's session-open hook.

    Parameters
    ----------
    accounts
        Reserved for future filtering — the SQL currently returns all
        accounts and the caller decides which ones to read.
    session_id
        Filter D23 to this session_id only. Default ``0`` is interpreted as
        "no session filter" (legacy callers); production callers should
        always pass the actual session_id from the orchestrator.

    Returns
    -------
    dict[account_id, dict]
        ``{account_id: {"l_t", "n_t", "l_b", "n_b", "effective_l_halt",
                        "effective_e_exposure", "session_opened_at"}}``
        ``effective_l_halt`` / ``effective_e_exposure`` may be ``None`` if
        the orchestrator session-open hook hasn't fired yet for this
        session — callers (B5C layers) MUST fall back to D08's per-session
        SOD share via ``shared.sod_session_budget.get_session_l_halt``.
    """
    with get_cursor() as cur:
        if session_id and session_id > 0:
            cur.execute(
                """SELECT account_id, l_t, n_t, l_b, n_b,
                          effective_l_halt, effective_e_exposure,
                          session_opened_at
                   FROM p3_d23_circuit_breaker_intraday
                   WHERE session_id = %s
                   LATEST ON last_updated PARTITION BY account_id, session_id""",
                (int(session_id),),
            )
        else:
            # Legacy/no-filter path: returns ALL session rows for an account;
            # the LATEST ON collapses to one row per account_id which may
            # belong to ANY session — only used by callers that don't care
            # about per-session isolation (none in production after Phase 4).
            cur.execute(
                """SELECT account_id, l_t, n_t, l_b, n_b,
                          effective_l_halt, effective_e_exposure,
                          session_opened_at
                   FROM p3_d23_circuit_breaker_intraday
                   LATEST ON last_updated PARTITION BY account_id"""
            )
        rows = cur.fetchall()

    result = {}
    for r in rows:
        lt_raw = r[1]
        if lt_raw is None:
            lt_dec = Decimal("0")
        elif isinstance(lt_raw, Decimal):
            lt_dec = lt_raw
        else:
            lt_dec = Decimal(str(lt_raw))
        eff_l_halt = r[5]
        if eff_l_halt is not None and not isinstance(eff_l_halt, Decimal):
            eff_l_halt = Decimal(str(eff_l_halt))
        eff_e = r[6]
        if eff_e is not None and not isinstance(eff_e, Decimal):
            eff_e = Decimal(str(eff_e))
        result[r[0]] = {
            "l_t": lt_dec,
            "n_t": r[2] or 0,
            "l_b": parse_json_decimal(r[3], {}),
            "n_b": parse_json(r[4], {}),
            "effective_l_halt": eff_l_halt,
            "effective_e_exposure": eff_e,
            "session_opened_at": r[7],
        }
    return result


def _get_rolling_trade_returns(lookback_days: int = 60) -> list[float]:
    """Query per-trade P&L from D03 for rolling basket Sharpe calculation."""
    try:
        with get_cursor() as cur:
            cur.execute(
                """SELECT pnl FROM p3_d03_trade_outcome_log
                   WHERE timestamp > dateadd('d', -%s, now())
                   ORDER BY timestamp DESC""",
                (lookback_days,),
            )
            rows = cur.fetchall()
        out: list[float] = []
        for r in rows:
            if r[0] is None:
                continue
            v = r[0]
            out.append(float(v))
        return out
    except Exception:
        # Table may not exist on fresh deployment (cold start) — return empty
        return []


def _resolve_fee(tsm: dict, asset_id: str, fallback_fee: float) -> float:
    """Resolve per-contract round-turn fee from TSM fee_schedule.

    Priority: fee_schedule.fees_by_instrument[asset].round_turn
    Fallback: commission_per_contract * 2 (round-trip)
    Last resort: fallback_fee parameter.
    """
    fee_schedule = parse_json_decimal(tsm.get("fee_schedule"), {})

    fees_by_instrument = fee_schedule.get("fees_by_instrument", {})
    instrument_fee = fees_by_instrument.get(asset_id, {})
    if isinstance(instrument_fee, dict) and "round_turn" in instrument_fee:
        return float(Decimal(str(instrument_fee["round_turn"])))

    cpc = tsm.get("commission_per_contract")
    if cpc is not None and Decimal(str(cpc)) > 0:
        return float(Decimal(str(cpc)) * Decimal(2))

    return fallback_fee


def _get_current_vix() -> float | None:
    """Get most recent VIX close from CSV provider.

    Used by L5 session halt: VIX > threshold blocks all trading.
    """
    from shared.vix_provider import get_latest_vix_close
    return get_latest_vix_close()


def _get_data_hold_count() -> int:
    """Count assets in DATA_HOLD status."""
    with get_cursor() as cur:
        cur.execute(
            """SELECT count() FROM p3_d00_asset_universe
               WHERE captain_status = 'DATA_HOLD'"""
        )
        row = cur.fetchone()
    return row[0] if row and row[0] else 0


def _check_manual_halt(ac_id: str) -> bool:
    """Check if account has a manual halt active. Stub for V1."""
    return False


