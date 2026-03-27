# region imports
try:
    from AlgorithmImports import *
except ImportError:
    pass
# endregion
"""Captain Command — Block 4: TSM Management (P3-PG-34).

Loads, validates, and manages per-account Trading System Model (TSM) JSON
files from ``/captain/config/tsm/providers/``.  Handles parameter
translation for Online sizing blocks.

V3 additions:
- ``fee_schedule`` with per-instrument fees (fallback to commission_per_contract).
- ``topstep_optimisation`` flag and ``topstep_params``.
- ``payout_rules`` and ``scaling_plan_active``.

Spec: Program3_Command.md lines 437-517
"""

import json
import logging
import os
from datetime import datetime
from typing import Any

from shared.questdb_client import get_cursor
from shared.journal import write_checkpoint

logger = logging.getLogger(__name__)

TSM_CONFIG_DIR = os.environ.get("TSM_CONFIG_DIR", "/captain/config/tsm/providers")

# ---------------------------------------------------------------------------
# TSM schema validation
# ---------------------------------------------------------------------------

_REQUIRED_FIELDS = [
    "name",
    "classification",
    "starting_balance",
    "max_drawdown_limit",
    "max_contracts",
]

_CLASSIFICATION_REQUIRED = ["provider", "category", "stage", "risk_goal"]

_VALID_CATEGORIES = {
    "PROP_EVAL", "PROP_FUNDED", "PROP_SCALING",
    "BROKER_RETAIL", "BROKER_INSTITUTIONAL",
    "PERSONAL", "INSTITUTION",
}
_VALID_STAGES = {"STAGE_1", "STAGE_2", "STAGE_3", "XFA", "LIVE", "FUNDED", "N_A"}
_VALID_RISK_GOALS = {"PASS_EVAL", "PRESERVE_CAPITAL", "GROW_CAPITAL", "PRESERVE", "GROW"}


def validate_tsm(tsm: dict) -> dict:
    """Validate a TSM JSON object.

    Returns
    -------
    dict
        ``{valid: bool, errors: list[str], warnings: list[str]}``
    """
    errors: list[str] = []
    warnings: list[str] = []

    # Required top-level fields
    for field in _REQUIRED_FIELDS:
        if field not in tsm or tsm[field] is None:
            errors.append(f"Missing required field: {field}")

    if errors:
        return {"valid": False, "errors": errors, "warnings": warnings}

    # Classification block
    classification = tsm.get("classification", {})
    if not isinstance(classification, dict):
        errors.append("classification must be a dict")
    else:
        for field in _CLASSIFICATION_REQUIRED:
            if field not in classification:
                errors.append(f"classification missing field: {field}")
        if classification.get("category") not in _VALID_CATEGORIES:
            errors.append(f"Invalid category: {classification.get('category')}")
        if classification.get("stage") not in _VALID_STAGES:
            errors.append(f"Invalid stage: {classification.get('stage')}")
        if classification.get("risk_goal") not in _VALID_RISK_GOALS:
            errors.append(f"Invalid risk_goal: {classification.get('risk_goal')}")

    # Numeric sanity
    if tsm.get("starting_balance", 0) <= 0:
        errors.append("starting_balance must be positive")
    if tsm.get("max_drawdown_limit", 0) <= 0:
        errors.append("max_drawdown_limit must be positive")
    if tsm.get("max_contracts", 0) <= 0:
        errors.append("max_contracts must be positive")

    # Optional: max_daily_loss
    mll = tsm.get("max_daily_loss")
    if mll is not None and mll <= 0:
        warnings.append("max_daily_loss should be positive if set")

    # V3: fee_schedule validation
    fee_sched = tsm.get("fee_schedule")
    if fee_sched:
        if not isinstance(fee_sched, dict):
            errors.append("fee_schedule must be a dict")
        else:
            fees_by_inst = fee_sched.get("fees_by_instrument", {})
            for inst, fees in fees_by_inst.items():
                rt = fees.get("round_turn")
                if rt is None or rt < 0:
                    warnings.append(f"fee_schedule.{inst}.round_turn missing or negative")
    elif tsm.get("commission_per_contract") is None:
        warnings.append("Neither fee_schedule nor commission_per_contract set — fees will be 0")

    # V3: payout_rules validation
    payout = tsm.get("payout_rules")
    if payout and isinstance(payout, dict):
        if payout.get("max_per_payout", 0) <= 0:
            warnings.append("payout_rules.max_per_payout should be positive")
        if not (0 < payout.get("commission_rate", 0.10) < 1):
            warnings.append("payout_rules.commission_rate should be between 0 and 1")

    # V3: scaling_plan
    if tsm.get("scaling_plan_active") and not tsm.get("scaling_plan"):
        warnings.append("scaling_plan_active=true but no scaling_plan defined")

    return {"valid": len(errors) == 0, "errors": errors, "warnings": warnings}


# ---------------------------------------------------------------------------
# Load TSM files
# ---------------------------------------------------------------------------


