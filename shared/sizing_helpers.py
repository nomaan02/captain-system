"""Sizing helpers — single source of truth for SL distance resolution.

Phase 2 (F-04): B4 (Kelly sizing) and B5C (circuit breaker) must agree on the
SL distance used to compute `risk_per_contract` and `rho_j`. Per spec:

    risk_per_contract = strategy_sl × point_value
    rho_j             = contracts × (strategy_sl × point_value + phi)

Source of truth for `strategy_sl`:

    1. Primary  — `sl_multiple × historical_avg_or_range` from P3-D29
                  (`or_range_first_m_min` 20-day average, populated by
                  `b1_features.store_opening_volume(or_range=...)`).
                  Resolves Isaac Q1 (option b, 2026-04-22): B4 sizes against
                  an *expected* SL distance derived from historical OR ranges,
                  while B6 keeps live `sl_multiple × or_range`. The two
                  converge as more sessions populate the historical average.

    2. Fallback — `strategy.threshold` (legacy static seed in
                  `bootstrap_production.py`).

    3. Default  — `4.0` points (preserves prior behaviour for cold-start).

Pattern mirrors `shared/aim_compute.py` and `shared/statistics.py` — extracted
so captain-online (B4, B5C, orchestrator) AND scripts/replay_session.py can
share one resolution path. See `docs2/audits/2026-04-22_amendment_plan.md`
Phase 2 for the full design.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

DEFAULT_SL_POINTS = 4.0
DEFAULT_SL_MULTIPLE = 0.10
DEFAULT_OR_MINUTES = 15

# Per-process WARN dedup so cold-start fallback log fires at most once per
# (asset, source) combination. Reset is process-scoped (intentional).
_warned_assets: set[tuple[str, str]] = set()


def _warn_once(asset_id: str, source: str, message: str) -> None:
    key = (asset_id, source)
    if key in _warned_assets:
        return
    _warned_assets.add(key)
    logger.warning(message)


def resolve_sizing_sl(
    asset_id: str,
    strategy: dict,
    point_value: float,
    or_minutes: Optional[int] = None,
    *,
    historical_or_range_fn=None,
) -> float:
    """Resolve the SL distance (in points) to size against for this asset.

    Args:
        asset_id: Asset symbol (e.g. "MNQ", "ES").
        strategy: Locked strategy dict (`locked_strategies[asset]`). Reads
            `sl_multiple` and `threshold` keys.
        point_value: Dollar value per point (used for diagnostic log only —
            kept in the signature for symmetry with caller usage and possible
            future enrichment).
        or_minutes: OR window in minutes. If None, falls back to the strategy's
            `OR_window_minutes` (via `get_or_window_minutes`) or the module
            default (15). Determines which D29 rows to average.
        historical_or_range_fn: Injectable callable matching
            `_get_historical_or_range(asset_id, minutes, lookback)`. Defaults
            to the live import from `captain_online.blocks.b1_features`. The
            indirection lets tests inject a stub without touching QuestDB.

    Returns:
        SL distance in points (float, > 0).

    Behaviour:
        - Path 1 (primary):  sl_multiple × historical_avg_or_range
        - Path 2 (fallback): strategy.threshold
        - Path 3 (default):  DEFAULT_SL_POINTS (4.0)
        Fires a one-shot WARN per (asset, path) when paths 2/3 trigger.
    """
    sl_multiple = float(strategy.get("sl_multiple") or DEFAULT_SL_MULTIPLE)

    if or_minutes is None:
        try:
            from captain_online.blocks.b1_features import get_or_window_minutes
            or_minutes = get_or_window_minutes(strategy)
        except Exception:
            or_minutes = DEFAULT_OR_MINUTES

    if historical_or_range_fn is None:
        try:
            from captain_online.blocks.b1_features import _get_historical_or_range
            historical_or_range_fn = _get_historical_or_range
        except Exception:
            historical_or_range_fn = None

    # Path 1: historical OR range × sl_multiple
    hist_avg = None
    if historical_or_range_fn is not None:
        try:
            hist_avg = historical_or_range_fn(asset_id, int(or_minutes), 20)
        except Exception as e:
            logger.debug("resolve_sizing_sl: historical lookup failed for %s: %s",
                         asset_id, e)

    if hist_avg is not None and hist_avg > 0:
        sl = sl_multiple * float(hist_avg)
        if sl > 0:
            return sl

    # Path 2: legacy `threshold` static seed
    threshold = strategy.get("threshold")
    if threshold is not None:
        try:
            sl_t = float(threshold)
            if sl_t > 0:
                _warn_once(asset_id, "threshold",
                    f"resolve_sizing_sl: {asset_id} falling back to "
                    f"strategy.threshold={sl_t} (D29 historical OR range "
                    f"unavailable). pv={point_value}.")
                return sl_t
        except (TypeError, ValueError):
            pass

    # Path 3: hard default
    _warn_once(asset_id, "default",
        f"resolve_sizing_sl: {asset_id} using DEFAULT_SL_POINTS="
        f"{DEFAULT_SL_POINTS} (no D29 history, no strategy.threshold). "
        f"pv={point_value}.")
    return DEFAULT_SL_POINTS


def reset_warning_cache() -> None:
    """Test helper: clear the per-(asset, path) WARN dedup cache."""
    _warned_assets.clear()
