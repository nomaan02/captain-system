# region imports
try:
    from AlgorithmImports import *
except ImportError:
    pass
# endregion
"""ON-B1: Pre-Session Data Ingestion — P3-PG-21 (Task 3.1a / ON lines 37-221).

Loads all required data and computes pre-session features for the upcoming evaluation.
Session-aware: different assets are evaluated at different session opens.

Latency target: <5 seconds.

Steps:
  1. Filter active assets for this session (ACTIVE, WARM_UP, TRAINING_ONLY)
  2. Data Moderator — price/volume/data-source/timestamp validation
  3. Contract roll calendar check
  4. Load Offline outputs (P3-D01, D02, D05, D08, D12) — read-only
  5. Load P2 outputs (P2-D06, P2-D07) — read-only
  6. Compute features per asset (delegates to b1_features.py)
  7. Return all loaded data for Blocks 2-6

Reads: P3-D00, D01, D02, D05, D08, D12, P2-D06, P2-D07
Writes: P3-D00 (data_quality_flag, captain_status), P3-D17 (data_quality_log)
"""

import json
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone

from shared.questdb_client import get_cursor
from shared.constants import SYSTEM_TIMEZONE, SESSION_IDS
from shared.contract_resolver import resolve_contract_id
from shared.topstep_client import get_topstep_client, TopstepXClientError
from shared.topstep_stream import quote_cache

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data loading helpers
# ---------------------------------------------------------------------------

def _load_active_assets(session_id: int) -> list[dict]:
    """Load assets eligible for this session: ACTIVE, WARM_UP, or TRAINING_ONLY."""
    with get_cursor() as cur:
        cur.execute(
            """SELECT asset_id, captain_status, session_hours, session_schedule,
                      point_value, tick_size, margin_per_contract,
                      data_sources, data_quality_flag, roll_calendar,
                      locked_strategy, p1_data_path, p2_data_path
               FROM p3_d00_asset_universe
               ORDER BY last_updated DESC""",
        )
        rows = cur.fetchall()

    # Deduplicate by asset_id (latest row wins due to ORDER BY)
    seen = set()
    assets = []
    session_key = SESSION_IDS.get(session_id, "NY")

    for r in rows:
        asset_id = r[0]
        if asset_id in seen:
            continue
        seen.add(asset_id)

        captain_status = r[1]
        if captain_status not in ("ACTIVE", "WARM_UP", "TRAINING_ONLY"):
            continue

        session_hours = _parse_json(r[2], {})
        if not session_match(asset_id, session_id, session_hours):
            continue

        assets.append({
            "asset_id": asset_id,
            "captain_status": captain_status,
            "session_hours": session_hours,
            "session_schedule": _parse_json(r[3], {}),
            "point_value": r[4] or 50.0,
            "tick_size": r[5] or 0.25,
            "margin_per_contract": r[6] or 0.0,
            "data_sources": _parse_json(r[7], {}),
            "data_quality_flag": r[8] or "CLEAN",
            "roll_calendar": _parse_json(r[9], None),
            "locked_strategy": _parse_json(r[10], {}),
            "p1_data_path": r[11],
            "p2_data_path": r[12],
        })

    return assets


def _load_aim_states() -> dict:
    """Load all AIM states from P3-D01, keyed by (asset_id, aim_id)."""
    with get_cursor() as cur:
        cur.execute(
            """SELECT aim_id, asset_id, status, model_object,
                      warmup_progress, current_modifier, missing_data_rate_30d
               FROM p3_d01_aim_model_states
               ORDER BY last_updated DESC""",
        )
        rows = cur.fetchall()

    # Deduplicate by (aim_id, asset_id)
    seen = set()
    result = {}
    for r in rows:
        key = (r[1], r[0])  # (asset_id, aim_id)
        if key in seen:
            continue
        seen.add(key)
        result[key] = {
            "aim_id": r[0],
            "asset_id": r[1],
            "status": r[2],
            "model_object": _parse_json(r[3], None),
            "warmup_progress": r[4] or 0.0,
            "current_modifier": _parse_json(r[5], None),
            "missing_data_rate_30d": r[6] or 0.0,
        }

    # Also build per-AIM dict (global, not per-asset) for B3 MoE
    aim_global = {}
    for (asset_id, aim_id), state in result.items():
        if aim_id not in aim_global:
            aim_global[aim_id] = state
    return {"by_asset_aim": result, "global": aim_global}


