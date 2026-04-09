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
