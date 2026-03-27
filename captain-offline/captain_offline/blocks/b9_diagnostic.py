# region imports
try:
    from AlgorithmImports import *
except ImportError:
    pass
# endregion
"""System Health Diagnostic — P3-PG-16B (Tasks 2.9a, 2.9b / OFF lines 717-1021).

8-dimension diagnostic with QUEUE_ACTION helper for human action items.

Dimensions:
  D1: Strategy Portfolio Health (diversity, freshness, OO scores)
  D2: Feature Portfolio Health (distinct features, reuse, decay flags)
  D3: Model Staleness (P1/P2 ages, regime model, AIM retrain)
  D4: AIM Effectiveness (active count, dormant, dominant, warmup)
  D5: Edge Trajectory (30/60/90d edge, trend, regime breakdown) — MONTHLY only
  D6: Data Coverage Gaps (AIM missing rates, asset holds)
  D7: Research Pipeline (injection recency, unresolved Level 3)
  D8: Resolution Verification (resolved items verified, stale detection)

Schedule: WEEKLY (D1-D4, D6-D8), MONTHLY (all D1-D8 including D5)

Reads: P2-D06, P2-D07, P3-D00..D06, D13, D17, D22
Writes: P3-D22
"""

import json
import logging
from collections import Counter
from datetime import datetime, timedelta

from shared.questdb_client import get_cursor

logger = logging.getLogger(__name__)

# Thresholds from Arch §9
STALENESS_MEDIUM_DAYS = 90
STALENESS_HIGH_DAYS = 180
OO_WEAKNESS_THRESHOLD = 0.55
AIM_DORMANCY_WEIGHT = 0.05
AIM_DORMANCY_DAYS = 30
AIM_DOMINANCE_WEIGHT = 0.30
EDGE_DECLINE_THRESHOLD = 0.15
ACTION_STALE_DAYS = 90


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
        delta = datetime.now() - ts
        return max(getattr(delta, "days", 0), 0)
    except (ValueError, TypeError):
        return 999


def _compute_edge(win_rate: float, avg_win: float, avg_loss: float) -> float:
    """Expected edge per trade = p*W - (1-p)*L."""
    wr = win_rate or 0.5
    aw = avg_win or 0.01
    al = avg_loss or 0.01
    return wr * aw - (1 - wr) * al