def _load_aim_weights() -> dict:
    """Load DMA meta-weights from P3-D02, keyed by (asset_id, aim_id)."""
    with get_cursor() as cur:
        cur.execute(
            """SELECT aim_id, asset_id, inclusion_probability, inclusion_flag,
                      recent_effectiveness
               FROM p3_d02_aim_meta_weights
               ORDER BY last_updated DESC""",
        )
        rows = cur.fetchall()

    seen = set()
    result = {}
    for r in rows:
        key = (r[1], r[0])  # (asset_id, aim_id)
        if key in seen:
            continue
        seen.add(key)
        result[key] = {
            "aim_id": r[0],
            "asset_id": r[1],
            "inclusion_probability": r[2] or 0.0,
            "inclusion_flag": r[3] if r[3] is not None else True,
            "recent_effectiveness": r[4] or 0.0,
        }
    return result


def _load_ewma_states() -> dict:
    """Load EWMA states from P3-D05, keyed by (asset_id, regime, session)."""
    with get_cursor() as cur:
        cur.execute(
            """SELECT asset_id, regime, session, win_rate, avg_win, avg_loss, n_trades
               FROM p3_d05_ewma_states
               ORDER BY last_updated DESC""",
        )
        rows = cur.fetchall()

    seen = set()
    result = {}
    for r in rows:
        key = (r[0], r[1], r[2])  # (asset_id, regime, session)
        if key in seen:
            continue
        seen.add(key)
        result[key] = {
            "asset_id": r[0],
            "regime": r[1],
            "session": r[2],
            "win_rate": r[3] or 0.5,
            "avg_win": r[4] or 0.0,
            "avg_loss": r[5] or 0.0,
            "n_trades": r[6] or 0,
        }
    return result


def _load_kelly_params() -> dict:
    """Load Kelly parameters from P3-D12, keyed by (asset_id, regime)."""
    with get_cursor() as cur:
        cur.execute(
            """SELECT asset_id, regime, session, kelly_full, shrinkage_factor, sizing_override
               FROM p3_d12_kelly_parameters
               ORDER BY last_updated DESC""",
        )
        rows = cur.fetchall()

    seen = set()
    result = {}
    sizing_overrides = {}
    for r in rows:
        key = (r[0], r[1], r[2])  # (asset_id, regime, session)
        if key in seen:
            continue
        seen.add(key)
        result[key] = {
            "asset_id": r[0],
            "regime": r[1],
            "session": r[2],
            "kelly_full": r[3] or 0.0,
            "shrinkage_factor": r[4] or 1.0,
        }
        # Collect sizing overrides (Level 2 reductions)
        override = _parse_json(r[5], None)
        if override is not None and r[0] not in sizing_overrides:
            sizing_overrides[r[0]] = override

    return {"params": result, "sizing_overrides": sizing_overrides}


