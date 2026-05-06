# region imports
try:
    from AlgorithmImports import *
except ImportError:
    pass
# endregion
"""System Health Diagnostic — P3-PG-16B (Tasks 2.9a, 2.9b / OFF lines 717-1021).

8-dimension table in spec; **7 scored in v1** (D7 deferred per Q-21) diagnostic with QUEUE_ACTION helper for human action items.

Dimensions:
  D1: Strategy Portfolio Health (diversity, freshness, OO scores)
  D2: Feature Portfolio Health (distinct features, reuse, decay flags)
  D3: Model Staleness (per-asset P1/P2 age from p3_d22b.last_p1p2_rerun_ts — Q-19)
  D4: AIM Effectiveness (rolling monthly modifier-vs-PnL hit rate — Q-20)
  D5: Edge Trajectory (30/60/90d edge, trend, regime breakdown) — MONTHLY only
  D6: Data Coverage Gaps (AIM missing rates, asset holds)
  D7: deferred (Q-21 v1 — not scored)
  D8: Resolution Verification (resolved items verified, stale detection)

Rolling monthly window for D4: MONTHLY_HIT_WINDOW_DAYS (default 31 calendar days).

Schedule: WEEKLY (D1-D4, D6, D8 — no D5, no D7), MONTHLY (D1-D6 + D8 + D5)

Reads: P2-D06, P2-D07, P3-D00..D06, D13, D17, D22
Writes: P3-D22
"""

import json
import logging
from collections import Counter
from datetime import datetime, timedelta
from decimal import Decimal

from shared.constants import now_et
from shared.decimal_boundary import to_float
from shared.decimal_json import loads_decimal
from shared.questdb_client import get_cursor, qexecute

logger = logging.getLogger(__name__)

MAX_ACTION_QUEUE_SIZE = 1000

# Thresholds from Arch §9
STALENESS_MEDIUM_DAYS = 90
STALENESS_HIGH_DAYS = 180
OO_WEAKNESS_THRESHOLD = 0.55
EDGE_DECLINE_THRESHOLD = 0.15
ACTION_STALE_DAYS = 90
MONTHLY_HIT_WINDOW_DAYS = 31

# Q-34 / plan B4: equal weights 1/N over active dimensions (no D7 in v1).
OVERALL_HEALTH_KEYS_WEEKLY = (
    "strategy_portfolio",
    "feature_portfolio",
    "model_staleness",
    "aim_effectiveness",
    "data_coverage",
    "resolution_health",
)
OVERALL_HEALTH_KEYS_MONTHLY = (
    "strategy_portfolio",
    "feature_portfolio",
    "model_staleness",
    "aim_effectiveness",
    "edge_trajectory",
    "data_coverage",
    "resolution_health",
)


def _weighted_mean(items: list[tuple[float, float]]) -> float:
    """Compute weighted mean from list of (value, weight) tuples."""
    total_weight = sum(w for _, w in items)
    if total_weight <= 0:
        return 0.0
    return sum(v * w for v, w in items) / total_weight


def _safe_days_since(ts) -> int:
    """Compute days between now and a timestamp, handling None and type mismatches."""
    if ts is None:
        return 999
    try:
        if isinstance(ts, str):
            ts = datetime.fromisoformat(ts)
        delta = now_et() - ts
        return max(getattr(delta, "days", 0), 0)
    except (ValueError, TypeError):
        return 999


def _compute_edge(win_rate: float, avg_win: float, avg_loss: float) -> float:
    """Expected edge per trade = p*W - (1-p)*L."""
    wr = win_rate or 0.5
    aw = avg_win or 0.01
    al = avg_loss or 0.01
    return wr * aw - (1 - wr) * al


def _active_asset_p1p2_stale_days() -> dict[str, int]:
    """Days since last_p1p2_rerun_ts per active asset from p3_d22b (Q-19).

    Missing D22b row or NULL timestamp → 999 days (conservative; do not use
    global injection history as a proxy).
    """
    with get_cursor() as cur:
        cur.execute(
            "SELECT asset_id FROM p3_d00_asset_universe WHERE captain_status = 'ACTIVE'"
        )
        asset_ids = [r[0] for r in cur.fetchall()]
    if not asset_ids:
        return {}
    with get_cursor() as cur:
        cur.execute(
            "SELECT asset, last_p1p2_rerun_ts FROM p3_d22b_asset_rerun_status "
            "LATEST ON last_updated PARTITION BY asset"
        )
        rerun_rows = cur.fetchall()
    rerun_ts_by_asset = {row[0]: row[1] for row in (rerun_rows or [])}
    out: dict[str, int] = {}
    for aid in asset_ids:
        ts = rerun_ts_by_asset.get(aid)
        out[aid] = _safe_days_since(ts)
    return out


