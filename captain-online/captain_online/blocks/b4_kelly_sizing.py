# region imports
try:
    from AlgorithmImports import *
except ImportError:
    pass
# endregion
"""ON-B4: Kelly Sizing Under Constraints — P3-PG-24 (Task 3.4 / ON lines 710-892).

Computes optimal contract sizing per asset per account for the CURRENT USER.
This block runs once per user per session (per-user deployment loop).

Pipeline:
  1. Silo drawdown check (>30% → BLOCKED all)
  2. Blended Kelly across regimes (Paper 219)
  3. Parameter uncertainty shrinkage (Paper 217)
  4. Robust Kelly fallback during high uncertainty (Paper 218)
  5. AIM modifier application
  6. User-level Kelly ceiling
  7. Per-account sizing with risk_goal adjustment
  8. TSM hard constraints (MDD, MLL, margin, contracts, scaling)
  9. V3 Fee integration (risk_per_contract + expected_fee)
  10. V3 4-way min (kelly, tsm_cap, topstep_daily_cap, scaling_cap)
  11. User-level portfolio risk cap
  12. Level 2 sizing override

Reads: P3-D05 (EWMA), P3-D08 (TSM), P3-D12 (Kelly), P3-D16 (user silo),
       regime_probs (B2), combined_modifier (B3)
Writes: nothing (pure computation — signals written by B6)
"""

import json
import logging
import math
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