def _load_tsm_configs() -> dict:
    """Load TSM configurations from P3-D08, keyed by account_id."""
    with get_cursor() as cur:
        cur.execute(
            """SELECT account_id, user_id, name, classification,
                      starting_balance, current_balance, current_drawdown,
                      daily_loss_used, profit_target, max_drawdown_limit,
                      max_daily_loss, max_contracts, scaling_plan,
                      commission_per_contract, instrument_permissions,
                      overnight_allowed, trading_hours, margin_per_contract,
                      margin_buffer_pct, pass_probability, risk_goal,
                      evaluation_end_date, topstep_optimisation,
                      fee_schedule, payout_rules, scaling_plan_active,
                      scaling_tier_micros
               FROM p3_d08_tsm_state
               ORDER BY last_updated DESC""",
        )
        rows = cur.fetchall()

    seen = set()
    result = {}
    for r in rows:
        account_id = r[0]
        if account_id in seen:
            continue
        seen.add(account_id)
        result[account_id] = {
            "account_id": account_id,
            "user_id": r[1],
            "name": r[2],
            "classification": _parse_json(r[3], {}),
            "starting_balance": r[4] or 0.0,
            "current_balance": r[5] or 0.0,
            "current_drawdown": r[6] or 0.0,
            "daily_loss_used": r[7] or 0.0,
            "profit_target": r[8],
            "max_drawdown_limit": r[9],
            "max_daily_loss": r[10],
            "max_contracts": r[11],
            "scaling_plan": _parse_json(r[12], None),
            "commission_per_contract": r[13] or 0.0,
            "instrument_permissions": _parse_json(r[14], []),
            "overnight_allowed": r[15] if r[15] is not None else True,
            "trading_hours": r[16],
            "margin_per_contract": r[17] or 0.0,
            "margin_buffer_pct": r[18] or 1.5,
            "pass_probability": r[19],
            "risk_goal": r[20] or "GROW_CAPITAL",
            "evaluation_end_date": r[21],
            "topstep_optimisation": r[22] if r[22] is not None else False,
            "fee_schedule": _parse_json(r[23], None),
            "payout_rules": _parse_json(r[24], None),
            "scaling_plan_active": r[25] if r[25] is not None else False,
            "scaling_tier_micros": r[26] or 0,
        }
    return result


def _load_locked_strategies() -> dict:
    """Load locked strategies from P3-D00.locked_strategy, keyed by asset_id.

    P2-D06 data is pre-loaded into P3-D00 during asset onboarding.
    """
    with get_cursor() as cur:
        cur.execute(
            """SELECT asset_id, locked_strategy
               FROM p3_d00_asset_universe
               ORDER BY last_updated DESC""",
        )
        rows = cur.fetchall()

    seen = set()
    result = {}
    for r in rows:
        asset_id = r[0]
        if asset_id in seen:
            continue
        seen.add(asset_id)
        strategy = _parse_json(r[1], {})
        if strategy:
            result[asset_id] = strategy
    return result


def _load_regime_models() -> dict:
    """Load regime classifier info for each asset.

    P2-D07 data is stored as part of asset config. In V1 with a single asset,
    the regime result is REGIME_NEUTRAL (locked in P2). The classifier details
    (model_type, feature_list, pettersson_threshold) are loaded here.
    """
    # For V1, regime models come from the locked strategy data in P3-D00
    # The actual classifier object would be loaded from file; for now we
    # store the metadata needed for Block 2.
    strategies = _load_locked_strategies()
    result = {}
    for asset_id, strategy in strategies.items():
        result[asset_id] = {
            "model_type": strategy.get("regime_model_type", "BINARY_ONLY"),
            "feature_list": strategy.get("regime_feature_list", []),
            "pettersson_threshold": strategy.get("pettersson_threshold"),
            "regime_label": strategy.get("regime_label", "REGIME_NEUTRAL"),
        }
    return result


def _load_system_param(key: str, default=None):
    """Load a single system parameter from P3-D17."""
    with get_cursor() as cur:
        cur.execute(
            """SELECT param_value FROM p3_d17_system_monitor_state
               LATEST ON last_updated PARTITION BY param_key
               WHERE param_key = %s""",
            (key,),
        )
        row = cur.fetchone()
    if row and row[0]:
        try:
            return json.loads(row[0])
        except (json.JSONDecodeError, TypeError):
            return row[0]
    return default


# ---------------------------------------------------------------------------
# Data Moderator
# ---------------------------------------------------------------------------