def _modifier_pnl_hit(modifier: float, pnl: float) -> bool | None:
    """Q-20: modifier tilt vs realised PnL sign (None = neutral modifier, skip)."""
    if abs(modifier - 1.0) < 1e-9:
        return None
    if modifier > 1.0:
        return pnl > 0
    return pnl < 0


def _queue_action(action_queue: list, priority: str, category: str,
                   dimension: str, constraint_type: str, title: str,
                   detail: str, recommendation: str,
                   metric_snapshot: dict | None = None):
    """QUEUE_ACTION helper: add or update action item with deduplication."""
    # Deduplication: don't create duplicate if same constraint_type is open
    for item in action_queue:
        if (item["constraint_type"] == constraint_type
                and item["status"] in ("OPEN", "ACKNOWLEDGED", "IN_PROGRESS")):
            item["last_seen"] = now_et().isoformat()
            item["detail"] = detail
            return

    action_queue.append({
        "action_id": f"ACT-{now_et().strftime('%Y-%m-%d')}-{len(action_queue)+1:03d}",
        "created": now_et().isoformat(),
        "priority": priority,
        "category": category,
        "dimension": dimension,
        "constraint_type": constraint_type,
        "title": title,
        "detail": detail,
        "impact_estimate": "",
        "recommendation": recommendation,
        "status": "OPEN",
        "acknowledged_by": None,
        "acknowledged_at": None,
        "resolved_at": None,
        "verified_at": None,
        "verification_result": None,
        "notes": "",
        "metric_snapshot_at_creation": metric_snapshot or {},
        "last_seen": now_et().isoformat(),
    })


# ════════════════════════════════════════════════════════════════════════
# D1: STRATEGY PORTFOLIO HEALTH
# ════════════════════════════════════════════════════════════════════════

def compute_d1(action_queue: list) -> float:
    """D1: Strategy Portfolio Health — diversity, freshness, OO scores."""
    with get_cursor() as cur:
        cur.execute(
            "SELECT locked_strategy, last_updated FROM p3_d00_asset_universe "
            "WHERE captain_status = 'ACTIVE'"
        )
        rows = cur.fetchall()

    if not rows:
        return 0.0

    strategy_models = {}
    strategy_ages = {}
    oo_scores = {}
    n_assets = len(rows)

    for r in rows:
        s = json.loads(r[0]) if r[0] else {}
        asset_id = s.get("asset", f"asset_{len(strategy_models)}")
        strategy_models[asset_id] = (s.get("model", 0), s.get("feature", 0))
        # Age: days since locked_strategy timestamp or last_updated
        strategy_ts = s.get("timestamp") or s.get("locked_at")
        if strategy_ts:
            strategy_ages[asset_id] = _safe_days_since(strategy_ts)
        else:
            strategy_ages[asset_id] = _safe_days_since(r[1])
        oo_scores[asset_id] = s.get("oo_score", s.get("OO", 0.5))

    type_count = len(set(strategy_models.values()))
    age_max = max(strategy_ages.values()) if strategy_ages else 0
    age_mean = (sum(strategy_ages.values()) / len(strategy_ages)) if strategy_ages else 0
    oo_min = min(oo_scores.values()) if oo_scores else 0.0
    oo_spread = (max(oo_scores.values()) - min(oo_scores.values())) if len(oo_scores) > 1 else 0.0
    freshness = max(0, 1.0 - age_max / 365.0)

    # Queue actions
    if type_count == 1 and n_assets > 1:
        _queue_action(action_queue, "HIGH", "MODEL_DEV", "D1",
                      "STRATEGY_HOMOGENEITY",
                      f"All {n_assets} assets use the same (model, feature) pair",
                      "No strategy diversification. Single strategy failure affects all assets.",
                      "Develop alternative strategies via P1/P2",
                      {"type_count": type_count, "n_assets": n_assets})

    if age_max > STALENESS_HIGH_DAYS:
        stale = [u for u, age in strategy_ages.items() if age > STALENESS_HIGH_DAYS]
        _queue_action(action_queue, "MEDIUM", "RESEARCH", "D1",
                      "STRATEGY_STALENESS",
                      f"Strategy for {stale} is {age_max} days old",
                      "Strategies older than 180 days may have degraded.",
                      f"Schedule P1/P2 re-run for stale assets: {stale}",
                      {"age_max": age_max, "stale_assets": stale})

    if oo_min < OO_WEAKNESS_THRESHOLD:
        weak = [u for u, oo in oo_scores.items() if oo < OO_WEAKNESS_THRESHOLD]
        _queue_action(action_queue, "MEDIUM", "MODEL_DEV", "D1",
                      "WEAK_OO_SCORE",
                      f"Assets {weak} have OO scores below {OO_WEAKNESS_THRESHOLD}",
                      f"OO range [{oo_min:.4f}, {max(oo_scores.values()):.4f}]",
                      "Re-run P1 with additional models/features for weak assets",
                      {"oo_min": oo_min})

    return _weighted_mean([
        (min(type_count / 3.0, 1.0), 0.3),   # strategy diversity
        (freshness, 0.3),                      # freshness (was placeholder)
        (oo_min, 0.2),                         # weakest link
        (1.0 - min(oo_spread, 0.5) / 0.5, 0.2),  # consistency
    ])


