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
  Layer 5: Session-level regime halt (VIX spike, DATA_HOLD)
  Layer 6: Manual override (ADMIN halt)

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
from typing import Optional

from shared.questdb_client import get_cursor

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
    point_value: float = 50.0,
    fee_per_trade: float = 0.0,
    model_m: str | None = None,
    locked_strategies: dict | None = None,
    assets_detail: dict | None = None,
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

    Returns:
        dict with updated recommended_trades, final_contracts, account_recommendation,
        account_skip_reason.
    """
    if proposed_contracts is None:
        proposed_contracts = final_contracts

    cb_params = _load_cb_params(accounts, model_m=model_m)
    intraday_state = _load_intraday_state(accounts)

    blocked_count = 0

    for u in recommended_trades:
        # Per-asset SL distance and point value (fall back to scalar defaults)
        asset_sl = sl_distance
        asset_pv = point_value
        if locked_strategies:
            asset_sl = locked_strategies.get(u, {}).get("threshold", sl_distance)
        if assets_detail:
            asset_pv = assets_detail.get(u, {}).get("point_value", point_value)

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
    point_value: float = 50.0,
    fee_per_trade: float = 0.0,
    model_m: str | None = None,
) -> str | None:
    """Check all 7 CB layers (L0-L6). Returns block reason string or None if OK.

    Composite decision per spec:
        D_{j+1} = H(L_t, rho_j) * B(n_t) * C_b(L_b) * Q(L_b, n_t)
    Plus safety layers L5 (VIX/DATA_HOLD) and L6 (manual override).
    """
    if intraday is None:
        intraday = {}

    # Layer 0: Scaling cap (XFA only — Live accounts skip)
    reason = _layer0_scaling_cap(tsm, contracts)
    if reason:
        return reason

    # Compute worst-case risk for this trade: rho_j = contracts * (SL * pv + fee)
    rho_j = contracts * (sl_distance * point_value + fee_per_trade)

    # Layer 1: Preemptive hard halt — abs(L_t) + rho_j >= c * e * A
    reason = _layer1_preemptive_halt(intraday, tsm, rho_j)
    if reason:
        return reason

    # Layer 2: Budget — n_t >= N (total trades today)
    reason = _layer2_budget(intraday, tsm, fee_per_trade)
    if reason:
        return reason

    # Layer 3: Per-basket conditional expectancy — mu_b = r_bar + beta_b * L_b
    reason = _layer3_basket_expectancy(cb_param, intraday, model_m)
    if reason:
        return reason

    # Layer 4: Correlation-adjusted conditional Sharpe
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

def _layer0_scaling_cap(tsm: dict, proposed_contracts: int) -> str | None:
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

    current_open_micros = tsm.get("current_open_micros", 0)
    proposed_micros = proposed_contracts  # Already in micro-equivalent units

    if current_open_micros + proposed_micros > scaling_tier_micros:
        return (
            f"L0: scaling cap exceeded — open {current_open_micros} + "
            f"proposed {proposed_micros} > tier cap {scaling_tier_micros}"
        )

    return None


def _layer1_preemptive_halt(intraday: dict, tsm: dict, rho_j: float) -> str | None:
    """Layer 1: Preemptive hard halt (account survival).

    Formula: abs(L_t) + rho_j >= c * e * A
    Where rho_j = contracts * (SL_distance * point_value + fee).

    This is PREEMPTIVE: blocks trades whose worst-case SL outcome would breach
    the halt threshold, not just trades where L_t has already breached it.
    When H = 0, all trading stops. No exceptions.
    """
    topstep_params = _parse_json(tsm.get("topstep_params"), {})

    c = topstep_params.get("c", 0.5)    # Hard halt fraction
    e = topstep_params.get("e", 0.01)   # Daily exposure fraction
    A = tsm.get("current_balance", 0)

    if A <= 0:
        return None  # Cannot compute — skip (safety layers still apply)

    l_halt = c * e * A
    l_t = intraday.get("l_t", 0.0)

    projected = abs(l_t) + rho_j

    if projected >= l_halt:
        return (
            f"L1: preemptive halt — |L_t|={abs(l_t):.0f} + rho_j={rho_j:.0f} "
            f"= {projected:.0f} >= L_halt={l_halt:.0f}"
        )

    return None


def _layer2_budget(intraday: dict, tsm: dict, fee_per_trade: float = 0.0) -> str | None:
    """Layer 2: Remaining budget — n_t >= N -> BLOCKED.

    N = floor((e * A) / (MDD * p + phi)) per spec Part 3.2.
    MDD is read from TSM config (not hardcoded) so changes propagate automatically.
    n_t is total trades completed today (all baskets), NOT consecutive losses.
    """
    topstep_params = _parse_json(tsm.get("topstep_params"), {})

    p = topstep_params.get("p", 0.005)  # Fraction of MDD% risked per trade
    e = topstep_params.get("e", 0.01)   # Daily exposure fraction
    A = tsm.get("current_balance", 0)
    mdd = tsm.get("max_drawdown_limit") or tsm.get("max_daily_drawdown") or 4500.0

    if A <= 0 or p <= 0:
        return None

    # N(A, p, e, phi) = floor((e * A) / (MDD * p + phi))
    denominator = mdd * p + fee_per_trade
    if denominator <= 0:
        return None

    N = math.floor((e * A) / denominator)

    n_t = intraday.get("n_t", 0)

    if n_t >= N:
        return f"L2: budget exhausted — n_t={n_t} >= N={N} (max trades today)"

    return None


def _layer3_basket_expectancy(
    cb_param: dict | None,
    intraday: dict,
    model_m: str | None,
) -> str | None:
    """Layer 3: Per-basket conditional expectancy filter.

    mu_b = r_bar_b + beta_b * L_b
    If mu_b <= 0 -> BLOCKED (negative expected return for this basket).

    Cold start: beta_b = 0 -> mu_b = r_bar_b > 0 (assuming positive-expectancy
    strategy). Filter never triggers until Offline Block 8 produces significant
    beta_b estimates (n >= 100, p < 0.05).
    """
    if cb_param is None:
        return None  # No CB params available — cold start, skip

    r_bar = cb_param.get("r_bar", 0.0)
    beta_b = cb_param.get("beta_b", 0.0)
    p_value = cb_param.get("p_value", 1.0)
    n_obs = cb_param.get("n_observations", 0)

    # Cold start: spec says "beta_b=0, layers 3-4 disabled" — skip when
    # no trade observations exist yet (r_bar and beta_b are both zero).
    if n_obs == 0:
        return None

    # Significance gate: only use beta_b if p < 0.05 AND n >= 100
    if p_value > 0.05 or n_obs < 100:
        beta_b = 0.0  # Cold start / insignificant — basket defaults to "always open"

    # Get per-basket cumulative P&L
    l_b_dict = intraday.get("l_b", {})
    basket_key = str(model_m) if model_m is not None else None
    l_b = l_b_dict.get(basket_key, 0.0) if basket_key else 0.0

    mu_b = r_bar + beta_b * l_b

    if mu_b <= 0:
        return (
            f"L3: negative basket expectancy — mu_b={mu_b:.2f} "
            f"(r_bar={r_bar:.2f}, beta_b={beta_b:.4f}, L_b={l_b:.0f})"
        )

    return None


def _layer4_correlation_sharpe(
    cb_param: dict | None,
    intraday: dict,
    tsm: dict,
    model_m: str | None,
) -> str | None:
    """Layer 4: Correlation-adjusted conditional Sharpe.

    S = mu_b / (sigma * sqrt(1 + 2 * n_t * rho_bar))
    If S <= lambda -> BLOCKED.

    Cold start: rho_bar = 0 -> denominator = sigma -> S = mu_b / sigma
    (unconditional Sharpe). With lambda = 0 (default), filter never triggers
    if mu_b > 0 (which is guaranteed if Layer 3 passed).
    """
    if cb_param is None:
        return None

    r_bar = cb_param.get("r_bar", 0.0)
    beta_b = cb_param.get("beta_b", 0.0)
    sigma = cb_param.get("sigma", 0.0)
    rho_bar = cb_param.get("rho_bar", 0.0)
    p_value = cb_param.get("p_value", 1.0)
    n_obs = cb_param.get("n_observations", 0)

    # Cold start: spec says "beta_b=0, layers 3-4 disabled"
    if n_obs == 0:
        return None

    # Significance gate for beta_b
    if p_value > 0.05 or n_obs < 100:
        beta_b = 0.0

    if sigma <= 0:
        return None  # Cannot compute Sharpe — skip

    # Get per-basket cumulative P&L
    l_b_dict = intraday.get("l_b", {})
    basket_key = str(model_m) if model_m is not None else None
    l_b = l_b_dict.get(basket_key, 0.0) if basket_key else 0.0

    mu_b = r_bar + beta_b * l_b

    # Marginal portfolio variance denominator
    n_t = intraday.get("n_t", 0)
    denominator = sigma * math.sqrt(1.0 + 2.0 * n_t * rho_bar)

    if denominator <= 0:
        return None  # Edge case — skip

    S = mu_b / denominator

    # Lambda threshold from topstep_params
    topstep_params = _parse_json(tsm.get("topstep_params"), {})
    lambda_threshold = topstep_params.get("lambda", DEFAULT_LAMBDA)

    if S <= lambda_threshold:
        return (
            f"L4: Sharpe below threshold — S={S:.4f} <= lambda={lambda_threshold} "
            f"(mu_b={mu_b:.2f}, sigma={sigma:.2f}, n_t={n_t}, rho_bar={rho_bar:.4f})"
        )

    return None


def _layer5_session_halt(session_id: int) -> str | None:
    """Layer 5: Session-level regime halt (VIX spike, DATA_HOLD count).

    Per Arch 19.6: DATA_HOLD >= 3 OR VIX > threshold -> skip session.
    """
    vix = _get_current_vix()
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


def _load_intraday_state(accounts: list[str]) -> dict:
    """Load intraday CB state from P3-D23, keyed by account_id."""
    with get_cursor() as cur:
        cur.execute(
            """SELECT account_id, l_t, n_t, l_b, n_b
               FROM p3_d23_circuit_breaker_intraday
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
            "l_t": r[1] or 0.0,
            "n_t": r[2] or 0,
            "l_b": _parse_json(r[3], {}),
            "n_b": _parse_json(r[4], {}),
        }
    return result


def _resolve_fee(tsm: dict, asset_id: str, fallback_fee: float) -> float:
    """Resolve per-contract round-turn fee from TSM fee_schedule.

    Priority: fee_schedule.fees_by_instrument[asset].round_turn
    Fallback: commission_per_contract * 2 (round-trip)
    Last resort: fallback_fee parameter.
    """
    fee_schedule = _parse_json(tsm.get("fee_schedule"), {})

    fees_by_instrument = fee_schedule.get("fees_by_instrument", {})
    instrument_fee = fees_by_instrument.get(asset_id, {})
    if isinstance(instrument_fee, dict) and "round_turn" in instrument_fee:
        return float(instrument_fee["round_turn"])

    # Fallback: commission_per_contract * 2
    cpc = tsm.get("commission_per_contract")
    if cpc is not None and cpc > 0:
        return float(cpc) * 2.0

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


def _parse_json(raw, default):
    if raw is None:
        return default
    if isinstance(raw, (dict, list)):
        return raw
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return default