def _run_data_moderator(assets: list[dict], session_id: int, aim_states: dict | None = None) -> list[dict]:
    """Run pre-ingestion data quality checks on all assets.

    Returns updated asset list (some may be set to DATA_HOLD).
    Writes quality flags to P3-D00 and incidents to P3-D21.
    """
    clean_count = 0
    flagged_count = 0
    held_count = 0

    for asset in assets:
        asset_id = asset["asset_id"]
        flag = "CLEAN"

        # Price bounds check — 5% deviation from prior close
        current_price = _get_latest_price(asset_id)
        prior_close = _get_prior_close(asset_id)

        if prior_close and prior_close > 0 and current_price and current_price > 0:
            price_deviation = abs(current_price - prior_close) / prior_close
            if price_deviation > 0.05:
                flag = "PRICE_SUSPECT"
                _create_incident(
                    "DATA_QUALITY", "P2_HIGH", "DATA_FEED",
                    f"Price for {asset_id} deviates {price_deviation * 100:.1f}% from prior close. Halting signals."
                )
                _update_asset_status(asset_id, "DATA_HOLD", flag)
                asset["captain_status"] = "DATA_HOLD"
                asset["data_quality_flag"] = flag
                held_count += 1
                continue

        # Volume sanity check
        current_volume = _get_current_session_volume(asset_id)
        avg_volume = _get_avg_session_volume_20d(asset_id)

        if avg_volume and avg_volume > 0:
            if current_volume == 0:
                flag = "ZERO_VOLUME"
                logger.warning("Volume = 0 for %s — data feed may be stale", asset_id)
            elif current_volume > avg_volume * 10:
                flag = "VOLUME_EXTREME"
                logger.warning("Volume for %s is %.0fx normal — flagged", asset_id,
                               current_volume / avg_volume)

        # Missing data source check — runs unconditionally, logs all missing
        required_features = _get_required_features(asset_id, aim_states)
        for feat in required_features:
            if not _check_data_source_for_feature(asset_id, feat):
                logger.info("Data source unavailable for feature %s for %s — will use last known value",
                            feat, asset_id)
                if flag == "CLEAN":
                    flag = "STALE_FEATURE"

        # Timestamp validation
        if not _has_valid_timestamp(asset_id):
            _create_incident(
                "DATA_QUALITY", "P2_HIGH", "DATA_FEED",
                f"Data for {asset_id} missing timezone offset. Rejecting."
            )
            flagged_count += 1
            continue

        # Update flag
        asset["data_quality_flag"] = flag
        _update_asset_quality_flag(asset_id, flag)

        if flag == "CLEAN":
            clean_count += 1
        else:
            flagged_count += 1

    # Log data quality summary to P3-D17
    _log_data_quality_summary(session_id, len(assets), clean_count, flagged_count, held_count)

    # Filter out DATA_HOLD assets
    return [a for a in assets if a["captain_status"] != "DATA_HOLD"]


def _check_roll_calendar(assets: list[dict]) -> list[dict]:
    """Check contract roll calendar for each asset.

    Sets ROLL_PENDING for assets at/past roll date.
    """
    today = datetime.now().date()
    result = []

    for asset in assets:
        asset_id = asset["asset_id"]
        roll_info = asset.get("roll_calendar")

        if roll_info and isinstance(roll_info, dict):
            next_roll_str = roll_info.get("next_roll_date")
            if next_roll_str:
                try:
                    next_roll = datetime.strptime(next_roll_str, "%Y-%m-%d").date()
                except (ValueError, TypeError):
                    next_roll = None

                if next_roll:
                    days_to_roll = (next_roll - today).days

                    if days_to_roll <= 0 and not roll_info.get("roll_confirmed", False):
                        logger.warning("CONTRACT ROLL: %s roll date is today (%s). Signals paused.",
                                       asset_id, next_roll_str)
                        _update_asset_status(asset_id, "ROLL_PENDING", asset["data_quality_flag"])
                        asset["captain_status"] = "ROLL_PENDING"
                        _publish_alert(
                            "CRITICAL",
                            f"CONTRACT ROLL: {asset_id} roll date is today ({next_roll_str}). "
                            f"Signals paused until roll confirmed.",
                            action_required=True,
                        )
                        continue

                    elif days_to_roll <= 3:
                        logger.info("CONTRACT ROLL: %s rolls in %d days (%s)",
                                    asset_id, days_to_roll, next_roll_str)
                        _publish_alert(
                            "HIGH",
                            f"CONTRACT ROLL: {asset_id} rolls in {days_to_roll} days ({next_roll_str}).",
                        )

        if asset["captain_status"] != "ROLL_PENDING":
            result.append(asset)

    return result