# ════════════════════════════════════════════════════════════════════════
# D2: FEATURE PORTFOLIO HEALTH
# ════════════════════════════════════════════════════════════════════════

def compute_d2(action_queue: list) -> float:
    """D2: Feature Portfolio Health — distinct features, reuse, decay flags."""
    with get_cursor() as cur:
        cur.execute(
            "SELECT locked_strategy FROM p3_d00_asset_universe "
            "WHERE captain_status = 'ACTIVE'"
        )
        rows = cur.fetchall()

    if not rows:
        return 0.0

    features = []
    for r in rows:
        s = json.loads(r[0]) if r[0] else {}
        features.append(s.get("feature", s.get("k", 0)))

    distinct = len(set(features))
    counts = Counter(features)
    max_reuse = max(counts.values()) if counts else 0
    most_reused = max(counts, key=counts.get) if counts else "unknown"
    n_assets = len(rows)

    # Check for decay flags: features with FRAGILE status in P3-D13 sensitivity scans
    decay_flagged_features = set()
    with get_cursor() as cur:
        cur.execute(
            "SELECT asset_id, robustness_status FROM p3_d13_sensitivity_scan_results "
            "ORDER BY scan_date DESC"
        )
        scan_rows = cur.fetchall()

    # Deduplicate by asset (latest scan per asset)
    seen_assets = set()
    for sr in scan_rows:
        if sr[0] not in seen_assets:
            seen_assets.add(sr[0])
            if sr[1] == "FRAGILE":
                # Look up which feature this asset uses
                for r in rows:
                    s = json.loads(r[0]) if r[0] else {}
                    if s.get("asset") == sr[0]:
                        decay_flagged_features.add(s.get("feature", s.get("k", 0)))

    n_decay_flagged = len(decay_flagged_features)
    decay_score = 1.0 - n_decay_flagged / max(distinct, 1)

    # Queue actions
    if max_reuse >= 0.6 * n_assets and n_assets > 1:
        _queue_action(action_queue, "MEDIUM", "FEATURE_DEV", "D2",
                      "FEATURE_CONCENTRATION",
                      f"{max_reuse}/{n_assets} assets use feature {most_reused}",
                      "Feature concentration risk — single feature degradation affects most assets.",
                      "Diversify feature selection in P1. Consider asset-specific features.")

    if n_decay_flagged > 0:
        _queue_action(action_queue, "HIGH", "RESEARCH", "D2",
                      "FEATURE_DECAY_FLAG",
                      f"Features with sensitivity decay flag: {list(decay_flagged_features)}",
                      "These features showed FRAGILE status in AIM-13 sensitivity scan.",
                      "Re-run P1 Block 2B for affected assets to confirm or replace features")

    return _weighted_mean([
        (min(distinct / max(n_assets, 1), 1.0), 0.4),      # diversity
        (1.0 - max_reuse / max(n_assets, 1), 0.3),          # concentration
        (decay_score, 0.3),                                   # decay flags (was placeholder)
    ])


# ════════════════════════════════════════════════════════════════════════
# D3: MODEL STALENESS TRACKER
# ════════════════════════════════════════════════════════════════════════

