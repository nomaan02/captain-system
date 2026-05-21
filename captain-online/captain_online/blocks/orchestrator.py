# region imports
try:
    from AlgorithmImports import *
except ImportError:
    pass
# endregion
"""Captain Online Orchestrator — P3-PG-20 (Task 3.11a / ON lines 1349-1430).

Session loop: runs 24/7, evaluates at session opens (NY, LON, APAC).

Flow per session:
  1. Circuit breaker check (DATA_HOLD >= 3 OR VIX > threshold OR manual_halt)
  2. SHARED: B1 (ingestion) → B2 (regime) → B3 (AIM aggregation)
  3. PER-USER LOOP: B4 (Kelly) → B5 (selection) → B5B (quality) → B5C (CB) → B6 (signal)
  4. POST-LOOP: B8 (concentration) → B9 (capacity)
  5. CONTINUOUS: B7 (position monitoring) while any position open

Session schedule:
  NY:   09:30 America/New_York
  LON:  08:00 (≈03:00 EST)
  APAC: per asset config

Subscribes to Redis: captain:commands (for manual halt, pause, etc.)
"""

import json
import logging
import os
import threading
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from shared.redis_client import (
    get_redis_client,
    ensure_consumer_group, read_stream, ack_message, publish_to_stream,
    STREAM_COMMANDS, GROUP_ONLINE_COMMANDS,
    CH_STATUS, CH_ALERTS, REDIS_KEY_QUOTES,
)
from shared.journal import write_checkpoint
from shared.constants import SESSION_IDS, SYSTEM_TIMEZONE, now_et
from shared.process_logger import ProcessLogger
from captain_online.blocks.b9_session_controller import (
    get_session_open_times,
    is_session_opening as _sc_is_session_opening,
)

_ET = ZoneInfo(SYSTEM_TIMEZONE)

logger = logging.getLogger(__name__)

REDIS_KEY_OPEN_POSITIONS = "captain:open_positions"

# Session open times — loaded from session_registry.json via B9 session controller.
SESSION_OPEN_TIMES = get_session_open_times()


