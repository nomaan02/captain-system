# region imports
try:
    from AlgorithmImports import *
except ImportError:
    pass
# endregion
"""ON-B3: AIM Aggregation (MoE/DMA) — P3-PG-23 (Task 3.3 / ON lines 660-706).

Delegates to shared.aim_compute for the actual computation logic.
This module re-exports for backward compatibility with existing imports.

See shared/aim_compute.py for the full implementation and docstrings.
"""

from shared.aim_compute import (  # noqa: F401
    MODIFIER_FLOOR,
    MODIFIER_CEILING,
    run_aim_aggregation,
    compute_aim_modifier,
)

__all__ = [
    "MODIFIER_FLOOR",
    "MODIFIER_CEILING",
    "run_aim_aggregation",
    "compute_aim_modifier",
]