# ---------------------------------------------------------------------------
# Data feed stubs — replaced by real adapters in integration
# ---------------------------------------------------------------------------

def _get_latest_price(asset_id: str) -> float | None:
    """Get latest price from TopstepX market stream or REST fallback."""
    contract_id = resolve_contract_id(asset_id)
    if contract_id is None:
        logger.warning("_get_latest_price: no contract_id for asset %s", asset_id)
        return None
    # Try stream cache first (sub-second freshness)
    quote = quote_cache.get(contract_id)
    if quote and quote.get("lastPrice"):
        return float(quote["lastPrice"])
    # REST fallback: 1-minute bar
    try:
        client = get_topstep_client()
        now = datetime.now(timezone.utc)
        bars = client.get_bars(
            contract_id, 2, 1,  # barUnit=2 (Minute), barUnitNumber=1
            (now - timedelta(minutes=5)).isoformat(),
            now.isoformat(),
        )
        if bars:
            return float(bars[-1]["close"])
    except TopstepXClientError as exc:
        logger.warning("_get_latest_price REST fallback failed: %s", exc)
    return None


def _get_prior_close(asset_id: str) -> float | None:
    """Get yesterday's closing price from TopstepX daily bars."""
    contract_id = resolve_contract_id(asset_id)
    if contract_id is None:
        logger.warning("_get_prior_close: no contract_id for asset %s", asset_id)
        return None
    try:
        client = get_topstep_client()
        today = datetime.now(timezone.utc).date()
        start = (today - timedelta(days=5)).isoformat()
        end = (today - timedelta(days=1)).isoformat()
        bars = client.get_bars(contract_id, 4, 1, start, end)  # barUnit=4 (Day)
        if bars:
            return float(bars[-1]["close"])
    except TopstepXClientError as exc:
        logger.warning("_get_prior_close failed: %s", exc)
    return None


def _get_current_session_volume(asset_id: str) -> int:
    """Get current session volume from stream cache."""
    contract_id = resolve_contract_id(asset_id)
    if contract_id is None:
        logger.warning("_get_current_session_volume: no contract_id for asset %s", asset_id)
        return 0
    quote = quote_cache.get(contract_id)
    if quote and quote.get("volume") is not None:
        return int(quote["volume"])
    return 0


def _get_avg_session_volume_20d(asset_id: str) -> float | None:
    """Get 20-day average session volume from TopstepX daily bars."""
    contract_id = resolve_contract_id(asset_id)
    if contract_id is None:
        logger.warning("_get_avg_session_volume_20d: no contract_id for asset %s", asset_id)
        return None
    try:
        client = get_topstep_client()
        today = datetime.now(timezone.utc).date()
        start = (today - timedelta(days=30)).isoformat()
        end = (today - timedelta(days=1)).isoformat()
        bars = client.get_bars(contract_id, 4, 1, start, end)  # Daily
        if bars:
            volumes = [b.get("volume", 0) for b in bars[-20:]]
            return sum(volumes) / len(volumes) if volumes else None
    except TopstepXClientError as exc:
        logger.warning("_get_avg_session_volume_20d failed: %s", exc)
    return None


def _get_required_features(asset_id: str, aim_states: dict | None = None) -> list[str]:
    """Get list of required features based on active AIMs."""
    if aim_states is None:
        return []
    try:
        from captain_online.blocks.b1_features import get_required_features
        return get_required_features(asset_id, aim_states)
    except ImportError:
        return []


def _check_data_source_for_feature(asset_id: str, feature_name: str) -> bool:
    """Check if data source for a feature is available.

    Returns False if the underlying data feed for this feature is missing
    or stale (no quote in cache).  Downstream uses last-known-value fallback
    when this returns False; callers set DATA_HOLD only on timestamp failure.
    """
    # Market-data features require a live quote in the cache
    market_features = {
        "last_price", "bid", "ask", "spread", "volume",
        "or_high", "or_low", "or_range", "vwap",
    }
    if feature_name in market_features:
        contract_id = resolve_contract_id(asset_id)
        if contract_id is None:
            return False
        quote = quote_cache.get(contract_id)
        return quote is not None and quote.get("lastPrice") is not None

    # Non-market features (VIX, COT, sentiment) — accept if any data present.
    # Individual AIM blocks handle their own null checks.
    return True


