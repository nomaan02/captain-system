"""shared/nkd_jitter.py — Per-trade Isaac-tower jitter sampler.

Lifecycle
---------
1. B6 (``b6_signal_output.py``) calls ``sample_isaac_jitter`` ONCE per NKD
   signal on Isaac tower (INSTANCE_PARITY == "1"). J is included in the
   signal payload and used immediately to jitter the TP bracket price via
   ``_tp_from_dollars(4450 + J, ...)``.
2. J is threaded through the signal → TAKEN message → position dict so
   ``b7b_nkd_trail._scan_one_trail`` can read it from the position dict on
   every poll without re-sampling.
3. Defence-in-depth: if the trail block encounters a position where
   ``jitter_j`` is None (e.g. replay tests that bypass B6), it samples
   fresh using this same function.

J only modifies dollar amounts sent to the broker. Phase boundaries
($2000 / $3000 / $4450) are clean and never jittered.
"""
import os
import random
from decimal import Decimal
from typing import Optional

_JITTER_X_MIN = 0.01
_JITTER_X_MAX = 1.00
_JITTER_SCALE = Decimal("20")  # |J| ∈ [0.2, 20.0]


def sample_isaac_jitter(
    parity_env: Optional[str],
) -> tuple[Decimal, int, Decimal]:
    """Sample once-per-trade jitter parameters.

    Nomaan tower (INSTANCE_PARITY != "1"): returns (0, 0, 0).
    Isaac tower  (INSTANCE_PARITY == "1"): X ~ U(0.01, 1.00),
                                           Y ~ choice({-1, +1}),
                                           J = 20 * X * Y.
    """
    if parity_env != "1":
        return (Decimal("0"), 0, Decimal("0"))
    x_float = random.uniform(_JITTER_X_MIN, _JITTER_X_MAX)
    x = Decimal(str(round(x_float, 8)))
    y = random.choice([-1, 1])
    j = _JITTER_SCALE * x * Decimal(y)
    return (x, y, j)
