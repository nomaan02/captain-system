# region imports
try:
    from AlgorithmImports import *
except ImportError:
    pass
# endregion
"""Captain Command — Block 10: Data Input Validation (P3-PG-41, P3-PG-42).

Validates all user-provided data inputs before they enter the system.
Catches typos, unit errors, and suspicious values.  Part of the Data
Moderator system.

Spec: Program3_Command.md lines 781-877
"""

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Validation thresholds
# ---------------------------------------------------------------------------

PRICE_DEVIATION_THRESHOLD = 0.02       # 2%
COMMISSION_MULTIPLIER_THRESHOLD = 10   # 10× expected
BALANCE_DEVIATION_THRESHOLD = 0.05     # 5%

# Required fields for asset onboarding
ASSET_REQUIRED_FIELDS = [
    "asset_id",
    "exchange_timezone",
    "point_value",
    "tick_size",
    "margin_per_contract",
    "session_hours",
    "roll_calendar",
    "p1_data_path",
    "p2_data_path",
    "data_sources",
]

# Valid data source adapter types
VALID_ADAPTERS = {"REST", "FILE", "WEBSOCKET", "BROKER_API"}

# Valid session_hours format: "HH:MM-HH:MM TZ"
import re
_SESSION_HOURS_RE = re.compile(
    r"^\d{2}:\d{2}-\d{2}:\d{2}\s+[\w/]+$"
)


# ---------------------------------------------------------------------------
# P3-PG-41: User Input Validation
# ---------------------------------------------------------------------------


def validate_user_input(input_type: str, value: Any, context: dict) -> dict:
    """Validate a single user-provided input value.

    Parameters
    ----------
    input_type : str
        One of ``ACTUAL_ENTRY_PRICE``, ``ACTUAL_COMMISSION``,
        ``ACCOUNT_BALANCE``.
    value : float
        The value provided by the user.
    context : dict
        Contextual data needed for comparison:
        - ``signal_entry_price`` (for price validation)
        - ``tsm_commission_per_contract`` + ``contracts`` (for commission)
        - ``last_known_balance`` (for balance validation)

    Returns
    -------
    dict
        ``{valid, flag?, message?, requires_confirmation?}``
    """
    if input_type == "ACTUAL_ENTRY_PRICE":
        signal_price = context.get("signal_entry_price")
        if signal_price and signal_price != 0:
            deviation_pct = abs(value - signal_price) / abs(signal_price)
            if deviation_pct > PRICE_DEVIATION_THRESHOLD:
                return {
                    "valid": False,
                    "flag": "PRICE_DEVIATION",
                    "message": (
                        f"Entry price {value} deviates {deviation_pct * 100:.1f}% "
                        f"from signal price {signal_price}. Confirm?"
                    ),
                    "requires_confirmation": True,
                }

    elif input_type == "ACTUAL_COMMISSION":
        commission_per = context.get("tsm_commission_per_contract", 0)
        contracts = context.get("contracts", 1)
        tsm_default = commission_per * contracts * 2  # round-turn
        if tsm_default > 0 and value > tsm_default * COMMISSION_MULTIPLIER_THRESHOLD:
            return {
                "valid": False,
                "flag": "COMMISSION_SUSPICIOUS",
                "message": (
                    f"Commission {value} is {value / tsm_default:.0f}x the "
                    f"expected {tsm_default}. Confirm?"
                ),
                "requires_confirmation": True,
            }

    elif input_type == "ACCOUNT_BALANCE":
        last_known = context.get("last_known_balance")
        if last_known and last_known != 0:
            deviation_pct = abs(value - last_known) / abs(last_known)
            if deviation_pct > BALANCE_DEVIATION_THRESHOLD:
                return {
                    "valid": False,
                    "flag": "BALANCE_DEVIATION",
                    "message": (
                        f"Balance {value} differs {deviation_pct * 100:.1f}% "
                        f"from last known {last_known}. Confirm?"
                    ),
                    "requires_confirmation": True,
                }

    else:
        logger.warning("Unknown input_type for validation: %s", input_type)

    return {"valid": True}