def compute_d3(action_queue: list) -> float:
    """D3: Model Staleness — per-asset P1/P2 age (p3_d22b), regime model, AIM retrain.

    Q-19: Primary P1/P2 staleness uses last_p1p2_rerun_ts per asset from
    p3_d22b_asset_rerun_status; global injection timestamps are not used.
    """
    p1p2_age_by_asset = _active_asset_p1p2_stale_days()
    max_p1p2_stale = max(p1p2_age_by_asset.values()) if p1p2_age_by_asset else 0

    # Regime model ages per asset (locked_strategy timestamps; prefer D22b rerun)
    with get_cursor() as cur:
        cur.execute(
            "SELECT asset_id, locked_strategy, last_updated "
            "FROM p3_d00_asset_universe WHERE captain_status = 'ACTIVE'"
        )
        asset_rows = cur.fetchall()

    with get_cursor() as cur:
        cur.execute(
            "SELECT asset, last_p1p2_rerun_ts FROM p3_d22b_asset_rerun_status "
            "LATEST ON last_updated PARTITION BY asset"
        )
        rerun_rows = cur.fetchall()
    rerun_ts_by_asset = {row[0]: row[1] for row in (rerun_rows or [])}

    regime_model_ages = {}
    for ar in asset_rows:
        s = json.loads(ar[1]) if ar[1] else {}
        regime_ts = (
            rerun_ts_by_asset.get(ar[0])
            or s.get("p2_locked_at")
            or s.get("timestamp")
            or ar[2]
        )
        regime_model_ages[ar[0]] = _safe_days_since(regime_ts)

    max_regime_age = max(regime_model_ages.values()) if regime_model_ages else 0

    # AIM retrain ages (from P3-D01.last_retrained)
    with get_cursor() as cur:
        cur.execute(
            "SELECT aim_id, last_retrained FROM p3_d01_aim_model_states "
            "WHERE status = 'ACTIVE' ORDER BY aim_id"
        )
        aim_rows = cur.fetchall()

    aim_retrain_ages = {}
    seen_aims = set()
    for ar in aim_rows:
        if ar[0] not in seen_aims:
            seen_aims.add(ar[0])
            aim_retrain_ages[ar[0]] = _safe_days_since(ar[1])

    max_aim_retrain = max(aim_retrain_ages.values()) if aim_retrain_ages else 999

    # Queue: portfolio-wide P1/P2 backlog using worst per-asset staleness (Q-19)
    if max_p1p2_stale > STALENESS_MEDIUM_DAYS:
        worst_assets = sorted(
            [a for a, d in p1p2_age_by_asset.items() if d > STALENESS_MEDIUM_DAYS],
            key=lambda x: p1p2_age_by_asset[x],
            reverse=True,
        )[:10]
        priority = "HIGH" if max_p1p2_stale > STALENESS_HIGH_DAYS else "MEDIUM"
        _queue_action(action_queue, priority, "RESEARCH", "D3",
                      "PIPELINE_STALENESS",
                      f"No recent P1/P2 rerun for worst asset in {max_p1p2_stale} days "
                      f"(sample stale: {worst_assets})",
                      "Per-asset pipeline staleness from p3_d22b — refresh P1/P2 for stale assets.",
                      "Schedule P1/P2 re-run for stale assets; verify last_p1p2_rerun_ts writers.",
                      {"max_days_since_p1p2": max_p1p2_stale, "worst_assets": worst_assets})

    for asset_id, age in regime_model_ages.items():
        if age > STALENESS_HIGH_DAYS:
            _queue_action(action_queue, "MEDIUM", "MODEL_DEV", "D3",
                          f"REGIME_MODEL_STALE_{asset_id}",
                          f"Regime model for {asset_id} is {age} days old",
                          "Regime classification degrades as volatility structure evolves.",
                          f"Re-run P2 Block 3b for {asset_id}")

    if max_aim_retrain > STALENESS_MEDIUM_DAYS:
        stale_aims = [a for a, age in aim_retrain_ages.items() if age > STALENESS_MEDIUM_DAYS]
        _queue_action(action_queue, "MEDIUM", "AIM_IMPROVEMENT", "D3",
                      "AIM_RETRAIN_STALE",
                      f"AIMs {stale_aims} not retrained in {max_aim_retrain}+ days",
                      "Stale AIMs may not reflect current market dynamics.",
                      "Verify weekly retrain schedule is running")

    # Three independent components (no duplicate global injection term — F-35)
    return _weighted_mean([
        (max(0, 1.0 - max_p1p2_stale / 180.0), 0.40),
        (max(0, 1.0 - max_regime_age / 365.0), 0.35),
        (max(0, 1.0 - max_aim_retrain / 90.0), 0.25),
    ])


# ════════════════════════════════════════════════════════════════════════
# D4: AIM EFFECTIVENESS PORTFOLIO
# ════════════════════════════════════════════════════════════════════════