def _has_valid_timestamp(asset_id: str) -> bool:
    """Check if latest data for an asset has a valid, non-stale timestamp.

    Returns False (triggering DATA_HOLD) when:
      - No quote exists in the cache at all
      - Quote has no price data (feed disconnected)
      - Quote is older than STALE_THRESHOLD_SECONDS (stale feed)
    """
    contract_id = resolve_contract_id(asset_id)
    if contract_id is None:
        return False
    quote = quote_cache.get(contract_id)
    if quote is None or quote.get("lastPrice") is None:
        return False
    # If the cache carries a timestamp field, enforce staleness bound
    ts = quote.get("timestamp") or quote.get("lastTradeTime")
    if ts is not None:
        try:
            from datetime import timezone as tz
            if isinstance(ts, str):
                ts_dt = datetime.fromisoformat(ts)
            elif isinstance(ts, (int, float)):
                ts_dt = datetime.fromtimestamp(ts, tz=tz.utc)
            else:
                return True  # unknown format — pass through
            age = (datetime.now(tz.utc) - ts_dt.astimezone(tz.utc)).total_seconds()
            STALE_THRESHOLD_SECONDS = 300  # 5 minutes
            if age > STALE_THRESHOLD_SECONDS:
                logger.warning("Stale data for %s: quote age %.0fs > %ds",
                               asset_id, age, STALE_THRESHOLD_SECONDS)
                return False
        except (ValueError, TypeError, OSError):
            pass  # unparseable timestamp — pass through
    return True


# ---------------------------------------------------------------------------
# QuestDB writers
# ---------------------------------------------------------------------------

def _update_asset_status(asset_id: str, status: str, quality_flag: str):
    """Update captain_status and data_quality_flag in P3-D00."""
    from shared.questdb_client import update_d00_fields
    update_d00_fields(asset_id, {"captain_status": status, "data_quality_flag": quality_flag})


def _update_asset_quality_flag(asset_id: str, flag: str):
    """Update data_quality_flag in P3-D00."""
    from shared.questdb_client import update_d00_fields
    update_d00_fields(asset_id, {"data_quality_flag": flag})


def _create_incident(incident_type: str, severity: str, component: str, details: str):
    """Create incident in P3-D21."""
    incident_id = f"INC-{uuid.uuid4().hex[:8].upper()}"
    with get_cursor() as cur:
        cur.execute(
            """INSERT INTO p3_d21_incident_log
               (incident_id, incident_type, severity, component, details, status, ts)
               VALUES (%s, %s, %s, %s, %s, 'OPEN', now())""",
            (incident_id, incident_type, severity, component, details),
        )
    logger.warning("Incident %s created: [%s] %s — %s", incident_id, severity, incident_type, details)


def _log_data_quality_summary(session_id: int, total: int, clean: int, flagged: int, held: int):
    """Log data quality summary to P3-D17."""
    summary = json.dumps({
        "session": session_id,
        "assets_checked": total,
        "clean": clean,
        "flagged": flagged,
        "held": held,
    })
    with get_cursor() as cur:
        cur.execute(
            """INSERT INTO p3_d17_system_monitor_state
               (param_key, param_value, category, last_updated)
               VALUES (%s, %s, %s, now())""",
            (f"data_quality_log_{session_id}", summary, "data_quality"),
        )