# ---------------------------------------------------------------------------
# P3-PG-42: Asset Configuration Validation
# ---------------------------------------------------------------------------


def validate_asset_config(asset_config: dict) -> dict:
    """Validate an asset configuration for onboarding.

    Parameters
    ----------
    asset_config : dict
        Full asset configuration dict containing required fields,
        data sources, roll calendar, session hours, etc.

    Returns
    -------
    dict
        ``{valid: bool, errors: list[str], warnings: list[str]}``
    """
    errors: list[str] = []
    warnings: list[str] = []

    # --- Required fields ---
    for field in ASSET_REQUIRED_FIELDS:
        if field not in asset_config or asset_config[field] is None:
            errors.append(f"Missing required field: {field}")

    if errors:
        return {"valid": False, "errors": errors, "warnings": warnings}

    # --- P1/P2 output data existence ---
    p1_path = asset_config.get("p1_data_path", "")
    if p1_path and not os.path.exists(p1_path):
        errors.append(f"P1 output path not found: {p1_path}")

    p2_path = asset_config.get("p2_data_path", "")
    if p2_path and not os.path.exists(p2_path):
        errors.append(f"P2 output path not found: {p2_path}")

    # --- Data source connectivity ---
    data_sources = asset_config.get("data_sources", {})
    for source_name, source_config in data_sources.items():
        adapter = source_config.get("adapter", "")
        endpoint = source_config.get("endpoint", "")

        if adapter not in VALID_ADAPTERS:
            errors.append(f"{source_name}: Unknown adapter type '{adapter}'")
            continue

        if adapter == "FILE":
            if not endpoint:
                errors.append(f"{source_name}: FILE adapter missing endpoint path")
            elif not os.path.exists(endpoint):
                errors.append(f"{source_name}: FILE not found at {endpoint}")
            elif os.path.getsize(endpoint) == 0:
                warnings.append(f"{source_name}: FILE exists but is empty")

        elif adapter == "REST":
            if not endpoint:
                errors.append(f"{source_name}: REST adapter missing endpoint URL")
            else:
                # Connectivity tested at runtime — just validate URL shape
                if not endpoint.startswith(("http://", "https://")):
                    errors.append(f"{source_name}: REST endpoint not a valid URL: {endpoint}")

        elif adapter == "WEBSOCKET":
            if not endpoint:
                errors.append(f"{source_name}: WEBSOCKET adapter missing endpoint URL")
            else:
                if not endpoint.startswith(("ws://", "wss://")):
                    errors.append(f"{source_name}: WEBSOCKET endpoint not a valid URL: {endpoint}")

        elif adapter == "BROKER_API":
            if not endpoint:
                errors.append(f"{source_name}: BROKER_API adapter missing endpoint")

    # --- Roll calendar validation ---
    roll_cal = asset_config.get("roll_calendar", {})
    if isinstance(roll_cal, dict):
        if not roll_cal.get("current_contract"):
            warnings.append(
                "roll_calendar.current_contract not set — "
                "will need manual entry before first session"
            )
    else:
        errors.append("roll_calendar must be a dict")

    # --- Session hours format ---
    session_hours = asset_config.get("session_hours", "")
    if session_hours and not _SESSION_HOURS_RE.match(session_hours):
        errors.append(
            f"Invalid session_hours format: '{session_hours}'. "
            f"Expected 'HH:MM-HH:MM Timezone'"
        )

    # --- Numeric sanity checks ---
    point_value = asset_config.get("point_value")
    if point_value is not None and point_value <= 0:
        errors.append(f"point_value must be positive, got {point_value}")

    tick_size = asset_config.get("tick_size")
    if tick_size is not None and tick_size <= 0:
        errors.append(f"tick_size must be positive, got {tick_size}")

    margin = asset_config.get("margin_per_contract")
    if margin is not None and margin <= 0:
        errors.append(f"margin_per_contract must be positive, got {margin}")

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
    }