def compute_d4(action_queue: list) -> float:
    """D4: AIM Effectiveness — rolling monthly modifier-vs-PnL hit rate (Q-20)."""
    cutoff = (now_et() - timedelta(days=MONTHLY_HIT_WINDOW_DAYS)).isoformat()
    with get_cursor() as cur:
        cur.execute(
            "SELECT pnl, aim_breakdown_at_entry FROM p3_d03_trade_outcome_log "
            "WHERE ts > %s",
            (cutoff,),
        )
        rows = cur.fetchall()

    if not rows:
        return 1.0

    # Per-AIM: informative hits / informative trades
    inform_hits: dict[int, int] = {}
    inform_total: dict[int, int] = {}

    for pnl, breakdown_raw in rows:
        if breakdown_raw:
            try:
                bd = loads_decimal(breakdown_raw)
            except (TypeError, ValueError, json.JSONDecodeError):
                bd = {}
        else:
            bd = {}
        if not isinstance(bd, dict):
            continue
        pnl_f = to_float(pnl)  # NULL pnl rows: skipped (hit returns None below).
        if pnl is None:
            continue
        for aid_str, payload in bd.items():
            try:
                aid = int(aid_str)
            except (ValueError, TypeError):
                continue
            if not isinstance(payload, dict):
                continue
            mod_raw = payload.get("modifier", 1.0)
            mod = float(mod_raw)
            hit = _modifier_pnl_hit(mod, pnl_f)
            if hit is None:
                continue
            inform_total[aid] = inform_total.get(aid, 0) + 1
            inform_hits[aid] = inform_hits.get(aid, 0) + (1 if hit else 0)

    if not inform_total:
        return 1.0

    rates = []
    low_hit_aims = []
    for aid, n in inform_total.items():
        hr = inform_hits.get(aid, 0) / max(n, 1)
        rates.append(hr)
        if n >= 5 and hr < 0.45:
            low_hit_aims.append((aid, hr, n))

    for aid, hr, n in low_hit_aims:
        _queue_action(action_queue, "MEDIUM", "AIM_IMPROVEMENT", "D4",
                      f"AIM_HIT_RATE_LOW_{aid}",
                      f"AIM-{aid:02d} monthly hit rate {hr:.1%} over {n} informative trades",
                      "Modifier directional agreement with PnL below threshold.",
                      "Review AIM inputs and regime alignment; confirm DMA modifiers.")

    score = sum(rates) / len(rates)
    return max(0.0, min(1.0, score))


# ════════════════════════════════════════════════════════════════════════
# D5: EDGE TRAJECTORY (monthly only)
# ════════════════════════════════════════════════════════════════════════

def _compute_windowed_edge(window_days: int) -> float:
    """Compute system-wide expected edge from EWMA states within a time window."""
    cutoff = (now_et() - timedelta(days=window_days)).isoformat()
    with get_cursor() as cur:
        cur.execute(
            "SELECT win_rate, avg_win, avg_loss FROM p3_d05_ewma_states "
            "WHERE last_updated > %s",
            (cutoff,),
        )
        rows = cur.fetchall()

    if not rows:
        return 0.0
    edges = [_compute_edge(r[0], r[1], r[2]) for r in rows]
    return sum(edges) / len(edges)


def _compute_regime_edge(regime: str, window_days: int) -> float:
    """Compute expected edge for a specific regime within a time window."""
    cutoff = (now_et() - timedelta(days=window_days)).isoformat()
    with get_cursor() as cur:
        cur.execute(
            "SELECT win_rate, avg_win, avg_loss FROM p3_d05_ewma_states "
            "WHERE regime = %s AND last_updated > %s",
            (regime, cutoff),
        )
        rows = cur.fetchall()

    if not rows:
        return 0.0
    edges = [_compute_edge(r[0], r[1], r[2]) for r in rows]
    return sum(edges) / len(edges)