def run_kelly_sizing(
    active_assets: list[str],
    regime_probs: dict,
    regime_uncertain: dict,
    combined_modifier: dict,
    kelly_params: dict,
    ewma_states: dict,
    tsm_configs: dict,
    sizing_overrides: dict,
    user_silo: dict,
    locked_strategies: dict,
    assets_detail: dict,
    session_id: int,
) -> dict | None:
    """P3-PG-24: Kelly sizing under constraints for one user.

    Returns:
        dict with final_contracts, account_recommendation, account_skip_reason
        or None if user is blocked (silo drawdown).
    """
    user_id = user_silo.get("user_id", "unknown")
    accounts = _parse_json(user_silo.get("accounts", "[]"), [])

    logger.info("ON-B4: Kelly sizing for user %s (%d accounts, %d assets)",
                user_id, len(accounts), len(active_assets))

    # Step 0: Silo-level drawdown check
    starting_capital = user_silo.get("starting_capital", 0)
    total_capital = user_silo.get("total_capital", 0)
    max_silo_dd = _load_system_param("max_silo_drawdown_threshold", 0.30)

    if starting_capital > 0:
        silo_drawdown_pct = 1 - (total_capital / starting_capital)
        if silo_drawdown_pct > max_silo_dd:
            logger.warning("ON-B4: SILO DRAWDOWN %.1f%% > %.1f%% — user %s BLOCKED",
                           silo_drawdown_pct * 100, max_silo_dd * 100, user_id)
            # NOTIFY: CRITICAL alert for silo drawdown (P3-PG-24 lines 734-736)
            try:
                from shared.redis_client import get_redis_client, CH_ALERTS
                client = get_redis_client()
                client.publish(CH_ALERTS, json.dumps({
                    "type": "SILO_DRAWDOWN",
                    "user_id": user_id,
                    "priority": "CRITICAL",
                    "message": f"CRITICAL: Silo drawdown at {silo_drawdown_pct:.1%}. All trading halted for user {user_id}.",
                    "silo_drawdown_pct": silo_drawdown_pct,
                    "timestamp": datetime.now().isoformat(),
                }))
            except Exception as e:
                logger.error("Failed to publish silo drawdown alert: %s", e)
            # Block all assets/accounts
            final_contracts = {}
            account_recommendation = {}
            account_skip_reason = {}
            for u in active_assets:
                final_contracts[u] = {ac: 0 for ac in accounts}
                account_recommendation[u] = {ac: "BLOCKED" for ac in accounts}
                account_skip_reason[u] = {ac: "SILO_DRAWDOWN_LIMIT" for ac in accounts}
            return {
                "final_contracts": final_contracts,
                "account_recommendation": account_recommendation,
                "account_skip_reason": account_skip_reason,
                "silo_blocked": True,
            }

    final_contracts = {}
    account_recommendation = {}
    account_skip_reason = {}

    user_kelly_ceiling = user_silo.get("user_kelly_ceiling", 1.0)

    for u in active_assets:
        final_contracts[u] = {}
        account_recommendation[u] = {}
        account_skip_reason[u] = {}

        # Step 1: Blended Kelly across regimes (Paper 219)
        blended_kelly = 0.0
        r_probs = regime_probs.get(u, {"LOW_VOL": 0.5, "HIGH_VOL": 0.5})
        for regime in ("LOW_VOL", "HIGH_VOL"):
            # Find Kelly for this asset/regime (any session)
            regime_kelly = _get_kelly_for_regime(u, regime, kelly_params, session_id)
            regime_weight = r_probs.get(regime, 0.5)
            blended_kelly += regime_weight * regime_kelly

        # Step 2: Shrinkage (Paper 217)
        shrinkage = _get_shrinkage(u, kelly_params, session_id)
        adjusted_kelly = blended_kelly * shrinkage

        # Step 3: Robust Kelly fallback (Paper 218)
        if regime_uncertain.get(u, False):
            dominant_regime = max(r_probs, key=r_probs.get)
            ewma = _get_ewma_for_regime(u, dominant_regime, ewma_states, session_id)
            if ewma:
                from captain_online.blocks.b1_features import get_return_bounds, compute_robust_kelly
                bounds = get_return_bounds(ewma)
                std_kelly = adjusted_kelly
                robust = compute_robust_kelly(bounds, std_kelly)
                adjusted_kelly = min(adjusted_kelly, robust)

        # Step 4: AIM modifier
        modifier = combined_modifier.get(u, 1.0)
        kelly_with_aim = adjusted_kelly * modifier

        # Step 5: User-level Kelly ceiling
        kelly_with_aim = min(kelly_with_aim, user_kelly_ceiling)

        # Step 6: Per-account sizing
        asset_detail = assets_detail.get(u, {})
        strategy = locked_strategies.get(u, {})
        strategy_sl = strategy.get("threshold", 4.0)  # SL distance in points
        point_value = asset_detail.get("point_value", 50.0)

        for ac_id in accounts:
            tsm = tsm_configs.get(ac_id)
            if tsm is None:
                final_contracts[u][ac_id] = 0
                account_recommendation[u][ac_id] = "SKIP"
                account_skip_reason[u][ac_id] = "No TSM config"
                continue

            # Check instrument permissions
            permissions = tsm.get("instrument_permissions", [])
            if permissions and u not in permissions:
                final_contracts[u][ac_id] = 0
                account_recommendation[u][ac_id] = "SKIP"
                account_skip_reason[u][ac_id] = "Not eligible for this asset"
                continue

            risk_goal = tsm.get("risk_goal", "GROW_CAPITAL")

            # Step 6a: Risk-goal adjustment
            account_kelly = _apply_risk_goal(kelly_with_aim, risk_goal, tsm)

            # Step 6b: TSM hard constraints
            classification = tsm.get("classification", {})
            category = classification.get("category", "BROKER_RETAIL")
            tsm_cap = _compute_tsm_cap(tsm, category, strategy_sl, point_value)

            # V3: Topstep daily cap and scaling cap
            topstep_daily_cap = _compute_topstep_daily_cap(tsm, strategy_sl, point_value)
            current_open_micros = tsm.get("current_open_micros", 0)
            scaling_cap = _compute_scaling_cap(tsm, current_open_micros)

            # Step 6c: Compute final contracts
            account_capital = tsm.get("current_balance", 0)

            # Risk per contract from EWMA (per-contract $ risk)
            dominant_regime = max(r_probs, key=r_probs.get)
            ewma = _get_ewma_for_regime(u, dominant_regime, ewma_states, session_id)
            risk_per_contract = ewma["avg_loss"] if ewma and ewma.get("avg_loss", 0) > 0 else strategy_sl * point_value

            # V3: Fee integration — add expected fee to risk per contract
            expected_fee = _get_expected_fee(tsm, u)
            risk_per_contract_with_fee = risk_per_contract + expected_fee

            if risk_per_contract_with_fee <= 0:
                risk_per_contract_with_fee = strategy_sl * point_value

            kelly_contracts = account_kelly * account_capital / risk_per_contract_with_fee if risk_per_contract_with_fee > 0 else 0

            # V3: 4-way min
            raw_contracts = math.floor(kelly_contracts)
            final = min(raw_contracts, tsm_cap, topstep_daily_cap, scaling_cap)
            final = max(final, 0)
            final_contracts[u][ac_id] = final

            # Step 6d: Recommendation
            remaining_mdd = None
            if category in ("PROP_EVAL", "PROP_FUNDED", "PROP_SCALING"):
                mdd_limit = tsm.get("max_drawdown_limit")
                current_dd = tsm.get("current_drawdown", 0)
                remaining_mdd = (mdd_limit - current_dd) if mdd_limit is not None else None

            if final == 0:
                max_daily_loss = tsm.get("max_daily_loss")
                daily_used = tsm.get("daily_loss_used", 0)
                if max_daily_loss and daily_used >= max_daily_loss:
                    account_recommendation[u][ac_id] = "BLOCKED"
                    account_skip_reason[u][ac_id] = "Daily loss limit reached"
                elif remaining_mdd is not None and remaining_mdd < strategy_sl * point_value:
                    account_recommendation[u][ac_id] = "BLOCKED"
                    account_skip_reason[u][ac_id] = "Insufficient MDD headroom"
                else:
                    account_recommendation[u][ac_id] = "SKIP"
                    account_skip_reason[u][ac_id] = "Position size rounded to 0"
            else:
                account_recommendation[u][ac_id] = "TRADE"
                account_skip_reason[u][ac_id] = None

        # Step 7: User-level portfolio risk cap
        total_risk = sum(
            final_contracts[u].get(ac, 0) * strategy_sl * point_value
            for ac in accounts
        )
        max_risk_pct = user_silo.get("max_portfolio_risk_pct", 0.10)
        max_risk = max_risk_pct * total_capital if total_capital > 0 else float("inf")

        if total_risk > max_risk and total_risk > 0:
            scale_factor = max_risk / total_risk
            for ac_id in accounts:
                final_contracts[u][ac_id] = math.floor(final_contracts[u].get(ac_id, 0) * scale_factor)

        # Step 8: Level 2 sizing override
        override = sizing_overrides.get(u)
        if override is not None:
            override_val = float(override) if not isinstance(override, float) else override
            for ac_id in accounts:
                final_contracts[u][ac_id] = math.floor(final_contracts[u].get(ac_id, 0) * override_val)
                if final_contracts[u][ac_id] == 0 and account_recommendation[u].get(ac_id) == "TRADE":
                    account_recommendation[u][ac_id] = "REDUCED_TO_ZERO"
                    account_skip_reason[u][ac_id] = "Level 2 sizing override"

    return {
        "final_contracts": final_contracts,
        "account_recommendation": account_recommendation,
        "account_skip_reason": account_skip_reason,
        "silo_blocked": False,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_kelly_for_regime(asset_id: str, regime: str, kelly_params: dict, session_id: int) -> float:
    """Get Kelly fraction for asset/regime. Falls back to any session."""
    key = (asset_id, regime, session_id)
    entry = kelly_params.get(key)
    if entry:
        return entry.get("kelly_full", 0.0)
    # Fallback: try any session
    for k, v in kelly_params.items():
        if k[0] == asset_id and k[1] == regime:
            return v.get("kelly_full", 0.0)
    return 0.0


def _get_shrinkage(asset_id: str, kelly_params: dict, session_id: int) -> float:
    """Get shrinkage factor for asset."""
    for k, v in kelly_params.items():
        if k[0] == asset_id:
            return v.get("shrinkage_factor", 1.0)
    return 1.0


def _get_ewma_for_regime(asset_id: str, regime: str, ewma_states: dict, session_id: int) -> dict | None:
    """Get EWMA state for asset/regime."""
    key = (asset_id, regime, session_id)
    entry = ewma_states.get(key)
    if entry:
        return entry
    # Fallback: try any session
    for k, v in ewma_states.items():
        if k[0] == asset_id and k[1] == regime:
            return v
    return None


def _apply_risk_goal(kelly: float, risk_goal: str, tsm: dict) -> float:
    """Apply risk-goal-specific Kelly adjustment."""
    if risk_goal == "PASS_EVAL":
        pass_prob = tsm.get("pass_probability")
        if pass_prob is not None and pass_prob < 0.5:
            return kelly * 0.5
        elif pass_prob is not None and pass_prob < 0.7:
            return kelly * 0.7
        return kelly * 0.85
    elif risk_goal == "PRESERVE_CAPITAL":
        return kelly * 0.5
    else:  # GROW_CAPITAL
        return kelly


def _compute_tsm_cap(tsm: dict, category: str, strategy_sl: float, point_value: float) -> int:
    """Compute TSM constraint cap on contracts."""
    if category in ("PROP_EVAL", "PROP_FUNDED", "PROP_SCALING"):
        mdd_limit = tsm.get("max_drawdown_limit")
        current_dd = tsm.get("current_drawdown", 0)
        remaining_mdd = (mdd_limit - current_dd) if mdd_limit is not None else 0

        # Budget divisor
        eval_end = tsm.get("evaluation_end_date")
        budget_divisor = _load_system_param("tsm_budget_divisor_default", 20)
        if eval_end:
            try:
                if isinstance(eval_end, str):
                    eval_end = datetime.fromisoformat(eval_end)
                remaining_days = max((eval_end.date() - datetime.now().date()).days, 1)
                budget_divisor = remaining_days
            except (ValueError, TypeError):
                pass

        daily_budget = remaining_mdd / budget_divisor if budget_divisor > 0 else 0
        risk_per_contract = strategy_sl * point_value
        max_by_mdd = math.floor(daily_budget / risk_per_contract) if risk_per_contract > 0 else 0

        max_daily_loss = tsm.get("max_daily_loss")
        daily_used = tsm.get("daily_loss_used", 0)
        if max_daily_loss:
            remaining_mll = max_daily_loss - daily_used
            max_by_mll = math.floor(remaining_mll / risk_per_contract) if risk_per_contract > 0 else 0
        else:
            max_by_mll = 999

        max_contracts = tsm.get("max_contracts") or 999

        # Scaling plan
        cap = min(max_by_mdd, max_by_mll, max_contracts)
        scaling_plan = tsm.get("scaling_plan")
        if scaling_plan and isinstance(scaling_plan, list):
            balance = tsm.get("current_balance", 0)
            for tier in reversed(scaling_plan):
                if balance >= tier.get("balance_threshold", float("inf")):
                    cap = min(cap, tier.get("max_contracts", 999))
                    break

        return max(cap, 0)

    elif category in ("BROKER_RETAIL", "BROKER_INSTITUTIONAL"):
        margin = tsm.get("margin_per_contract") or 0
        buffer = tsm.get("margin_buffer_pct") or 1.5
        balance = tsm.get("current_balance", 0)
        if margin > 0:
            cap = math.floor(balance / (margin * buffer))
        else:
            cap = 999
        max_contracts = tsm.get("max_contracts")
        if max_contracts:
            cap = min(cap, max_contracts)
        return max(cap, 0)

    return 999


def _compute_topstep_daily_cap(tsm: dict, strategy_sl: float = 4.0, point_value: float = 50.0) -> int:
    """V3: Topstep daily contract cap from SOD exposure budget E.

    E = e * A (computed by reconciliation SOD).
    Cap = floor(E / (strategy_sl * point_value))
    """
    if not tsm.get("topstep_optimisation", False):
        return 999
    topstep_state = _parse_json(tsm.get("topstep_state"), {})
    computed_sod = topstep_state.get("computed_sod", {})
    E = computed_sod.get("E_daily_exposure", 0)
    if E <= 0:
        # Fallback to static cap
        topstep_params = _parse_json(tsm.get("topstep_params"), {})
        return topstep_params.get("daily_contract_cap", 999)
    risk_per_trade = strategy_sl * point_value
    if risk_per_trade <= 0:
        return 999
    return max(math.floor(E / risk_per_trade), 0)


def _compute_scaling_cap(tsm: dict, current_open_micros: int = 0) -> int:
    """V3: Scaling cap — available capacity in micro-equivalent contracts.

    Per spec: available = tier_micros - current_open_micros
    Live accounts have NO scaling plan → returns 999.
    XFA accounts only.
    """
    if not tsm.get("scaling_plan_active", False):
        return 999
    tier_micros = tsm.get("scaling_tier_micros", 0)
    if tier_micros <= 0:
        return 999
    available = tier_micros - current_open_micros
    return max(available, 0)


def _get_expected_fee(tsm: dict, asset_id: str) -> float:
    """V3: Get expected fee per contract (round-trip) from fee_schedule.

    Per Nomaan_Edits_Fees.md Change 2:
    Read from fee_schedule.fees_by_instrument first, fall back to commission_per_contract.
    """
    fee_schedule = _parse_json(tsm.get("fee_schedule"), None)
    if fee_schedule:
        fees_by_instrument = fee_schedule.get("fees_by_instrument", {})
        if asset_id in fees_by_instrument:
            return fees_by_instrument[asset_id].get("round_turn", 0.0)
        # Fallback to default in fee_schedule
        default_fee = fee_schedule.get("default_round_turn", 0.0)
        if default_fee > 0:
            return default_fee

    # Fallback to commission_per_contract (× 2 for round trip)
    cpc = tsm.get("commission_per_contract", 0.0)
    return cpc * 2 if cpc else 0.0


def _load_system_param(key: str, default):
    """Load a system parameter from P3-D17."""
    try:
        from shared.questdb_client import get_cursor
        with get_cursor() as cur:
            cur.execute(
                "SELECT param_value FROM p3_d17_system_monitor_state "
                "WHERE param_key = %s ORDER BY last_updated DESC LIMIT 1",
                (key,),
            )
            row = cur.fetchone()
        if row and row[0]:
            return type(default)(row[0])
    except Exception:
        pass
    return default


def _parse_json(raw, default):
    if raw is None:
        return default
    if isinstance(raw, (dict, list)):
        return raw
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return default