def load_all_tsm_files() -> list[dict]:
    """Load and validate all TSM JSON files from the config directory.

    Returns
    -------
    list[dict]
        List of ``{filename, tsm, validation}`` dicts.
    """
    results = []
    if not os.path.isdir(TSM_CONFIG_DIR):
        logger.warning("TSM config directory not found: %s", TSM_CONFIG_DIR)
        return results

    for filename in sorted(os.listdir(TSM_CONFIG_DIR)):
        if not filename.endswith(".json"):
            continue
        filepath = os.path.join(TSM_CONFIG_DIR, filename)
        try:
            with open(filepath) as f:
                tsm = json.load(f)
            validation = validate_tsm(tsm)
            results.append({
                "filename": filename,
                "tsm": tsm,
                "validation": validation,
            })
            if not validation["valid"]:
                logger.warning("TSM %s has errors: %s", filename, validation["errors"])
        except json.JSONDecodeError as exc:
            logger.error("Invalid JSON in TSM file %s: %s", filename, exc)
            results.append({
                "filename": filename,
                "tsm": None,
                "validation": {"valid": False, "errors": [f"Invalid JSON: {exc}"], "warnings": []},
            })
        except Exception as exc:
            logger.error("Failed to load TSM file %s: %s", filename, exc, exc_info=True)

    return results


def load_tsm_for_account(account_id: str, tsm_filename: str) -> dict | None:
    """Load a specific TSM file and store it in P3-D08 for an account.

    Parameters
    ----------
    account_id : str
        The account to assign this TSM to.
    tsm_filename : str
        Filename within TSM_CONFIG_DIR.

    Returns
    -------
    dict or None
        The loaded TSM dict, or None on failure.
    """
    filepath = os.path.join(TSM_CONFIG_DIR, tsm_filename)
    if not os.path.exists(filepath):
        logger.error("TSM file not found: %s", filepath)
        return None

    try:
        with open(filepath) as f:
            tsm = json.load(f)
    except Exception as exc:
        logger.error("Failed to parse TSM %s: %s", tsm_filename, exc)
        return None

    validation = validate_tsm(tsm)
    if not validation["valid"]:
        logger.error("TSM %s validation failed: %s", tsm_filename, validation["errors"])
        return None

    # Store in P3-D08
    _store_tsm_in_d08(account_id, tsm)

    write_checkpoint("COMMAND", "TSM_LOADED", "loaded", "ready",
                     {"account_id": account_id, "tsm_name": tsm.get("name")})

    return tsm


# ---------------------------------------------------------------------------
# Parameter translation
# ---------------------------------------------------------------------------


def translate_for_tsm(signal_contracts: int, trade_risk: float,
                      tsm: dict) -> dict:
    """Apply TSM constraints to a proposed trade.

    Parameters
    ----------
    signal_contracts : int
        Proposed contract count from Kelly sizing.
    trade_risk : float
        Estimated risk in $ for this trade.
    tsm : dict
        Full TSM dict from P3-D08.

    Returns
    -------
    dict
        ``{contracts: int, suppressed: bool, reason: str | None}``
    """
    max_contracts = tsm.get("max_contracts", signal_contracts)

    # Cap at TSM maximum
    final_contracts = min(signal_contracts, max_contracts)

    # Daily loss budget check
    mll = tsm.get("max_daily_loss")
    daily_used = tsm.get("daily_loss_used", 0)
    if mll is not None and mll > 0:
        remaining_budget = mll - daily_used
        if trade_risk > remaining_budget:
            # Reduce contracts proportionally
            if trade_risk > 0 and signal_contracts > 0:
                risk_per_contract = trade_risk / signal_contracts
                affordable = int(remaining_budget / risk_per_contract) if risk_per_contract > 0 else 0
                final_contracts = min(final_contracts, affordable)

    if final_contracts < 1:
        return {
            "contracts": 0,
            "suppressed": True,
            "reason": "Insufficient daily risk budget",
        }

    return {
        "contracts": final_contracts,
        "suppressed": False,
        "reason": None,
    }


def get_fee_for_instrument(tsm: dict, instrument: str) -> float:
    """Get the round-turn fee for an instrument from a TSM.

    V3: Uses fee_schedule.fees_by_instrument if available,
    falls back to commission_per_contract × 2.

    Parameters
    ----------
    tsm : dict
        Full TSM dict.
    instrument : str
        Instrument symbol (e.g. "ES", "MES").

    Returns
    -------
    float
        Round-turn fee per contract.
    """
    fee_sched = tsm.get("fee_schedule", {})
    fees_by_inst = fee_sched.get("fees_by_instrument", {})
    if instrument in fees_by_inst:
        return fees_by_inst[instrument].get("round_turn", 0)

    # Fallback to legacy field
    cpc = tsm.get("commission_per_contract", 0)
    return cpc * 2  # round-turn