def compute_d5(action_queue: list) -> float:
    """D5: Edge Trajectory (MONTHLY only) — 30/60/90d edge, trend, regime breakdown."""
    edge_30d = _compute_windowed_edge(30)
    edge_60d = _compute_windowed_edge(60)
    edge_90d = _compute_windowed_edge(90)

    # Per-regime breakdown (60d window)
    edge_low_vol = _compute_regime_edge("LOW_VOL", 60)
    edge_high_vol = _compute_regime_edge("HIGH_VOL", 60)
    worst_regime_edge = min(edge_low_vol, edge_high_vol)

    # Trend: compare 30d to 90d
    if abs(edge_90d) > 1e-8:
        edge_trend = (edge_30d - edge_90d) / abs(edge_90d)
    else:
        edge_trend = 0.0

    # Queue actions
    if edge_trend < -EDGE_DECLINE_THRESHOLD:
        _queue_action(action_queue, "HIGH", "RESEARCH", "D5",
                      "EDGE_DECLINING",
                      f"System-wide edge declined {abs(edge_trend)*100:.0f}% over 60 days",
                      f"30d edge: {edge_30d:.4f}, 90d edge: {edge_90d:.4f}. "
                      "May indicate strategy decay or market microstructure shift.",
                      "Cross-reference with decay detector and AIM weights.",
                      {"edge_30d": edge_30d, "edge_90d": edge_90d, "trend": edge_trend})

    if edge_high_vol < 0:
        _queue_action(action_queue, "HIGH", "RESEARCH", "D5",
                      "REGIME_EDGE_COLLAPSE",
                      f"HIGH_VOL regime edge is negative ({edge_high_vol:.4f})",
                      "Strategy is losing money in high-volatility regimes.",
                      "Check AIM-11 transition accuracy and regime model validation (P2-D08)",
                      {"edge_high_vol": edge_high_vol, "edge_low_vol": edge_low_vol})

    if edge_30d < 0:
        _queue_action(action_queue, "HIGH", "RESEARCH", "D5",
                      "EDGE_NEGATIVE",
                      f"30-day system edge is negative: {edge_30d:.4f}",
                      "Strategy may have lost edge in recent window.",
                      "Investigate decay detector status + AIM weight distribution")

    return _weighted_mean([
        (min(max(edge_30d, 0) / 0.02, 1.0), 0.3),                    # current edge level
        (0.5 + min(max(edge_trend, -0.5), 0.5), 0.4),                 # trend direction
        (min(max(worst_regime_edge, 0) / 0.01, 1.0), 0.3),            # worst regime
    ])


# ════════════════════════════════════════════════════════════════════════
# D6: DATA COVERAGE GAPS
# ════════════════════════════════════════════════════════════════════════

def compute_d6(action_queue: list) -> float:
    """D6: Data Coverage Gaps — AIM missing rates, asset data quality."""
    # AIM data gap checks
    with get_cursor() as cur:
        cur.execute(
            "SELECT aim_id, missing_data_rate_30d FROM p3_d01_aim_model_states "
            "WHERE missing_data_rate_30d > 0.1"
        )
        aim_issues = cur.fetchall()

    # Deduplicate by aim_id (take first = latest)
    seen_aims = set()
    unique_issues = []
    for r in aim_issues:
        if r[0] not in seen_aims:
            seen_aims.add(r[0])
            unique_issues.append(r)

    # Queue actions with severity-based priority
    for aim_id, rate in unique_issues:
        priority = "HIGH" if rate > 0.2 else "MEDIUM"
        _queue_action(action_queue, priority, "DATA_ACQUISITION", "D6",
                      f"AIM_DATA_GAP_{aim_id}",
                      f"AIM-{aim_id:02d} data feed: {rate*100:.0f}% missing in last 30d",
                      "High missing rate degrades AIM quality and may trigger DMA suppression.",
                      "Verify data source availability. Check API connectivity.")

    # Asset data quality: count decay events as proxy for data issues
    with get_cursor() as cur:
        cur.execute(
            "SELECT asset_id, count() FROM p3_d04_decay_detector_states "
            "WHERE decay_events IS NOT NULL GROUP BY asset_id"
        )
        asset_quality_rows = cur.fetchall()

    asset_quality_scores = []
    for ar in asset_quality_rows:
        event_count = ar[1] or 0
        # More decay events -> lower quality score
        quality = max(0, 1.0 - event_count / 20.0)
        asset_quality_scores.append(quality)

        if event_count >= 3:
            _queue_action(action_queue, "MEDIUM", "DATA_ACQUISITION", "D6",
                          f"ASSET_DATA_UNRELIABLE_{ar[0]}",
                          f"Asset {ar[0]}: {event_count} decay alert events",
                          "Frequent decay alerts may indicate unreliable data or genuine strategy degradation.",
                          f"Investigate data source for {ar[0]}")

    mean_quality = (sum(asset_quality_scores) / len(asset_quality_scores)) if asset_quality_scores else 1.0

    # Data hold rate: count DATA_HOLD entries in P3-D17 system monitor (last 30 days)
    # Online Block 9 writes data_quality entries with category='data_quality'
    # when sessions are held due to data issues.
    cutoff_30d = (now_et() - timedelta(days=30)).isoformat()
    with get_cursor() as cur:
        cur.execute(
            "SELECT asset_id, count() FROM p3_d00_asset_universe "
            "WHERE captain_status = 'ACTIVE' GROUP BY asset_id"
        )
        active_assets = {r[0]: 0 for r in cur.fetchall()}

    # Count data hold events per asset from P3-D17
    if active_assets:
        with get_cursor() as cur:
            cur.execute(
                "SELECT param_value, count() FROM p3_d17_system_monitor_state "
                "WHERE category = 'data_quality' AND last_updated > %s "
                "GROUP BY param_value",
                (cutoff_30d,),
            )
            hold_rows = cur.fetchall()

        for hr in hold_rows:
            # param_value may contain asset_id for asset-specific holds
            asset = hr[0] if hr[0] in active_assets else None
            if asset:
                active_assets[asset] = hr[1] or 0

    n_active = len(active_assets)
    if n_active > 0:
        assets_with_holds = sum(1 for c in active_assets.values() if c > 2)
        hold_rate_score = 1.0 - assets_with_holds / n_active
    else:
        hold_rate_score = 1.0

    # Queue actions for assets with frequent holds
    for asset_id, hold_count in active_assets.items():
        if hold_count >= 3:
            _queue_action(action_queue, "MEDIUM", "DATA_ACQUISITION", "D6",
                          f"ASSET_DATA_HOLD_{asset_id}",
                          f"Asset {asset_id}: {hold_count} DATA_HOLD events in 30 days",
                          "Frequent data holds cause missed trading sessions.",
                          f"Investigate data feed reliability for {asset_id}")

    return _weighted_mean([
        (1.0 - len(unique_issues) / 15.0, 0.5),     # AIM data coverage
        (mean_quality, 0.3),                           # asset data quality
        (hold_rate_score, 0.2),                        # data hold rate
    ])


