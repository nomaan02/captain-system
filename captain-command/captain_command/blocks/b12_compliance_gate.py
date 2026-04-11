# region imports
try:
    from AlgorithmImports import *
except ImportError:
    pass
# endregion
"""B12 Compliance Gate — RTS 6 requirement enforcement.

Reads config/compliance_gate.json and validates all 11 RTS 6 requirements.
Used by B3 (API adapter) before order placement and B2 (GUI data server)
for dashboard visibility.

Gate behaviour:
  - All 11 rts6_* flags must be ``True`` for automated execution.
  - If any flag is ``False`` or missing, execution_mode is ``MANUAL``.
  - V1: gate is intentionally locked (MANUAL) until all requirements are
    validated for production automated trading.
"""

import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

COMPLIANCE_GATE_PATH = os.environ.get(
    "COMPLIANCE_GATE_PATH", "/captain/config/compliance_gate.json"
)

_EXPECTED_REQUIREMENTS = 11
_RTS6_PREFIX = "rts6_"

# ---------------------------------------------------------------------------
# Gate loading
# ---------------------------------------------------------------------------

_SEARCH_PATHS = [
    Path(__file__).resolve().parent.parent.parent.parent / "config" / "compliance_gate.json",
]


def _load_gate_config() -> dict:
    """Load compliance_gate.json from env path or fallback search paths."""
    paths = [Path(COMPLIANCE_GATE_PATH)] + _SEARCH_PATHS
    for p in paths:
        if p.exists():
            try:
                with open(p, encoding="utf-8") as f:
                    return json.load(f)
            except Exception as exc:
                logger.error("Failed to read compliance gate at %s: %s", p, exc)
    logger.warning("compliance_gate.json not found — defaulting to LOCKED")
    return {}


# ---------------------------------------------------------------------------
# Enforcement
# ---------------------------------------------------------------------------

def check_compliance_gate() -> dict:
    """Check if automated execution is permitted.

    Reads the flat ``rts6_*`` boolean flags from compliance_gate.json.
    All 11 must be ``True`` for ``allowed=True``.

    Returns
    -------
    dict
        ``{allowed, execution_mode, unsatisfied, total_requirements}``
    """
    gate = _load_gate_config()

    # Extract rts6_* requirement flags (ignore _comment and other keys)
    requirements = {
        k: v for k, v in gate.items()
        if k.startswith(_RTS6_PREFIX) and isinstance(v, bool)
    }

    unsatisfied = [
        req_id for req_id, status in requirements.items()
        if not status
    ]

    all_met = len(unsatisfied) == 0 and len(requirements) == _EXPECTED_REQUIREMENTS
    auto_execute = os.environ.get("AUTO_EXECUTE", "false").lower() == "true"

    return {
        "allowed": all_met and auto_execute,
        "execution_mode": "AUTO" if (all_met and auto_execute) else "MANUAL",
        "unsatisfied": unsatisfied,
        "total_requirements": len(requirements),
    }


def get_gate_status() -> dict:
    """Return full gate config for GUI display (all flags + computed status)."""
    gate = _load_gate_config()
    result = check_compliance_gate()
    return {
        **gate,
        "_enforcement": result,
    }


# ---------------------------------------------------------------------------
# Per-signal compliance (PG-32 spec)
# ---------------------------------------------------------------------------


def _get_active_assets() -> set[str]:
    """Load active asset IDs from D00."""
    try:
        from shared.questdb_client import get_cursor
        with get_cursor() as cur:
            cur.execute(
                "SELECT asset_id FROM p3_d00_asset_universe "
                "WHERE captain_status = 'ACTIVE'"
            )
            return {row[0] for row in cur.fetchall()}
    except Exception as exc:
        logger.error("Failed to load active assets from D00: %s", exc)
    return set()


def _get_account_tsm(account_id: str) -> dict | None:
    """Load TSM config for an account from D08."""
    try:
        from shared.questdb_client import get_cursor
        with get_cursor() as cur:
            cur.execute(
                "SELECT max_contracts, fee_schedule "
                "FROM p3_d08_tsm_state "
                "WHERE account_id = %s "
                "ORDER BY ts DESC LIMIT 1",
                (account_id,),
            )
            row = cur.fetchone()
            if row:
                fee_schedule = {}
                if row[1]:
                    try:
                        fee_schedule = json.loads(row[1]) if isinstance(row[1], str) else row[1]
                    except (json.JSONDecodeError, TypeError):
                        fee_schedule = {}
                return {
                    "max_contracts": row[0],
                    "fee_schedule": fee_schedule,
                }
    except Exception as exc:
        logger.error("Failed to load TSM for account %s: %s", account_id, exc)
    return None


def instrument_permitted(asset: str, account_tsm: dict) -> bool:
    """Check if an instrument is permitted for the account.

    An instrument is permitted if it is in the D00 active universe.
    If the TSM has ``fee_schedule.fees_by_instrument`` entries,
    the asset must also be listed there.
    """
    active_assets = _get_active_assets()
    if active_assets and asset not in active_assets:
        return False

    fee_sched = account_tsm.get("fee_schedule", {})
    if isinstance(fee_sched, str):
        try:
            fee_sched = json.loads(fee_sched)
        except (json.JSONDecodeError, TypeError):
            fee_sched = {}
    fees_by_inst = fee_sched.get("fees_by_instrument", {})
    if fees_by_inst and asset not in fees_by_inst:
        return False

    return True


def compliance_check(signal: dict, account_id: str) -> dict:
    """Per-signal compliance check per spec PG-32.

    Verifies:
    1. ``signal.contracts <= max_contracts``
    2. ``instrument_permitted(signal.asset)``

    Parameters
    ----------
    signal : dict
        Signal/order dict with ``asset`` and ``size`` (contracts) fields.
    account_id : str
        Account ID to look up TSM constraints from D08.

    Returns
    -------
    dict
        ``{approved: bool, reason?: str}``
    """
    tsm = _get_account_tsm(account_id)
    if tsm is None:
        logger.warning("No TSM found for account %s — compliance check skipped", account_id)
        return {"approved": True}

    contracts = int(signal.get("size", signal.get("contracts", 0)))
    max_contracts = tsm.get("max_contracts") or 0

    if max_contracts > 0 and contracts > max_contracts:
        return {"approved": False, "reason": "EXCEEDS_MAX_CONTRACTS"}

    asset = signal.get("asset", "")
    if not instrument_permitted(asset, tsm):
        return {"approved": False, "reason": "INSTRUMENT_NOT_PERMITTED"}

    return {"approved": True}