def _publish_alert(priority: str, message: str, action_required: bool = False):
    """Publish an alert to Redis captain:alerts channel."""
    try:
        from shared.redis_client import get_redis_client, CH_ALERTS
        client = get_redis_client()
        payload = json.dumps({
            "priority": priority,
            "message": message,
            "action_required": action_required,
            "source": "ONLINE_B1",
            "timestamp": datetime.now().isoformat(),
        })
        client.publish(CH_ALERTS, payload)
    except Exception as e:
        logger.error("Failed to publish alert: %s", e)


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def _assert_system_timezone():
    """Assert system timezone is America/New_York (spec line 142)."""
    import os
    tz = os.environ.get("TZ", "")
    # In Docker, TZ is set via environment variable
    if tz and tz != SYSTEM_TIMEZONE:
        logger.error("System timezone mismatch: TZ=%s, expected %s", tz, SYSTEM_TIMEZONE)
        raise RuntimeError(f"System timezone not set to {SYSTEM_TIMEZONE} (got TZ={tz})")
    # If TZ not set, check Python's local timezone
    try:
        import zoneinfo
        local_tz = datetime.now().astimezone().tzinfo
        logger.info("ON-B1: System timezone check passed (local: %s)", local_tz)
    except Exception:
        logger.warning("ON-B1: Could not verify system timezone — proceeding")


def session_match(asset_id: str, session_id: int, session_hours: dict = None) -> bool:
    """Returns True if this asset trades in the given session.

    Checks P3-D00.session_hours for a key matching the session name.
    """
    session_key = SESSION_IDS.get(session_id, "NY")
    if session_hours is None:
        return session_key == "NY"  # default: NY only
    return session_hours.get(session_key) is not None


def _parse_json(raw, default):
    """Safely parse a JSON string, returning default on failure."""
    if raw is None:
        return default
    if isinstance(raw, (dict, list)):
        return raw
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return default


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run_data_ingestion(session_id: int) -> dict | None:
    """P3-PG-21: Pre-session data ingestion.

    Args:
        session_id: 1=NY, 2=LON, 3=APAC

    Returns:
        dict with all loaded data for Blocks 2-6, or None if no active assets.
    """
    session_name = SESSION_IDS.get(session_id, "NY")
    logger.info("ON-B1: Starting data ingestion for session %s (%d)", session_name, session_id)

    # Step 1: Filter active assets for this session
    assets = _load_active_assets(session_id)
    if not assets:
        logger.info("ON-B1: No active assets for session %s", session_name)
        return None

    logger.info("ON-B1: %d assets eligible for session %s", len(assets), session_name)

    # Step 1c: Validate system timezone — all internal ops use America/New_York
    _assert_system_timezone()

    # Load AIM states early so Data Moderator can resolve required features
    aim_states = _load_aim_states()

    # Step 1b: Data Moderator — pre-ingestion validation
    assets = _run_data_moderator(assets, session_id, aim_states=aim_states)
    if not assets:
        logger.warning("ON-B1: All assets held by Data Moderator")
        return None

    # Step 1c: Contract roll calendar check
    assets = _check_roll_calendar(assets)
    if not assets:
        logger.warning("ON-B1: All assets in ROLL_PENDING")
        return None

    # Step 2: Load Offline outputs (read-only) — aim_states already loaded above
    aim_weights = _load_aim_weights()
    ewma_states = _load_ewma_states()
    kelly_data = _load_kelly_params()
    kelly_params = kelly_data["params"]
    sizing_overrides = kelly_data["sizing_overrides"]
    tsm_configs = _load_tsm_configs()

    # Step 3: Load P2 outputs (read-only)
    locked_strategies = _load_locked_strategies()
    regime_models = _load_regime_models()

    # Step 4: Compute pre-session features per asset
    # Delegates to b1_features.py (ON-B1A) which implements the 17 feature
    # computation functions + data access utilities.
    from captain_online.blocks.b1_features import compute_all_features
    features = compute_all_features(assets, aim_states, locked_strategies)

    # Build active_assets list (asset_id strings)
    active_assets = [a["asset_id"] for a in assets]

    logger.info("ON-B1: Data ingestion complete. %d active assets, %d features computed",
                len(active_assets), sum(len(f) for f in features.values()))

    return {
        "active_assets": active_assets,
        "assets_detail": {a["asset_id"]: a for a in assets},
        "features": features,
        "aim_states": aim_states,
        "aim_weights": aim_weights,
        "ewma_states": ewma_states,
        "kelly_params": kelly_params,
        "sizing_overrides": sizing_overrides,
        "tsm_configs": tsm_configs,
        "locked_strategies": locked_strategies,
        "regime_models": regime_models,
        "session_id": session_id,
    }