# ════════════════════════════════════════════════════════════════════════
# D8: RESOLUTION VERIFICATION
# ════════════════════════════════════════════════════════════════════════

def compute_d8(action_queue: list) -> float:
    """D8: Resolution Verification — verify resolved items, stale detection."""
    now = now_et()

    for item in action_queue:
        status = item.get("status", "")

        # Verify resolved items: check if metric actually improved
        if status == "RESOLVED":
            metric_before = item.get("metric_snapshot_at_creation", {})
            if metric_before:
                # Compare against current state
                result = _check_constraint_resolution(item.get("constraint_type", ""))
                if result == "IMPROVED":
                    item["status"] = "VERIFIED"
                    item["verified_at"] = now.isoformat()
                    item["verification_result"] = "IMPROVED"
                elif result == "NOT_IMPROVED":
                    # Metric didn't improve — reopen
                    item["status"] = "OPEN"
                    item["verification_result"] = "NOT_IMPROVED"
                    item["notes"] = (item.get("notes", "") +
                                     " [Auto-reopened: metric did not improve after resolution]").strip()
                else:
                    # INCONCLUSIVE — keep as RESOLVED, may need more time
                    item["verification_result"] = "INCONCLUSIVE"

        # Stale detection for OPEN/ACKNOWLEDGED items
        elif status in ("OPEN", "ACKNOWLEDGED"):
            try:
                created = datetime.fromisoformat(item["created"]) if isinstance(item["created"], str) else item["created"]
                if (now - created).days > ACTION_STALE_DAYS:
                    item["status"] = "STALE"
            except (ValueError, TypeError):
                pass

    open_stale = sum(1 for i in action_queue if i.get("status") in ("OPEN", "STALE"))
    total = len(action_queue)

    return 1.0 - open_stale / max(total, 1)


def _check_constraint_resolution(constraint_type: str) -> str:
    """Check if a resolved constraint has actually improved.

    Returns:
        "IMPROVED" — constraint no longer active, resolution worked
        "NOT_IMPROVED" — constraint still active, should reopen
        "INCONCLUSIVE" — can't determine, keep as RESOLVED
    """
    try:
        if constraint_type == "STRATEGY_HOMOGENEITY":
            with get_cursor() as cur:
                cur.execute(
                    "SELECT locked_strategy FROM p3_d00_asset_universe "
                    "WHERE captain_status = 'ACTIVE'"
                )
                rows = cur.fetchall()
            types = set()
            for r in rows:
                s = json.loads(r[0]) if r[0] else {}
                types.add((s.get("model", 0), s.get("feature", 0)))
            if len(types) > 1 or len(rows) <= 1:
                return "IMPROVED"
            return "NOT_IMPROVED"

        elif constraint_type == "EDGE_NEGATIVE":
            edge = _compute_windowed_edge(30)
            if edge > 0.005:
                return "IMPROVED"
            elif edge < 0:
                return "NOT_IMPROVED"
            return "INCONCLUSIVE"  # near-zero — need more time

        elif constraint_type.startswith("AIM_DATA_GAP_"):
            aim_id = int(constraint_type.split("_")[-1])
            with get_cursor() as cur:
                cur.execute(
                    "SELECT missing_data_rate_30d FROM p3_d01_aim_model_states "
                    "WHERE aim_id = %s "
                    "LATEST ON last_updated PARTITION BY aim_id",
                    (aim_id,),
                )
                row = cur.fetchone()
            if row is None or row[0] is None:
                return "INCONCLUSIVE"
            if row[0] <= 0.05:
                return "IMPROVED"
            elif row[0] > 0.1:
                return "NOT_IMPROVED"
            return "INCONCLUSIVE"  # between 0.05-0.1 — partially improved

        elif constraint_type.startswith("LEVEL3_UNRESOLVED"):
            with get_cursor() as cur:
                cur.execute(
                    "SELECT count() FROM p3_d00_asset_universe "
                    "WHERE captain_status = 'DECAYED'"
                )
                row = cur.fetchone()
            if row is None or row[0] == 0:
                return "IMPROVED"
            return "NOT_IMPROVED"

        elif constraint_type == "PIPELINE_STALENESS":
            stale = _active_asset_p1p2_stale_days()
            max_days = max(stale.values()) if stale else 0
            if max_days < STALENESS_MEDIUM_DAYS:
                return "IMPROVED"
            return "NOT_IMPROVED"

    except Exception:
        pass

    # Default: can't verify
    return "INCONCLUSIVE"