def get_scaling_tier(tsm: dict, current_profit: float) -> dict:
    """Look up the current scaling tier based on profit.

    Parameters
    ----------
    tsm : dict
        Full TSM dict with ``scaling_plan``.
    current_profit : float
        Current profit above starting balance.

    Returns
    -------
    dict
        ``{tier_label, max_contracts, max_micros, profit_to_next_tier,
          next_tier_label}``
    """
    plan = tsm.get("scaling_plan", [])
    if not plan:
        return {
            "tier_label": "No scaling plan",
            "max_contracts": tsm.get("max_contracts", 0),
            "max_micros": 0,
            "profit_to_next_tier": 0,
            "next_tier_label": "",
        }

    # Sort by balance_threshold ascending
    sorted_plan = sorted(plan, key=lambda t: t.get("balance_threshold", 0))

    starting = tsm.get("starting_balance", 0)
    current_balance = starting + current_profit
    current_tier = None
    next_tier = None

    for i, tier in enumerate(sorted_plan):
        threshold = tier.get("balance_threshold", 0)
        if current_balance >= threshold:
            current_tier = tier
            next_tier = sorted_plan[i + 1] if i + 1 < len(sorted_plan) else None
        else:
            if current_tier is None:
                current_tier = tier
            if next_tier is None:
                next_tier = tier
            break

    if current_tier is None:
        current_tier = sorted_plan[0] if sorted_plan else {}

    max_c = current_tier.get("max_contracts", tsm.get("max_contracts", 0))
    max_micros = current_tier.get("max_micros", max_c * 10)
    tier_label = current_tier.get("label", f"{max_micros}μ ({max_c} minis)")

    profit_to_next = 0
    next_label = ""
    if next_tier and next_tier != current_tier:
        next_threshold = next_tier.get("balance_threshold", 0)
        profit_to_next = max(next_threshold - current_balance, 0)
        next_max_c = next_tier.get("max_contracts", 0)
        next_micros = next_tier.get("max_micros", next_max_c * 10)
        next_label = next_tier.get("label", f"{next_micros}μ ({next_max_c} minis) at ${next_threshold:,.0f}+")

    return {
        "tier_label": tier_label,
        "max_contracts": max_c,
        "max_micros": max_micros,
        "profit_to_next_tier": round(profit_to_next, 2),
        "next_tier_label": next_label,
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _store_tsm_in_d08(account_id: str, tsm: dict, retries: int = 3):
    """Upsert TSM data into P3-D08."""
    import time

    classification = tsm.get("classification", {})
    topstep_opt = tsm.get("topstep_optimisation", False)
    topstep_state = json.dumps({
        "topstep_params": tsm.get("topstep_params", {}),
        "payout_rules": tsm.get("payout_rules", {}),
        "fee_schedule": tsm.get("fee_schedule", {}),
        "scaling_plan": tsm.get("scaling_plan", []),
    })

    params = (
        account_id,
        tsm.get("user_id", ""),
        tsm.get("name", ""),
        json.dumps(classification),
        tsm.get("starting_balance", 0),
        tsm.get("current_balance", tsm.get("starting_balance", 0)),
        tsm.get("max_drawdown_limit", 0),
        tsm.get("max_daily_loss"),
        0,  # daily_loss_used starts at 0
        tsm.get("profit_target"),
        tsm.get("max_contracts", 0),
        tsm.get("commission_per_contract", 0),
        tsm.get("overnight_allowed", False),
        json.dumps(tsm.get("trading_hours", "")) if isinstance(tsm.get("trading_hours"), dict) else tsm.get("trading_hours", ""),
        classification.get("risk_goal", ""),
        topstep_opt,
        tsm.get("scaling_plan_active", False),
        topstep_state,
        json.dumps(tsm.get("fee_schedule", {})),
        json.dumps(tsm.get("payout_rules", {})),
        datetime.now().isoformat(),
    )

    sql = """INSERT INTO p3_d08_tsm_state(
                 account_id, user_id, name, classification,
                 starting_balance, current_balance,
                 max_drawdown_limit, max_daily_loss,
                 daily_loss_used, profit_target, max_contracts,
                 commission_per_contract, overnight_allowed,
                 trading_hours, risk_goal,
                 topstep_optimisation, scaling_plan_active,
                 topstep_state, fee_schedule, payout_rules,
                 last_updated
             ) VALUES(
                 %s, %s, %s, %s,
                 %s, %s,
                 %s, %s,
                 %s, %s, %s,
                 %s, %s,
                 %s, %s,
                 %s, %s,
                 %s, %s, %s,
                 %s
             )"""

    for attempt in range(retries):
        try:
            with get_cursor() as cur:
                cur.execute(sql, params)
            logger.info("TSM stored in D08: account=%s tsm=%s", account_id, tsm.get("name"))
            return True
        except Exception as exc:
            if "table busy" in str(exc) and attempt < retries - 1:
                logger.warning("D08 table busy, retrying in %ds... (%d/%d)",
                               attempt + 1, attempt + 1, retries)
                time.sleep(attempt + 1)
            else:
                logger.error("Failed to store TSM in D08: %s", exc, exc_info=True)
                return False
    return False