def _queue_action(action_queue: list, priority: str, category: str,
                   dimension: str, constraint_type: str, title: str,
                   detail: str, recommendation: str,
                   metric_snapshot: dict | None = None):
    """QUEUE_ACTION helper: add or update action item with deduplication."""
    # Deduplication: don't create duplicate if same constraint_type is open
    for item in action_queue:
        if (item["constraint_type"] == constraint_type
                and item["status"] in ("OPEN", "ACKNOWLEDGED", "IN_PROGRESS")):
            item["last_seen"] = datetime.now().isoformat()
            item["detail"] = detail
            return

    action_queue.append({
        "action_id": f"ACT-{datetime.now().strftime('%Y-%m-%d')}-{len(action_queue)+1:03d}",
        "created": datetime.now().isoformat(),
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
        "last_seen": datetime.now().isoformat(),
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
    """D3: Model Staleness — P1/P2 ages, regime model, AIM retrain ages."""
    # Last injection date (proxy for last P1/P2 run)
    with get_cursor() as cur:
        cur.execute("SELECT max(ts) FROM p3_d06_injection_history")
        row = cur.fetchone()
    days_since_injection = _safe_days_since(row[0] if row else None)

    # Regime model ages per asset (from locked_strategy timestamp in P3-D00)
    with get_cursor() as cur:
        cur.execute(
            "SELECT asset_id, locked_strategy, last_updated "
            "FROM p3_d00_asset_universe WHERE captain_status = 'ACTIVE'"
        )
        asset_rows = cur.fetchall()

    regime_model_ages = {}
    for ar in asset_rows:
        s = json.loads(ar[1]) if ar[1] else {}
        # Use strategy timestamp or P2 completion date if available
        regime_ts = s.get("p2_locked_at") or s.get("timestamp") or ar[2]
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

    # Queue actions
    if days_since_injection > STALENESS_MEDIUM_DAYS:
        priority = "HIGH" if days_since_injection > STALENESS_HIGH_DAYS else "MEDIUM"
        _queue_action(action_queue, priority, "RESEARCH", "D3",
                      "PIPELINE_STALENESS",
                      f"No P1/P2 run in {days_since_injection} days",
                      "Strategy pipeline has not been refreshed.",
                      "Schedule full P1/P2 run across all assets",
                      {"days_since": days_since_injection})

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

    return _weighted_mean([
        (max(0, 1.0 - days_since_injection / 180.0), 0.3),       # P1/P2 freshness
        (max(0, 1.0 - max_regime_age / 365.0), 0.3),              # regime model freshness
        (max(0, 1.0 - max_aim_retrain / 90.0), 0.2),              # AIM retrain freshness
        (max(0, 1.0 - days_since_injection / 180.0), 0.2),        # P2 freshness (same proxy)
    ])


# ════════════════════════════════════════════════════════════════════════
# D4: AIM EFFECTIVENESS PORTFOLIO
# ════════════════════════════════════════════════════════════════════════

def compute_d4(action_queue: list) -> float:
    """D4: AIM Effectiveness — active, dormant, dominant, warmup."""
    # Load AIM weights
    with get_cursor() as cur:
        cur.execute(
            "SELECT aim_id, inclusion_probability, days_below_threshold "
            "FROM p3_d02_aim_meta_weights ORDER BY aim_id"
        )
        weight_rows = cur.fetchall()

    # Load AIM statuses
    with get_cursor() as cur:
        cur.execute(
            "SELECT aim_id, status FROM p3_d01_aim_model_states ORDER BY aim_id"
        )
        status_rows = cur.fetchall()

    if not weight_rows:
        return 0.0

    # Deduplicate by aim_id (latest per AIM)
    by_aim = {}
    for r in weight_rows:
        if r[0] not in by_aim:
            by_aim[r[0]] = {"prob": r[1], "days_below": r[2] or 0}

    aim_statuses = {}
    for r in status_rows:
        if r[0] not in aim_statuses:
            aim_statuses[r[0]] = r[1]

    active_count = sum(1 for s in aim_statuses.values() if s == "ACTIVE")
    warmup_count = sum(1 for s in aim_statuses.values() if s == "WARM_UP")

    dormant = [(aid, d) for aid, d in by_aim.items()
               if d["prob"] < AIM_DORMANCY_WEIGHT
               and d["days_below"] > AIM_DORMANCY_DAYS
               and aim_statuses.get(aid) == "ACTIVE"]

    dominant = [(aid, d) for aid, d in by_aim.items()
                if d["prob"] > AIM_DOMINANCE_WEIGHT]

    # Queue actions for dormant AIMs
    for aid, d in dormant:
        _queue_action(action_queue, "LOW", "AIM_IMPROVEMENT", "D4",
                      f"AIM_DORMANT_{aid}",
                      f"AIM-{aid:02d} dormant — weight {d['prob']:.3f} for {d['days_below']} days",
                      "DMA suppressed this AIM due to low predictive value.",
                      f"Check data feed quality for AIM-{aid:02d}. If clean, AIM may be uninformative.")

    # Queue actions for dominant AIMs
    for aid, d in dominant:
        _queue_action(action_queue, "MEDIUM", "AIM_IMPROVEMENT", "D4",
                      f"AIM_DOMINANT_{aid}",
                      f"AIM-{aid:02d} contributes {d['prob']:.1%} — concentration risk",
                      "System reliance on single AIM.",
                      "Review why other AIMs are underperforming. Expand data sources.")

    # Queue action for warmup backlog
    if warmup_count > 5:
        warming_aims = [a for a, s in aim_statuses.items() if s == "WARM_UP"]
        _queue_action(action_queue, "LOW", "DATA_ACQUISITION", "D4",
                      "AIM_WARMUP_BACKLOG",
                      f"{warmup_count} AIMs still in warm-up: {warming_aims}",
                      "Large warm-up backlog means system operates with limited intelligence.",
                      "Provide bootstrapped historical data for slow-warming AIMs")

    return _weighted_mean([
        (active_count / 15.0, 0.3),                                   # active ratio
        (1.0 - len(dormant) / max(active_count, 1), 0.3),             # dormancy
        (1.0 - len(dominant) / max(active_count, 1), 0.2),            # dominance
        (1.0 - warmup_count / 15.0, 0.2),                             # warmup backlog
    ])


# ════════════════════════════════════════════════════════════════════════
# D5: EDGE TRAJECTORY (monthly only)
# ════════════════════════════════════════════════════════════════════════

def _compute_windowed_edge(window_days: int) -> float:
    """Compute system-wide expected edge from EWMA states within a time window."""
    cutoff = (datetime.now() - timedelta(days=window_days)).isoformat()
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
    cutoff = (datetime.now() - timedelta(days=window_days)).isoformat()
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
    cutoff_30d = (datetime.now() - timedelta(days=30)).isoformat()
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
# D7: RESEARCH PIPELINE THROUGHPUT
# ════════════════════════════════════════════════════════════════════════

def compute_d7(action_queue: list) -> float:
    """D7: Research Pipeline — injection recency, unresolved Level 3, expansion."""
    # Days since last injection
    with get_cursor() as cur:
        cur.execute("SELECT max(ts) FROM p3_d06_injection_history")
        row = cur.fetchone()
    days_since_injection = _safe_days_since(row[0] if row else None)

    # Level 3 decay events in last 90 days
    cutoff_90d = (datetime.now() - timedelta(days=90)).isoformat()
    level3_total = 0
    level3_unresolved_assets = []

    with get_cursor() as cur:
        cur.execute(
            "SELECT asset_id, decay_events FROM p3_d04_decay_detector_states "
            "WHERE decay_events IS NOT NULL AND last_updated > %s",
            (cutoff_90d,),
        )
        decay_rows = cur.fetchall()

    for dr in decay_rows:
        try:
            event = json.loads(dr[1]) if dr[1] else {}
            if isinstance(event, dict) and event.get("level") == 3:
                level3_total += 1
                level3_unresolved_assets.append(dr[0])
        except (json.JSONDecodeError, TypeError):
            pass

    # Check which Level 3 assets have been resolved (have injection or ACTIVE status)
    resolved_assets = set()
    if level3_unresolved_assets:
        with get_cursor() as cur:
            cur.execute(
                "SELECT asset_id FROM p3_d00_asset_universe WHERE captain_status = 'ACTIVE'"
            )
            active = {r[0] for r in cur.fetchall()}
        resolved_assets = set(level3_unresolved_assets) & active

    truly_unresolved = [a for a in level3_unresolved_assets if a not in resolved_assets]

    # Auto-expansion attempts (from injection history with type = AUTO_EXPANSION)
    with get_cursor() as cur:
        cur.execute(
            "SELECT count(), "
            "sum(CASE WHEN outcome = 'ADOPTED' THEN 1 ELSE 0 END) "
            "FROM p3_d06_injection_history "
            "WHERE injection_type = 'AUTO_EXPANSION' AND ts > %s",
            (cutoff_90d,),
        )
        exp_row = cur.fetchone()
    expansion_attempts = exp_row[0] if exp_row and exp_row[0] else 0
    expansion_successes = exp_row[1] if exp_row and exp_row[1] else 0

    # Queue actions
    if days_since_injection > 120:
        priority = "HIGH" if days_since_injection > 180 else "MEDIUM"
        _queue_action(action_queue, priority, "RESEARCH", "D7",
                      "INJECTION_DROUGHT",
                      f"No new strategy injection in {days_since_injection} days",
                      "System is running on stale research.",
                      "Schedule P1/P2 run. Consider new model hypotheses.",
                      {"days_since": days_since_injection})

    if truly_unresolved:
        _queue_action(action_queue, "HIGH", "RESEARCH", "D7",
                      "LEVEL3_UNRESOLVED",
                      f"{len(truly_unresolved)} Level 3 decay events unresolved — "
                      f"assets: {truly_unresolved}",
                      "Level 3 decay halted signals but no replacement adopted.",
                      f"Prioritise P1/P2 re-runs for {truly_unresolved}")

    return _weighted_mean([
        (max(0, 1.0 - days_since_injection / 120.0), 0.4),                    # injection recency
        (1.0 - len(truly_unresolved) / max(level3_total, 1), 0.3),            # L3 resolution
        (expansion_successes / max(expansion_attempts, 1), 0.3),               # expansion success
    ])


# ════════════════════════════════════════════════════════════════════════
# D8: RESOLUTION VERIFICATION
# ════════════════════════════════════════════════════════════════════════

def compute_d8(action_queue: list) -> float:
    """D8: Resolution Verification — verify resolved items, stale detection."""
    now = datetime.now()

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
                    "WHERE aim_id = %s ORDER BY last_updated DESC LIMIT 1",
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
            with get_cursor() as cur:
                cur.execute("SELECT max(ts) FROM p3_d06_injection_history")
                row = cur.fetchone()
            days = _safe_days_since(row[0] if row else None)
            if days < STALENESS_MEDIUM_DAYS:
                return "IMPROVED"
            return "NOT_IMPROVED"

    except Exception:
        pass

    # Default: can't verify
    return "INCONCLUSIVE"


# ════════════════════════════════════════════════════════════════════════
# AGGREGATE AND STORE
# ════════════════════════════════════════════════════════════════════════

def run_diagnostic(mode: str = "WEEKLY") -> dict:
    """Execute P3-PG-16B: system health diagnostic.

    Args:
        mode: "WEEKLY" (D1-D4, D6-D8) or "MONTHLY" (all D1-D8 incl D5)

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
    scores["research_pipeline"] = compute_d7(action_queue)
    scores["resolution_health"] = compute_d8(action_queue)

    overall = sum(scores.values()) / len(scores) if scores else 0.0

    result = {
        "mode": mode,
        "scores": scores,
        "overall_health": overall,
        "action_items_generated": len([
            i for i in action_queue
            if i.get("created", "").startswith(datetime.now().strftime("%Y-%m-%d"))
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

    # Store to P3-D22
    with get_cursor() as cur:
        cur.execute(
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