# ════════════════════════════════════════════════════════════════════════
# AGGREGATE AND STORE
# ════════════════════════════════════════════════════════════════════════

def _overall_health_equal_weight(scores: dict, mode: str) -> float:
    """Q-34: equal weights 1/N over active dimensions (no D7 in v1)."""
    keys = OVERALL_HEALTH_KEYS_MONTHLY if mode == "MONTHLY" else OVERALL_HEALTH_KEYS_WEEKLY
    vals = [scores[k] for k in keys]
    return sum(vals) / len(vals) if vals else 0.0


def run_diagnostic(mode: str = "WEEKLY") -> dict:
    """Execute P3-PG-16B: system health diagnostic.

    Args:
        mode: "WEEKLY" (D1-D4, D6, D8 — no D5, no D7 per Q-21) or
              "MONTHLY" (adds D5 edge_trajectory; still no D7)

    Returns:
        Diagnostic result dict for P3-D22
    """
    # Load existing action queue
    with get_cursor() as cur:
        cur.execute("SELECT action_queue FROM p3_d22_system_health_diagnostic ORDER BY ts DESC LIMIT 1")
        row = cur.fetchone()
    action_queue = json.loads(row[0]) if row and row[0] else []

    scores = {}
    scores["strategy_portfolio"] = compute_d1(action_queue)
    scores["feature_portfolio"] = compute_d2(action_queue)
    scores["model_staleness"] = compute_d3(action_queue)
    scores["aim_effectiveness"] = compute_d4(action_queue)

    if mode == "MONTHLY":
        scores["edge_trajectory"] = compute_d5(action_queue)

    scores["data_coverage"] = compute_d6(action_queue)
    scores["resolution_health"] = compute_d8(action_queue)

    overall = _overall_health_equal_weight(scores, mode)

    result = {
        "mode": mode,
        "scores": scores,
        "overall_health": overall,
        "action_items_generated": len([
            i for i in action_queue
            if i.get("created", "").startswith(now_et().strftime("%Y-%m-%d"))
        ]),
        "critical_count": sum(
            1 for i in action_queue if i["priority"] == "CRITICAL" and i["status"] == "OPEN"
        ),
        "high_count": sum(
            1 for i in action_queue if i["priority"] == "HIGH" and i["status"] == "OPEN"
        ),
        "queue_total": len(action_queue),
        "open_count": sum(1 for i in action_queue if i["status"] == "OPEN"),
        "stale_count": sum(1 for i in action_queue if i["status"] == "STALE"),
    }

    # Cap action queue: drop oldest entries when exceeding max size
    if len(action_queue) > MAX_ACTION_QUEUE_SIZE:
        action_queue = action_queue[-MAX_ACTION_QUEUE_SIZE:]

    # Store to P3-D22
    with get_cursor() as cur:
        qexecute(
            cur,
            """INSERT INTO p3_d22_system_health_diagnostic
               (mode, scores, overall_health, action_items_generated,
                critical_count, high_count, queue_total, open_count,
                stale_count, action_queue, ts)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now())""",
            (mode, json.dumps(scores), overall, result["action_items_generated"],
             result["critical_count"], result["high_count"], result["queue_total"],
             result["open_count"], result["stale_count"], json.dumps(action_queue)),
        )

    logger.info("Diagnostic [%s]: overall=%.2f, actions=%d (critical=%d, high=%d, stale=%d)",
                mode, overall, result["queue_total"], result["critical_count"],
                result["high_count"], result["stale_count"])

    return result