class OnlineOrchestrator:
    """Event loop for Captain Online process."""

    def __init__(self, or_tracker=None):
        self.running = False
        self.open_positions = []  # Active positions across all users
        self.shadow_positions = []  # Shadow positions for theoretical outcome tracking
        self._position_lock = threading.Lock()  # Guards open_positions + shadow_positions
        self._session_evaluated_today = {}  # {session_id: date} — prevent double-eval
        self._all_signals = []  # Collect signals for B8 concentration
        self._or_tracker = or_tracker
        self.plog = ProcessLogger("ONLINE", get_redis_client())
        # Pending Phase A results awaiting OR breakout for Phase B (B6)
        # {session_id: {"data", "regime", "aim", "user_results", "resolved_assets"}}
        self._pending_sessions = {}
        self._last_heartbeat_time = 0
        self._last_monitor_time = 0  # Throttle B7 to 10s intervals per spec

    def start(self):
        """Start the orchestrator."""
        self.running = True
        logger.info("Online orchestrator starting...")
        write_checkpoint("ONLINE", "ORCHESTRATOR_START", "init", "session_loop")
        self._publish_pipeline_stage("WAITING")

        self._reconcile_positions_from_redis()

        # Redis command listener in background
        thread = threading.Thread(target=self._command_listener, daemon=True)
        thread.start()

        # Main loop
        self._session_loop()

    def stop(self):
        self.running = False
        logger.info("Online orchestrator stopping...")

    def _reconcile_positions_from_redis(self):
        try:
            client = get_redis_client()
            stored = client.hgetall(REDIS_KEY_OPEN_POSITIONS)
            if not stored:
                logger.info("Position reconciliation: no positions found in Redis")
                return
            recovered = 0
            with self._position_lock:
                for sig_id, raw in stored.items():
                    key = sig_id if isinstance(sig_id, str) else sig_id.decode()
                    val = raw if isinstance(raw, str) else raw.decode()
                    try:
                        pos = json.loads(val)
                        if pos.get("entry_time") and isinstance(pos["entry_time"], str):
                            pos["entry_time"] = datetime.fromisoformat(pos["entry_time"])
                        d = pos.get("direction", 1)
                        pos["direction"] = 1 if d in (1, "BUY") else -1 if d in (-1, "SELL") else int(d or 1)
                        for _f in ("entry_price", "tp_level", "sl_level", "point_value", "risk_amount", "contracts"):
                            if pos.get(_f) is not None:
                                pos[_f] = float(pos[_f]) if _f != "contracts" else int(pos[_f])
                        self.open_positions.append(pos)
                        recovered += 1
                    except (json.JSONDecodeError, ValueError) as exc:
                        logger.warning("Skipping corrupt position %s: %s", key, exc)
            if recovered > 0:
                logger.warning("POSITION RECONCILIATION: recovered %d position(s) from Redis after restart", recovered)
        except Exception as exc:
            logger.error("Position reconciliation failed: %s", exc)

    def _publish_pipeline_stage(self, stage: str):
        """Publish pipeline stage transition to Redis for GUI relay."""
        try:
            client = get_redis_client()
            client.publish(CH_STATUS, json.dumps({
                "role": "ONLINE",
                "type": "pipeline_stage",
                "stage": stage,
                "timestamp": datetime.now(_ET).isoformat(),
            }))
        except Exception as e:
            logger.error("Failed to publish pipeline stage %s: %s", stage, e)

    def _publish_heartbeat(self):
        """Publish Online process heartbeat to Redis."""
        try:
            client = get_redis_client()
            client.publish(CH_STATUS, json.dumps({
                "role": "ONLINE",
                "status": "ok",
                "timestamp": now_et().isoformat(),
                "details": {
                    "open_positions": len(self.open_positions),
                    "shadow_positions": len(self.shadow_positions),
                    "pending_sessions": len(self._pending_sessions),
                },
            }))
        except Exception as exc:
            logger.error("Heartbeat publish failed: %s", exc)

    def _session_loop(self):
        """Main 24/7 loop — check sessions, monitor positions, resolve OR."""
        while self.running:
            now = datetime.now(_ET)

            for session_id, (hour, minute) in SESSION_OPEN_TIMES.items():
                if self._is_session_opening(now, session_id, hour, minute):
                    self._run_session(session_id)

            # OR breakout check — run Phase B (B6) for resolved assets
            if self._pending_sessions and self._or_tracker:
                try:
                    self._check_or_breakouts()
                except Exception as e:
                    logger.error("OR breakout check error: %s", e, exc_info=True)

            # Continuous: B7 position monitoring (10s poll per spec)
            if self.open_positions:
                _now_mono = time.monotonic()
                if _now_mono - self._last_monitor_time >= 10:
                    self._last_monitor_time = _now_mono
                    try:
                        self._run_position_monitor()
                    except Exception as e:
                        logger.error("Position monitor error: %s", e, exc_info=True)

            # Continuous: Shadow position monitoring (theoretical outcomes)
            if self.shadow_positions:
                try:
                    self._run_shadow_monitor()
                except Exception as e:
                    logger.error("Shadow monitor error: %s", e, exc_info=True)

            # Publish live quotes to Redis for captain-command GUI
            self._publish_quotes_to_redis()

            # Heartbeat every 30s
            current_time = time.monotonic()
            if current_time - self._last_heartbeat_time >= 30:
                self._publish_heartbeat()
                self._last_heartbeat_time = current_time

            time.sleep(1)

    def _publish_quotes_to_redis(self):
        """Publish quote_cache snapshot to Redis for captain-command GUI."""
        from shared.topstep_stream import quote_cache
        from shared.contract_resolver import get_asset_for_contract
        try:
            all_quotes = quote_cache.all()
            if not all_quotes:
                return
            r = get_redis_client()
            pipe = r.pipeline(transaction=False)
            for contract_id, quote in all_quotes.items():
                asset = get_asset_for_contract(contract_id)
                if not asset:
                    continue
                pipe.hset(REDIS_KEY_QUOTES, asset, json.dumps({
                    "last_price": quote.get("lastPrice"),
                    "best_bid": quote.get("bestBid"),
                    "best_ask": quote.get("bestAsk"),
                    "change": quote.get("change"),
                    "change_pct": quote.get("changePercent"),
                    "open": quote.get("open"),
                    "high": quote.get("high"),
                    "low": quote.get("low"),
                    "volume": quote.get("volume"),
                    "timestamp": quote.get("timestamp"),
                }, default=str))
            pipe.expire(REDIS_KEY_QUOTES, 10)
            pipe.execute()
        except Exception:
            pass  # Non-critical — don't log every second

    def _is_session_opening(self, now: datetime, session_id: int, hour: int, minute: int) -> bool:
        """Check if we're within the session open window and haven't evaluated today."""
        today = now.date()
        if self._session_evaluated_today.get(session_id) == today:
            return False

        return _sc_is_session_opening(now, session_id, hour, minute)

    def _run_session(self, session_id: int):
        """Execute session evaluation pipeline.

        With OR tracker: Phase A (B1-B5C) runs now; Phase B (B6) deferred
        until OR breakout is detected in _check_or_breakouts().
        Without OR tracker: runs full B1-B6 immediately (legacy/test path).
        """
        session_name = SESSION_IDS.get(session_id, "UNKNOWN")
        logger.info("Session %s (%d) opening — beginning evaluation", session_name, session_id)
        self.plog.info(f"Session {session_name} opening \u2014 beginning evaluation", source="orchestrator")
        write_checkpoint("ONLINE", f"SESSION_{session_name}", "start", "circuit_breaker")

        # Circuit breaker check
        if not self._circuit_breaker_check(session_id):
            logger.warning("Session %s HALTED by circuit breaker", session_name)
            self._session_evaluated_today[session_id] = datetime.now(_ET).date()
            return

        # ──── PER-SESSION BUDGET INITIALISATION ────
        # Compute and persist this session's effective_l_halt and
        # effective_e_exposure for every active account, applying
        # carryover from any earlier sessions today (parity-skip support).
        # Idempotent — safe to call multiple times same day.
        try:
            self._initialize_session_budget(session_id)
        except Exception as exc:
            logger.error(
                "ON-Orch: session-budget init failed for session %s: %s "
                "— B5C will fall back to legacy single-budget for this session",
                session_name, exc, exc_info=True,
            )

        # ──── EARLY OR REGISTRATION (before Phase A) ────
        # Register active assets with the OR tracker NOW so ticks from
        # session open are captured. Phase A (B1-B5C) takes ~1-2 min;
        # without early registration those ticks would be lost.
        if self._or_tracker:
            try:
                from shared.questdb_client import get_cursor as _gc
                with _gc() as _cur:
                    _cur.execute(
                        """SELECT asset_id FROM p3_d00_asset_universe
                           WHERE captain_status = 'ACTIVE'
                           ORDER BY last_updated DESC"""
                    )
                    _rows = _cur.fetchall()
                _seen = set()
                for _r in _rows:
                    if _r[0] not in _seen:
                        _seen.add(_r[0])
                        self._or_tracker.register_asset(_r[0])
                if _seen:
                    logger.info("OR tracker: %d assets registered at session open", len(_seen))
                    self._publish_pipeline_stage("OR_FORMING")
            except Exception as e:
                logger.error("Early OR registration failed: %s — will retry after Phase A", e)

        try:
            # ──── SHARED INTELLIGENCE (once per session) ────
            from captain_online.blocks.b1_data_ingestion import run_data_ingestion
            data = run_data_ingestion(session_id)
            if data is None:
                logger.info("Session %s: no active assets — skipping", session_name)
                self.plog.info(f"Session {session_name}: no active assets \u2014 skipping", source="b1_data")
                self._session_evaluated_today[session_id] = datetime.now(_ET).date()
                return

            n_assets = len(data.get("active_assets", []))
            self.plog.info(f"B1: Data ingestion \u2014 {n_assets} assets", source="b1_data")

            from captain_online.blocks.b2_regime_probability import run_regime_probability
            regime = run_regime_probability(
                data["active_assets"], data["features"], data["regime_models"]
            )
            self.plog.info(f"B2: Regime probability \u2014 {n_assets} assets classified", source="b2_regime")

            # Update B7 regime cache so position monitor can detect regime shifts
            from captain_online.blocks.b7_position_monitor import update_regime_cache
            update_regime_cache(regime.get("regime_probs"))

            from shared.aim_compute import run_aim_aggregation
            aim = run_aim_aggregation(
                data["active_assets"], data["features"],
                data["aim_states"], data["aim_weights"]
            )
            self.plog.info(f"B3: AIM aggregation \u2014 {n_assets} assets scored", source="b3_aim")

            try:
                from captain_online.blocks.hmm_inference_block import persist_online_hmm_inference

                persist_online_hmm_inference(session_id, data["active_assets"])
            except Exception as hmm_exc:
                logger.warning("[aim16-online] inference persist skipped: %s", hmm_exc)

            write_checkpoint("ONLINE", f"SESSION_{session_name}", "shared_done", "per_user_loop")

            # ──── PER-USER SIZING LOOP (B4-B5C) ────
            active_users = self._get_active_users()
            self._all_signals = []

            user_results = []
            for user in active_users:
                user_silo = self._load_user_silo(user["user_id"])
                if user_silo is None:
                    logger.warning("No capital silo for user %s — skipping", user["user_id"])
                    continue

                if self._or_tracker:
                    # Phase A only: B4-B5C, defer B6 until OR resolves
                    result = self._process_user_sizing(
                        session_id, data, regime, aim, user_silo
                    )
                    if result is not None:
                        user_results.append(result)
                else:
                    # Legacy path: full B4-B6 immediately
                    self._process_user(
                        session_id, data, regime, aim, user_silo
                    )

            # ──── OR TRACKER: store Phase A results (assets already registered early) ────
            if self._or_tracker and user_results:
                # Register any assets that weren't caught by early registration
                # (e.g. if early query failed or new assets appeared during Phase A).
                # register_asset() overwrites, so only register MISSING ones.
                for asset in data["active_assets"]:
                    if self._or_tracker.get_state(asset) is None:
                        self._or_tracker.register_asset(asset)

                self._pending_sessions[session_id] = {
                    "session_name": session_name,
                    "data": data,
                    "regime": regime,
                    "aim": aim,
                    "user_results": user_results,
                    "active_users": active_users,
                    "resolved_assets": set(),
                }
                logger.info("Phase A complete for %s — %d assets tracked, "
                            "%d user(s) pending Phase B",
                            session_name, len(data["active_assets"]), len(user_results))
                self.plog.info(
                    f"Phase A complete \u2014 {len(data['active_assets'])} assets registered for OR tracking",
                    source="orchestrator",
                )
                # Don't run B8/B9 yet — defer until Phase B completes
                self._publish_pipeline_stage("OR_FORMING")
                self._session_evaluated_today[session_id] = datetime.now(_ET).date()
                return

            # ──── POST-LOOP (legacy path without OR tracker) ────
            if len(active_users) > 1:
                from captain_online.blocks.b8_concentration_monitor import run_concentration_monitor
                run_concentration_monitor(session_id, active_users, self._all_signals)

            from captain_online.blocks.b9_capacity_evaluation import run_capacity_evaluation
            run_capacity_evaluation(session_id, active_users, data["active_assets"])

            logger.info("Session %s evaluation complete for %d user(s)",
                        session_name, len(active_users))

            # PG-01C dispatch (B1_F-01 / Q-03 2026-04-27): publish SESSION_CLOSE on
            # STREAM_COMMANDS so Offline can run AIM-16 HMM training globally at
            # each session close. Timezone is America/New_York per CLAUDE.md.
            try:
                publish_to_stream(STREAM_COMMANDS, {
                    "type": "SESSION_CLOSE",
                    "session_id": int(session_id),
                    "closed_at": datetime.now(_ET).isoformat(),
                    "source": "captain-online.orchestrator._run_session",
                })
                self.plog.info(
                    f"[session_close] published SESSION_CLOSE session_id={session_id}",
                    source="orchestrator",
                )
            except Exception as exc:
                logger.error("SESSION_CLOSE publish failed for session_id=%s: %s",
                             session_id, exc)

        except Exception as e:
            logger.error("Session %s evaluation FAILED: %s", session_name, e, exc_info=True)
            write_checkpoint("ONLINE", f"SESSION_{session_name}", "error", "retry_next",
                             {"error": str(e)})

        self._session_evaluated_today[session_id] = datetime.now(_ET).date()

    def _check_or_breakouts(self):
        """Check OR states and run Phase B (B6) for newly resolved assets.

        Called every ~1s from _session_loop. For each pending session, checks
        which assets have breakout or expiry, injects OR data into features,
        and runs B6 for those assets only.
        """
        from captain_online.blocks.b8_or_tracker import ORState

        self._or_tracker.check_expirations()

        completed_sessions = []

        for session_id, pending in self._pending_sessions.items():
            data = pending["data"]
            regime = pending["regime"]
            aim = pending["aim"]
            all_assets = set(data["active_assets"])
            resolved = pending["resolved_assets"]

            newly_resolved = []

            for asset in all_assets - resolved:
                state = self._or_tracker.get_state(asset)
                if state is None or not state.is_resolved:
                    continue

                resolved.add(asset)

                if state.state == ORState.EXPIRED:
                    logger.info("OR expired for %s — no signal generated", asset)
                    continue

                # Inject OR data into features for this asset
                if asset not in data["features"]:
                    data["features"][asset] = {}
                data["features"][asset]["or_range"] = state.or_range
                data["features"][asset]["entry_price"] = state.entry_price
                data["features"][asset]["or_direction"] = state.direction

                # AIM-15 Phase B: recompute volume ratio with actual first-m-min data
                self._recompute_aim15_volume(asset, data, aim)

                # Persist today's daily OHLCV for feature baselines (P3-D30)
                try:
                    from captain_online.blocks.b1_features import store_daily_ohlcv
                    store_daily_ohlcv(asset)
                except Exception as e:
                    logger.debug("Daily OHLCV store skipped for %s: %s", asset, e)

                # Persist today's 5-min opening volatility for AIM-12 (P3-D33)
                try:
                    from captain_online.blocks.b1_features import store_opening_volatility
                    store_opening_volatility(asset)
                except Exception as e:
                    logger.debug("Opening vol store skipped for %s: %s", asset, e)

                newly_resolved.append(asset)

            # Run Phase B (B6) for newly resolved breakout assets
            if newly_resolved:
                self._publish_pipeline_stage("SIGNAL_GEN")
                for asset in newly_resolved:
                    state = self._or_tracker.get_state(asset)
                    direction = state.direction if state else "?"
                    self.plog.info(
                        f"BREAKOUT {direction}: {asset} (OR resolved)",
                        source="or_tracker",
                    )
                if not pending["user_results"]:
                    logger.warning(
                        "ON-B6-SKIP session=%s newly_resolved=%s — pending.user_results is empty, "
                        "B6 not invoked", session_id, newly_resolved,
                    )
                for ur in pending["user_results"]:
                    signals = self._run_b6_for_user(
                        session_id, data, regime, aim, ur,
                        assets=newly_resolved,
                    )
                    self._all_signals.extend(signals)
                    for sig in signals:
                        self.plog.info(
                            f"B6: Signal \u2014 {sig.get('asset')} {sig.get('direction')} "
                            f"@ {sig.get('entry_price')} ({sig.get('size', '?')} cts, "
                            f"conf={sig.get('quality_score', '?')})",
                            source="b6_signal",
                        )
                logger.info("Phase B: generated signals for %s", newly_resolved)
                self._publish_pipeline_stage("EXECUTED")

            # Session complete when all assets resolved
            if resolved >= all_assets:
                session_name = pending["session_name"]
                active_users = pending["active_users"]

                # Run post-loop blocks (B8, B9)
                if len(active_users) > 1:
                    from captain_online.blocks.b8_concentration_monitor import run_concentration_monitor
                    run_concentration_monitor(session_id, active_users, self._all_signals)

                from captain_online.blocks.b9_capacity_evaluation import run_capacity_evaluation
                run_capacity_evaluation(session_id, active_users, data["active_assets"])

                logger.info("Session %s Phase B complete — all assets resolved", session_name)
                write_checkpoint("ONLINE", f"SESSION_{session_name}", "phase_b_done", "monitoring")
                completed_sessions.append(session_id)

                # PG-01C dispatch (B1_F-01 / Q-03 2026-04-27): publish SESSION_CLOSE
                # at OR-resolved completion path (parity with legacy path).
                try:
                    publish_to_stream(STREAM_COMMANDS, {
                        "type": "SESSION_CLOSE",
                        "session_id": int(session_id),
                        "closed_at": datetime.now(_ET).isoformat(),
                        "source": "captain-online.orchestrator._check_or_breakouts",
                    })
                except Exception as exc:
                    logger.error("SESSION_CLOSE publish (OR path) failed for session_id=%s: %s",
                                 session_id, exc)

        for sid in completed_sessions:
            self._pending_sessions.pop(sid, None)

        if completed_sessions:
            self._publish_pipeline_stage("WAITING")

    def _recompute_aim15_volume(self, asset: str, data: dict, aim: dict):
        """AIM-15 Phase B: recompute volume ratio after OR close.

        At OR close, first-m-minute volume is now available. Fetch it,
        compare to 20-day historical average from P3-D29, update
        the combined modifier, and store today's volume for future use.
        """
        try:
            from captain_online.blocks.b1_features import (
                volume_first_N_min, _get_historical_volume_first_N_min,
                get_or_window_minutes, store_opening_volume,
            )
            from shared.aim_compute import (
                _aim15_volume, MODIFIER_FLOOR, MODIFIER_CEILING, _clamp,
            )
            from captain_online.blocks.b8_or_tracker import get_asset_session_type

            # Get OR window minutes from locked strategy
            locked = data.get("locked_strategies", {}).get(asset, {})
            or_min = get_or_window_minutes(locked)

            # Fetch today's first-m-minute volume
            vol_now = volume_first_N_min(asset, or_min)
            if vol_now is None or vol_now <= 0:
                return  # no data yet — keep Phase A neutral

            # Store today's volume + OR range for future AIM-15 reference and
            # for B4/B5C Kelly SL distance derivation (Phase 2 — F-04).
            # `or_range` is the high-low across the OR window; injected into
            # features at orchestrator.py line 418 from b8_or_tracker state.
            session_type = get_asset_session_type(asset)
            or_range_val = data.get("features", {}).get(asset, {}).get("or_range")
            store_opening_volume(asset, session_type, or_min, vol_now,
                                 or_range=or_range_val)

            # Get historical average from P3-D29
            hist_vols = _get_historical_volume_first_N_min(asset, or_min, lookback=20)
            if not hist_vols or len(hist_vols) < 5:
                return  # insufficient baseline

            vol_avg = sum(hist_vols) / len(hist_vols)
            if vol_avg <= 0:
                return

            volume_ratio = vol_now / vol_avg

            # Update feature and recompute AIM-15
            if asset in data["features"]:
                data["features"][asset]["opening_volume_ratio"] = volume_ratio

            result = _aim15_volume({"opening_volume_ratio": volume_ratio}, {})
            new_mod = result["modifier"]

            # Update combined modifier: replace old AIM-15 (was 1.0 from VOLUME_MISSING)
            # with the real value. Since Phase A had AIM-15=1.0, divide out 1.0 and multiply new.
            if asset in aim.get("combined_modifier", {}):
                old_combined = aim["combined_modifier"][asset]
                updated = _clamp(old_combined * new_mod, MODIFIER_FLOOR, MODIFIER_CEILING)
                aim["combined_modifier"][asset] = updated
                logger.info("AIM-15 Phase B for %s: vol_ratio=%.2f, mod=%.2f, "
                            "combined %.3f→%.3f", asset, volume_ratio, new_mod,
                            old_combined, updated)
        except Exception as e:
            logger.warning("AIM-15 Phase B recompute failed for %s: %s", asset, e)

    def _process_user_sizing(self, session_id: int, data: dict, regime: dict,
                             aim: dict, user_silo: dict) -> dict | None:
        """Run B4→B5→B5B→B5C for one user (Phase A — sizing/selection).

        Returns intermediate results dict for Phase B, or None if blocked.
        """
        user_id = user_silo.get("user_id", "unknown")
        accounts = user_silo.get("accounts", [])
        if isinstance(accounts, str):
            try:
                accounts = json.loads(accounts)
            except (json.JSONDecodeError, TypeError):
                accounts = []

        try:
            from captain_online.blocks.b4_kelly_sizing import run_kelly_sizing
            sizing = run_kelly_sizing(
                active_assets=data["active_assets"],
                regime_probs=regime["regime_probs"],
                regime_uncertain=regime["regime_uncertain"],
                combined_modifier=aim["combined_modifier"],
                kelly_params=data["kelly_params"],
                ewma_states=data["ewma_states"],
                tsm_configs=data["tsm_configs"],
                sizing_overrides=data["sizing_overrides"],
                user_silo=user_silo,
                locked_strategies=data["locked_strategies"],
                assets_detail=data["assets_detail"],
                session_id=session_id,
            )

            if sizing is None or sizing.get("silo_blocked"):
                return None

            from captain_online.blocks.b5_trade_selection import run_trade_selection, apply_hmm_session_allocation
            trades = run_trade_selection(
                active_assets=data["active_assets"],
                final_contracts=sizing["final_contracts"],
                account_recommendation=sizing["account_recommendation"],
                account_skip_reason=sizing["account_skip_reason"],
                ewma_states=data["ewma_states"],
                regime_probs=regime["regime_probs"],
                user_silo=user_silo,
                session_id=session_id,
            )

            # V3: HMM session allocation
            trades["final_contracts"] = apply_hmm_session_allocation(
                trades["selected_trades"], trades["final_contracts"],
                accounts, session_id,
            )

            from captain_online.blocks.b5b_quality_gate import run_quality_gate
            quality = run_quality_gate(
                selected_trades=trades["selected_trades"],
                expected_edge=trades["expected_edge"],
                combined_modifier=aim["combined_modifier"],
                regime_probs=regime["regime_probs"],
                user_silo=user_silo,
                session_id=session_id,
                final_contracts=trades["final_contracts"],
                account_recommendation=trades["account_recommendation"],
            )

            # V3: Circuit breaker screen (after quality gate, before signal output)
            from captain_online.blocks.b5c_circuit_breaker import run_circuit_breaker_screen
            cb_result = run_circuit_breaker_screen(
                recommended_trades=quality["recommended_trades"],
                final_contracts=trades["final_contracts"],
                account_recommendation=trades["account_recommendation"],
                account_skip_reason=trades["account_skip_reason"],
                accounts=accounts,
                tsm_configs=data["tsm_configs"],
                session_id=session_id,
                proposed_contracts=trades["final_contracts"],
                locked_strategies=data["locked_strategies"],
                assets_detail=data["assets_detail"],
                open_positions=self.open_positions,
            )

            rec_count = len(cb_result["recommended_trades"])
            below_count = len(quality["available_not_recommended"])
            logger.info("Phase A — user %s: %d recommended, %d below threshold",
                        user_id, rec_count, below_count)

            # Invariant I-3 guard: if Phase A produces zero recommendations for
            # an active session, emit a CRITICAL alert so the failure is visible
            # immediately rather than showing up as silent ON-B6-SKIP warnings.
            if rec_count == 0 and len(data.get("active_assets", [])) > 0:
                try:
                    reasons = {
                        a: next(iter(v.values()), "UNKNOWN") if v else "UNKNOWN"
                        for a, v in cb_result.get("account_skip_reason", {}).items()
                    }
                    get_redis_client().publish(CH_ALERTS, json.dumps({
                        "type": "ZERO_RECOMMEND_SESSION",
                        "priority": "CRITICAL",
                        "user_id": user_id,
                        "session_id": session_id,
                        "active_assets": data.get("active_assets", []),
                        "reasons": reasons,
                        "timestamp": now_et().isoformat(),
                    }))
                    logger.warning(
                        "ON-OrchA-ZERO-RECOMMEND user=%s session=%s active=%d "
                        "reasons=%s — CRITICAL alert published",
                        user_id, session_id,
                        len(data.get("active_assets", [])), reasons,
                    )
                except Exception as _alert_exc:
                    logger.error(
                        "Failed to publish ZERO_RECOMMEND_SESSION alert: %s", _alert_exc,
                    )

            return {
                "user_silo": user_silo,
                "cb_result": cb_result,
                "quality": quality,
                "trades": trades,
            }

        except Exception as e:
            logger.error("User %s sizing FAILED: %s", user_id, e, exc_info=True)
            return None

    def _run_b6_for_user(self, session_id: int, data: dict, regime: dict,
                         aim: dict, user_result: dict,
                         assets: list[str] | None = None) -> list[dict]:
        """Run B6 signal output for one user (Phase B).

        If *assets* is provided, only generate signals for those assets
        (filtering recommended_trades to the resolved subset).
        """
        cb_result = user_result["cb_result"]
        quality = user_result["quality"]
        trades = user_result["trades"]
        user_silo = user_result["user_silo"]

        user_id = user_silo.get("user_id", "unknown")
        recommended_full = list(cb_result["recommended_trades"])
        recommended = list(recommended_full)
        if assets is not None:
            recommended = [a for a in recommended if a in assets]

        if not recommended:
            logger.warning(
                "ON-B6-SKIP user=%s session=%s assets_filter=%s recommended_trades=%s "
                "account_skip_reason=%s — B6 short-circuited (no candidates)",
                user_id, session_id, assets, recommended_full,
                cb_result.get("account_skip_reason"),
            )
            return []

        try:
            from captain_online.blocks.b6_signal_output import run_signal_output
            output = run_signal_output(
                recommended_trades=recommended,
                available_not_recommended=quality["available_not_recommended"],
                quality_results=quality["quality_results"],
                final_contracts=cb_result["final_contracts"],
                account_recommendation=cb_result["account_recommendation"],
                account_skip_reason=cb_result["account_skip_reason"],
                features=data["features"],
                ewma_states=data["ewma_states"],
                aim_breakdown=aim["aim_breakdown"],
                combined_modifier=aim["combined_modifier"],
                regime_probs=regime["regime_probs"],
                expected_edge=trades["expected_edge"],
                locked_strategies=data["locked_strategies"],
                tsm_configs=data["tsm_configs"],
                user_silo=user_silo,
                assets_detail=data["assets_detail"],
                session_id=session_id,
            )

            # Register all signals as shadow positions for theoretical tracking.
            # If TAKEN, the shadow is removed later (_handle_taken_skipped).
            # If SKIPPED/PARITY_SKIPPED, the shadow resolves → theoretical outcome.
            signals = output.get("signals", [])
            from captain_online.blocks.b7_shadow_monitor import register_shadow_position
            for sig in signals:
                shadow = register_shadow_position(sig, session_id)
                with self._position_lock:
                    self.shadow_positions.append(shadow)

            return signals

        except Exception as e:
            user_id = user_silo.get("user_id", "unknown")
            logger.error("User %s B6 signal FAILED: %s", user_id, e, exc_info=True)
            return []

    def _process_user(self, session_id: int, data: dict, regime: dict, aim: dict, user_silo: dict):
        """Run B4→B5→B5B→B5C→B6 for one user (legacy path when no OR tracker)."""
        result = self._process_user_sizing(session_id, data, regime, aim, user_silo)
        if result is None:
            return
        signals = self._run_b6_for_user(session_id, data, regime, aim, result)
        self._all_signals.extend(signals)

    def _run_position_monitor(self):
        """Run B7 position monitoring pass.

        Order matters: B7 monitor_positions runs FIRST so any TP/SL/TIME_EXIT
        resolutions remove their positions from the open set before B7B scans
        for NKD trail updates — we never want to issue a /Order/modify on a
        position whose SL just fired and which the broker has already closed.
        """
        from captain_online.blocks.b7_position_monitor import monitor_positions
        from captain_online.blocks.b1_data_ingestion import _load_tsm_configs
        tsm_configs = _load_tsm_configs()
        with self._position_lock:
            resolved = monitor_positions(self.open_positions, tsm_configs)
            for pos in resolved:
                try:
                    self.open_positions.remove(pos)
                except ValueError:
                    logger.warning("Position already removed from tracking: %s", pos)
                sig_id = pos.get("signal_id")
                if sig_id:
                    try:
                        get_redis_client().hdel(REDIS_KEY_OPEN_POSITIONS, sig_id)
                    except Exception as exc:
                        logger.error("Failed to remove position %s from Redis: %s", sig_id, exc)

            # ── B7B: NKD trailing-stop ratchet ──
            # Runs after monitor_positions so we never modify a freshly-closed
            # position. Only fires when there is at least one open NKD trail
            # position; non-NKD towers pay zero cost.
            if any(p.get("is_nkd_trail") for p in self.open_positions):
                try:
                    from captain_online.blocks.b7b_nkd_trail import scan_nkd_trails
                    from shared.topstep_client import get_topstep_client
                    from captain_command.blocks.b12_compliance_gate import (
                        check_compliance_gate,
                    )
                    gate = check_compliance_gate()
                    execution_mode = gate.get("execution_mode", "MANUAL")
                    scan_nkd_trails(
                        open_positions=self.open_positions,
                        client=get_topstep_client(),
                        redis_client=get_redis_client(),
                        execution_mode=execution_mode,
                    )
                except Exception as e:
                    logger.error("ON-B7B-NKD scan error: %s", e, exc_info=True)

    def _run_shadow_monitor(self):
        """Run shadow position monitoring pass for theoretical outcomes."""
        from captain_online.blocks.b7_shadow_monitor import monitor_shadow_positions
        with self._position_lock:
            resolved = monitor_shadow_positions(self.shadow_positions)
            for shadow in resolved:
                try:
                    self.shadow_positions.remove(shadow)
                except ValueError:
                    pass

    def _initialize_session_budget(self, session_id: int) -> None:
        """Compute and persist this session's effective per-session budget.

        At every session-open (LON 03:00, NY 09:30, APAC 18:00), for every
        account with ``topstep_optimisation=true``:

        1. Read the session's SOD share from D08.computed_sod.session.<KEY>
           (written by Command Block 8 at 19:00 EST the prior evening).
        2. Read all completed earlier sessions today from D23 to compute
           the carryover unused-pool (parity-skip support).
        3. Apply ``compute_session_carryover`` (Isaac's "available × share /
           remaining" formula) to derive the effective L_halt and E.
        4. INSERT a fresh D23 row keyed by (account_id, session_id) with
           ``l_t=0``, ``n_t=0``, ``effective_l_halt`` / ``effective_e_exposure``
           / ``session_opened_at`` populated.

        Idempotent — if a row already exists for this (account, session, today)
        with ``session_opened_at`` set, this method is a no-op for that account.

        Failure on a single account is logged and skipped — does NOT abort
        the rest. Failure of the whole method is caught by the caller in
        ``_run_session`` so B5C falls back to legacy single-budget for this
        session if anything goes wrong.

        Sources:
          - Spec: ``docs2/quick-fixes/circuit-breaker-nkd-issue/15_Topstep_Optimisation_Functions (1).md`` §4.4.4
          - HMM:  ``docs2/quick-fixes/circuit-breaker-nkd-issue/16_HMM_Opportunity_Regime_Spec.md`` §3.6
          - Plan: ``docs2/audits/2026-05-06_per_session_budget_design.md``
        """
        from decimal import Decimal as _D
        from shared.constants import SESSION_IDS as _SESSION_IDS
        from shared.questdb_client import get_cursor as _gc, qexecute
        from shared.json_helpers import parse_json_decimal as _pjd
        from shared.decimal_json import dumps_decimal as _dd
        from shared.sod_session_budget import (
            session_budget_shares as _shares_fn,
            compute_session_carryover as _carryover_fn,
            sessions_earlier_in_day as _earlier_fn,
            sessions_remaining_in_day as _remaining_fn,
            session_key_for as _key_fn,
            TRADING_DAY_SESSION_ORDER as _ORDER,
        )
        import json as _json

        if session_id not in _ORDER:
            # NY_PRE etc. — falls back to legacy single-budget per design (v1).
            logger.debug(
                "ON-Orch: session %s not in TRADING_DAY_SESSION_ORDER — "
                "skipping per-session budget init (legacy fallback applies)",
                _SESSION_IDS.get(session_id, session_id),
            )
            return

        today = datetime.now(_ET).date()

        # Idempotency: if any account already has this (session, today) opened,
        # skip the whole method to avoid double-counting carryover. We check
        # one canonical account — the single-account convention is the eval
        # combine reality (multi-instance towers each manage one account).
        with _gc() as cur:
            cur.execute(
                """SELECT account_id, topstep_state
                   FROM p3_d08_tsm_state
                   LATEST ON last_updated PARTITION BY account_id"""
            )
            d08_rows = cur.fetchall() or []

        for d08 in d08_rows:
            ac_id = d08[0]
            ts_state_raw = d08[1] or "{}"
            try:
                ts_state = _pjd(ts_state_raw, {})
            except Exception:
                ts_state = {}
            computed_sod = ts_state.get("computed_sod") if isinstance(ts_state, dict) else None
            if not computed_sod:
                logger.debug(
                    "ON-Orch: account %s has no computed_sod — skipping "
                    "session-budget init (Phase 2 not yet run for this account)",
                    ac_id,
                )
                continue

            # SOD totals
            sod_l_halt_total = _D(str(computed_sod.get("L_halt", 0) or 0))
            sod_e_total = _D(str(computed_sod.get("E_daily_exposure", 0) or 0))
            if sod_l_halt_total <= 0 or sod_e_total <= 0:
                logger.debug(
                    "ON-Orch: account %s has zero SOD totals (L_halt=%s, "
                    "E=%s) — skipping",
                    ac_id, sod_l_halt_total, sod_e_total,
                )
                continue

            # Per-session shares: prefer the SOD-frozen ones if present,
            # else recompute (matches what Phase 2 wrote with the same HMM state).
            session_block = computed_sod.get("session", {}) or {}
            shares: dict[str, _D] = {}
            for k in ("NY", "LON", "APAC"):
                entry = session_block.get(k, {}) or {}
                share_val = entry.get("share")
                if share_val is not None:
                    shares[k] = _D(str(share_val))
            if not shares:
                # SOD didn't write per-session shares (legacy state) —
                # fall back to live recompute. Must match what compute_sod
                # WOULD have written; absent HMM state, defaults to equal.
                shares = _shares_fn(None)

            # Pull state for completed-earlier sessions today.
            earlier_ids = _earlier_fn(session_id)
            completed_state: dict[str, dict] = {}
            with _gc() as cur:
                for sid in earlier_ids:
                    sess_key = _key_fn(sid)
                    cur.execute(
                        """SELECT l_t, effective_l_halt, effective_e_exposure,
                                  session_opened_at
                           FROM p3_d23_circuit_breaker_intraday
                           WHERE account_id = %s AND session_id = %s
                           LATEST ON last_updated PARTITION BY account_id, session_id""",
                        (ac_id, int(sid)),
                    )
                    row = cur.fetchone()
                    if row is None:
                        # Session never opened today (parity skip pre-orch-start
                        # OR tower was offline). Treat as full-budget unused.
                        completed_state[sess_key] = {
                            "effective_l_halt": sod_l_halt_total * shares.get(sess_key, _D("0")),
                            "effective_e_exposure": sod_e_total * shares.get(sess_key, _D("0")),
                            "l_t_final": _D("0"),
                        }
                        continue
                    # Only count rows whose session_opened_at is on TODAY.
                    # If session_opened_at is NULL the session hasn't actually
                    # opened today — treat as full carryover.
                    opened_at = row[3]
                    if opened_at is None:
                        completed_state[sess_key] = {
                            "effective_l_halt": sod_l_halt_total * shares.get(sess_key, _D("0")),
                            "effective_e_exposure": sod_e_total * shares.get(sess_key, _D("0")),
                            "l_t_final": _D("0"),
                        }
                        continue
                    completed_state[sess_key] = {
                        "effective_l_halt": _D(str(row[1] or 0)),  # decimal-boundary: ok (Decimal(str()) coerces falsy-zero correctly)
                        "effective_e_exposure": _D(str(row[2] or 0)),  # decimal-boundary: ok (Decimal(str()) coerces falsy-zero correctly)
                        "l_t_final": _D(str(row[0] or 0)),  # decimal-boundary: ok (Decimal(str()) coerces falsy-zero correctly)
                    }

            # Idempotency: if THIS session already has session_opened_at on
            # today's date for this account, skip (re-init would double-count).
            with _gc() as cur:
                cur.execute(
                    """SELECT effective_l_halt, session_opened_at
                       FROM p3_d23_circuit_breaker_intraday
                       WHERE account_id = %s AND session_id = %s
                       LATEST ON last_updated PARTITION BY account_id, session_id""",
                    (ac_id, int(session_id)),
                )
                existing = cur.fetchone()
            if existing and existing[0] is not None and existing[1] is not None:
                logger.info(
                    "ON-Orch: session %s already initialised for %s (eff_L_halt=%s) "
                    "— skipping re-init",
                    _SESSION_IDS.get(session_id, session_id), ac_id, existing[0],
                )
                continue

            # Compute carryover.
            remaining_ids = _remaining_fn(session_id)
            eff_l_halt, eff_e = _carryover_fn(
                sod_l_halt_total=sod_l_halt_total,
                sod_e_total=sod_e_total,
                shares=shares,
                completed_sessions_state=completed_state,
                target_session_id=session_id,
                remaining_session_ids=remaining_ids,
            )

            # Persist initial D23 row for this (account, session) today.
            with _gc() as cur:
                qexecute(
                    cur,
                    """INSERT INTO p3_d23_circuit_breaker_intraday(
                           account_id, session_id, l_t, n_t,
                           l_b, n_b,
                           effective_l_halt, effective_e_exposure,
                           session_opened_at, last_updated
                       ) VALUES(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                    (
                        ac_id, int(session_id),
                        _D("0"), 0,
                        _dd({}), _json.dumps({}),
                        eff_l_halt, eff_e,
                        datetime.now(_ET).isoformat(),
                        datetime.now(_ET).isoformat(),
                    ),
                )

            sess_name = _SESSION_IDS.get(session_id, session_id)
            logger.info(
                "ON-Orch: session %s init for %s — eff_L_halt=%.2f eff_E=%.2f "
                "(SOD share=%.4f, completed=%d earlier sessions, carryover=%.2f)",
                sess_name, ac_id, float(eff_l_halt), float(eff_e),
                float(shares.get(_key_fn(session_id), _D("0"))),
                len(completed_state),
                float(eff_l_halt - sod_l_halt_total * shares.get(_key_fn(session_id), _D("0"))),
            )

    def _circuit_breaker_check(self, session_id: int) -> bool:
        """Per Arch §19.6: DATA_HOLD >= 3 OR VIX > threshold OR manual_halt."""
        from captain_online.blocks.b5c_circuit_breaker import _get_data_hold_count, _get_current_vix

        data_hold_count = _get_data_hold_count()
        if data_hold_count >= 3:
            logger.warning("Circuit breaker: %d assets in DATA_HOLD", data_hold_count)
            return False

        vix = _get_current_vix()
        if vix is not None and vix > 50.0:
            logger.warning("Circuit breaker: VIX = %.1f", vix)
            return False

        # Manual halt check
        if self._is_manual_halt():
            logger.warning("Circuit breaker: manual halt active")
            return False

        return True

    def _is_manual_halt(self) -> bool:
        """Check if manual halt is active via P3-D17."""
        from shared.questdb_client import get_cursor
        with get_cursor() as cur:
            cur.execute(
                """SELECT param_value FROM p3_d17_system_monitor_state
                   WHERE param_key = 'manual_halt_all'
                   LATEST ON last_updated PARTITION BY param_key"""
            )
            row = cur.fetchone()
        if row and row[0]:
            return row[0].lower() in ("true", "1", "yes")
        return False

    def _get_active_users(self) -> list[dict]:
        """Load active users from P3-D15."""
        from shared.questdb_client import get_cursor
        with get_cursor() as cur:
            cur.execute(
                """SELECT user_id, role FROM p3_d15_user_session_data
                   ORDER BY last_active DESC"""
            )
            rows = cur.fetchall()

        seen = set()
        users = []
        for r in rows:
            if r[0] in seen:
                continue
            seen.add(r[0])
            users.append({"user_id": r[0], "role": r[1]})
        return users if users else [{"user_id": os.environ.get("BOOTSTRAP_USER_ID", "primary_user"), "role": "ADMIN"}]

    def _load_user_silo(self, user_id: str) -> dict | None:
        """Load user capital silo from P3-D16.

        Monetary fields (starting_capital, total_capital) come back as
        Decimal via shared.decimal_boundary.as_money so the dict is
        type-pure for downstream consumers (B4 sizing, B6 signal output).
        Risk percentages (max_portfolio_risk_pct, correlation_threshold,
        user_kelly_ceiling) stay float — they are dimensionless ratios,
        not money.
        """
        from shared.questdb_client import get_cursor
        from shared.decimal_boundary import as_money
        with get_cursor() as cur:
            cur.execute(
                """SELECT user_id, starting_capital, total_capital, accounts,
                          max_simultaneous_positions, max_portfolio_risk_pct,
                          correlation_threshold, user_kelly_ceiling
                   FROM p3_d16_user_capital_silos
                   WHERE user_id = %s
                   LATEST ON last_updated PARTITION BY user_id""",
                (user_id,),
            )
            row = cur.fetchone()

        if row is None:
            return None

        return {
            "user_id": row[0],
            "starting_capital": as_money(row[1]),
            "total_capital": as_money(row[2]),
            "accounts": row[3] or "[]",
            "max_simultaneous_positions": row[4],
            "max_portfolio_risk_pct": row[5] if row[5] is not None else 0.10,
            "correlation_threshold": row[6] if row[6] is not None else 0.7,
            "user_kelly_ceiling": row[7] if row[7] is not None else 1.0,
        }

    def _command_listener(self):
        """Read commands from Redis Stream with consumer group acknowledgment.

        Reconnects with exponential backoff (1s → 30s) on any failure.
        """
        backoff = 1
        while self.running:
            try:
                ensure_consumer_group(STREAM_COMMANDS, GROUP_ONLINE_COMMANDS)
                logger.info("Online command stream consumer group ready")
                backoff = 1

                while self.running:
                    for msg_id, data in read_stream(
                        STREAM_COMMANDS, GROUP_ONLINE_COMMANDS,
                        "online_1", block=2000,
                    ):
                        self._handle_command(data)
                        ack_message(STREAM_COMMANDS, GROUP_ONLINE_COMMANDS, msg_id)

            except Exception as e:
                if not self.running:
                    break
                logger.error("Command stream error: %s — reconnecting in %ds", e, backoff)
                time.sleep(backoff)
                backoff = min(backoff * 2, 30)

    def _handle_command(self, data: dict):
        """Handle incoming command."""
        cmd_type = data.get("type")
        if cmd_type == "MANUAL_HALT":
            logger.info("Manual halt command received")
            # Stored in D17 by Command process
        elif cmd_type == "TAKEN_SKIPPED":
            self._handle_taken_skipped(data)
        else:
            logger.debug("Unhandled command type: %s", cmd_type)

    def _handle_taken_skipped(self, data: dict):
        """Handle TAKEN/SKIPPED decision from Command/GUI."""
        action = data.get("action")
        signal_id = data.get("signal_id")
        user_id = data.get("user_id")

        if action == "TAKEN":
            # Bug C boundary (2026-04-30): `data` came from a Redis stream
            # message reassembled via loads_decimal, so monetary fields
            # are Decimal-typed. Coerce all price / monetary fields via
            # the shared boundary helpers so the open_positions dict is
            # type-pure for monitor_positions / shadow_monitor downstream.
            from shared.decimal_boundary import as_money, as_money_or_none
            position = {
                "signal_id": signal_id,
                "user_id": user_id,
                "asset": data.get("asset"),
                "direction": 1 if data.get("direction") in (1, "BUY") else -1 if data.get("direction") in (-1, "SELL") else int(data.get("direction") or 1),
                "entry_price": as_money_or_none(
                    data.get("actual_entry_price")
                    if data.get("actual_entry_price") is not None
                    else data.get("entry_price")
                ),
                "signal_entry_price": as_money_or_none(data.get("entry_price")),
                "actual_entry_price": as_money_or_none(data.get("actual_entry_price")),
                "contracts": int(data.get("contracts", 0) or 0),
                "tp_level": as_money_or_none(data.get("tp_level")),
                "sl_level": as_money_or_none(data.get("sl_level")),
                "point_value": as_money(data.get("point_value"), default=as_money(50)),
                "risk_amount": as_money(data.get("risk_amount")),
                "account": data.get("account_id"),
                "session": data.get("session"),
                "regime_state": data.get("regime_state"),
                "combined_modifier": data.get("combined_modifier"),
                "aim_breakdown": data.get("aim_breakdown"),
                "tsm_id": data.get("tsm_id"),
                "entry_time": datetime.now(_ET),
                # Phase 3a: bracket=True means the exchange owns the OCO SL/TP
                # legs. B7 uses this to fetch the actual exit fill price from
                # the broker on resolution rather than relying on its polled
                # lastPrice (which can drift from the stop fill on fast moves).
                "bracket": bool(data.get("bracket", False)),
                "entry_order_id": data.get("entry_order_id"),
                # NY-Open-May-5 fix: when bracket=False the SL/TP were placed
                # as separate non-OCO orders. B7 must cancel the orphan when
                # the other one fills. For bracket=True these are "BRACKET".
                "sl_order_id": data.get("sl_order_id"),
                "tp_order_id": data.get("tp_order_id"),
                # NKD pivot trail-control fields (None for all non-NKD assets).
                # Populated by B6 → Command orchestrator → here when is_nkd_trail=True.
                # F2 fix (audit §4 + §7 Option B): tp_dollars / snapped_d_init /
                # jitter_* now thread through sanitise_for_api → _auto_execute_signal
                # → STREAM_COMMANDS → here.
                "is_nkd_trail": bool(data.get("is_nkd_trail", False)),
                "tp_dollars": as_money_or_none(data.get("tp_dollars")),
                "snapped_d_init": as_money_or_none(data.get("snapped_d_init")),
                # F2 audit §8.2: jitter_x/y/j threaded from B6 sample. The
                # defence-in-depth re-sample at b7b_nkd_trail.py:660-669 still
                # wins when these are None (e.g. replay tests or pre-F2 Redis
                # hash rehydration), but the normal Isaac-tower path now reuses
                # B6's J for per-trade symmetry.
                "jitter_x": as_money_or_none(data.get("jitter_x")),
                "jitter_y": (
                    int(data["jitter_y"])
                    if data.get("jitter_y") is not None else None
                ),
                "jitter_j": as_money_or_none(data.get("jitter_j")),
                "current_phase": None,
                "current_buffer": None,
                "current_stop_price": None,
                "modify_seq": 0,
            }
            with self._position_lock:
                self.open_positions.append(position)
                # Remove shadow position — real B7 supersedes theoretical tracking.
                # The real trade outcome from B7 will feed into ALL offline blocks
                # (both Category A and Category B), so the shadow is redundant.
                self.shadow_positions = [
                    s for s in self.shadow_positions if s.get("signal_id") != signal_id
                ]
            # Bug C: position dict now holds Decimals (Phase 5 type purity).
            # Use dumps_decimal so Decimal serialises as a string in the
            # Redis hash; the corresponding read path is _reconcile_open_positions
            # which already coerces back to float on recovery (line 116).
            pos_for_redis = dict(position)
            pos_for_redis["entry_time"] = position["entry_time"].isoformat()
            # C5: consume staged bracket children (race: UserStream delivered
            # SL/TP child order IDs before this TAKEN message was processed).
            if position.get("bracket"):
                _entry_oid = data.get("entry_order_id")
                _acct = data.get("account_id")
                if _entry_oid and _acct:
                    _children_key = (
                        f"bracket:children:{_acct}:{_entry_oid}"
                    )
                    try:
                        _children_raw = get_redis_client().get(_children_key)
                        if _children_raw:
                            _children = json.loads(_children_raw)
                            if _children.get("sl_order_id"):
                                pos_for_redis["sl_order_id"] = _children["sl_order_id"]
                                position["sl_order_id"] = _children["sl_order_id"]
                            if _children.get("tp_order_id"):
                                pos_for_redis["tp_order_id"] = _children["tp_order_id"]
                                position["tp_order_id"] = _children["tp_order_id"]
                            get_redis_client().delete(_children_key)
                            logger.info(
                                "Applied staged bracket children for %s:"
                                " sl=%s tp=%s",
                                signal_id,
                                pos_for_redis.get("sl_order_id"),
                                pos_for_redis.get("tp_order_id"),
                            )
                    except Exception as _stage_exc:
                        logger.warning(
                            "Failed to apply staged bracket children: %s",
                            _stage_exc,
                        )
            try:
                from shared.decimal_json import dumps_decimal
                get_redis_client().hset(REDIS_KEY_OPEN_POSITIONS, signal_id,
                                        dumps_decimal(pos_for_redis))
            except Exception as exc:
                logger.error("Failed to persist position to Redis: %s", exc)
            logger.info("Position opened: %s for user %s (%d contracts)",
                        data.get("asset"), user_id, position["contracts"])

        elif action == "SKIPPED":
            logger.info("Signal %s SKIPPED by user %s — shadow monitor will track outcome",
                        signal_id, user_id)
