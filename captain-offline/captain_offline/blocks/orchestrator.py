# region imports
try:
    from AlgorithmImports import *
except ImportError:
    pass
# endregion
"""Captain Offline Orchestrator — P3-ORCH-OFFLINE (Task 2.10a / OFF lines 1025-1091).

Event-driven scheduler that dispatches to all Offline blocks.

Events:
  trade_outcome_received -> DMA, BOCPD, CUSUM, Kelly, TSM sim, CB params
  daily_close            -> drift detection, AIM lifecycle, warmup check
  asset_added            -> asset_bootstrap
  weekly_schedule        -> HDWM diversity, diagnostic (WEEKLY), CUSUM calibration check
  monthly_schedule       -> sensitivity scan, diagnostic (MONTHLY)
  level_3_trigger        -> auto-expansion
  injection_event        -> injection comparison
  adoption_decision      -> transition phasing
  tsm_change             -> TSM re-simulation
  action_resolved        -> diagnostic D8 verification
  quarterly_schedule     -> CUSUM recalibration

Subscribes to Redis: captain:trade_outcomes, captain:commands
"""

import json
import logging
import threading
import time
from datetime import datetime

from shared.constants import now_et
from shared.redis_client import (
    get_redis_client,
    ensure_consumer_group, read_stream, ack_message,
    STREAM_TRADE_OUTCOMES, STREAM_COMMANDS, STREAM_SIGNAL_OUTCOMES,
    GROUP_OFFLINE_OUTCOMES, GROUP_OFFLINE_COMMANDS, GROUP_OFFLINE_SIGNAL_OUTCOMES,
)
from shared.journal import write_checkpoint
from shared.process_logger import ProcessLogger

logger = logging.getLogger(__name__)


class OfflineOrchestrator:
    """Event loop for Captain Offline process."""

    def __init__(self):
        self.running = False
        self._detectors = {}  # {asset_id: (bocpd_detector, cusum_detector)}
        self._active_transitions = {}  # {asset_id: TransitionPhaser}
        self._redis_thread = None  # Stored for graceful shutdown join
        self.plog = ProcessLogger("OFFLINE", get_redis_client())

    def start(self):
        """Start the orchestrator event loop."""
        self.running = True
        logger.info("Offline orchestrator starting...")
        write_checkpoint("OFFLINE", "ORCHESTRATOR_START", "init", "subscribe_redis")

        # Resume any active transitions from persistence
        self._resume_transitions()

        # G-OFF-011: Restore BOCPD/CUSUM detector state from D04
        self._restore_detectors()

        # G-OFF-010: Run init-time CUSUM calibration for detectors with empty limits
        self._init_cusum_calibration()

        # Start Redis subscriber in background thread
        self._redis_thread = threading.Thread(target=self._redis_listener, daemon=True)
        self._redis_thread.start()

        # Start scheduler in main thread
        self._run_scheduler()

    def stop(self):
        """Stop the orchestrator. Joins Redis listener to flush in-flight outcomes."""
        self.running = False
        logger.info("Offline orchestrator stopping...")
        if self._redis_thread and self._redis_thread.is_alive():
            self._redis_thread.join(timeout=5.0)
            if self._redis_thread.is_alive():
                logger.warning("Redis listener thread did not exit within 5s timeout")

    def _redis_listener(self):
        """Read trade outcomes and commands from Redis Streams.

        Uses consumer groups for durable delivery with acknowledgment.
        Reconnects with exponential backoff (1s → 30s) on any failure.
        """
        backoff = 1
        while self.running:
            try:
                ensure_consumer_group(STREAM_TRADE_OUTCOMES, GROUP_OFFLINE_OUTCOMES)
                ensure_consumer_group(STREAM_COMMANDS, GROUP_OFFLINE_COMMANDS)
                ensure_consumer_group(STREAM_SIGNAL_OUTCOMES, GROUP_OFFLINE_SIGNAL_OUTCOMES)
                logger.info("Offline stream consumer groups ready")
                backoff = 1

                while self.running:
                    # Read trade outcomes (real trades — feed ALL blocks: Category A + B)
                    for msg_id, data in read_stream(
                        STREAM_TRADE_OUTCOMES, GROUP_OFFLINE_OUTCOMES,
                        "offline_1", block=1000,
                    ):
                        self._handle_trade_outcome(data)
                        ack_message(STREAM_TRADE_OUTCOMES, GROUP_OFFLINE_OUTCOMES, msg_id)

                    # Read signal outcomes (theoretical — feed Category A only)
                    for msg_id, data in read_stream(
                        STREAM_SIGNAL_OUTCOMES, GROUP_OFFLINE_SIGNAL_OUTCOMES,
                        "offline_1", block=500,
                    ):
                        self._handle_signal_outcome(data)
                        ack_message(STREAM_SIGNAL_OUTCOMES, GROUP_OFFLINE_SIGNAL_OUTCOMES, msg_id)

                    # Read commands
                    for msg_id, data in read_stream(
                        STREAM_COMMANDS, GROUP_OFFLINE_COMMANDS,
                        "offline_1", block=1000,
                    ):
                        self._handle_command(data)
                        ack_message(STREAM_COMMANDS, GROUP_OFFLINE_COMMANDS, msg_id)

            except Exception as e:
                if not self.running:
                    break
                logger.error("Stream listener error: %s — reconnecting in %ds", e, backoff)
                time.sleep(backoff)
                backoff = min(backoff * 2, 30)

    def _handle_trade_outcome(self, outcome: dict):
        """Process a trade outcome event.

        Triggers: DMA, BOCPD, CUSUM, Level escalation, Kelly, TSM sim, CB params.
        """
        asset_id = outcome.get("asset", "")
        pnl = outcome.get("pnl", 0)
        logger.info("Trade outcome received: %s pnl=%.2f", asset_id, pnl)
        self.plog.info(
            f"Trade outcome received: {asset_id} {'+'if pnl>=0 else ''}"
            f"${pnl:.2f}",
            source="orchestrator",
        )

        write_checkpoint("OFFLINE", "TRADE_OUTCOME", "processing",
                         "dma_bocpd_cusum_kelly", {"asset": asset_id})

        try:
            # 1. DMA meta-weight update
            from captain_offline.blocks.b1_dma_update import run_dma_update
            run_dma_update(outcome)
            self.plog.info(f"B1: DMA meta-weight update \u2014 {asset_id}", source="b1_dma")

            # 2. BOCPD decay detection
            from captain_offline.blocks.b2_bocpd import run_bocpd_update
            pnl_pc = outcome.get("pnl", 0) / max(outcome.get("contracts", 1), 1)
            bocpd_det = self._detectors.get(asset_id, (None, None))[0]
            cp_prob, bocpd_det = run_bocpd_update(asset_id, pnl_pc, bocpd_det)
            if cp_prob and cp_prob > 0.5:
                self.plog.warn(f"B2: BOCPD changepoint detected for {asset_id} (p={cp_prob:.2f})", source="b2_bocpd")
            else:
                self.plog.info(f"B2: BOCPD \u2014 no changepoint ({asset_id})", source="b2_bocpd")

            # 3. CUSUM decay detection
            from captain_offline.blocks.b2_cusum import run_cusum_update
            cusum_det = self._detectors.get(asset_id, (None, None))[1]
            cusum_signal, cusum_det = run_cusum_update(asset_id, pnl_pc, cusum_det)

            self._detectors[asset_id] = (bocpd_det, cusum_det)

            # 4. Level escalation check
            from captain_offline.blocks.b2_level_escalation import check_level_escalation
            cp_history = bocpd_det.cp_history if bocpd_det else []
            check_level_escalation(asset_id, cp_prob, cp_history, cusum_signal)

            # 5. Kelly parameter update
            from captain_offline.blocks.b8_kelly_update import run_kelly_update
            run_kelly_update(outcome)
            self.plog.info(f"B8: Kelly update \u2014 {asset_id}", source="b8_kelly")

            # 6. CB parameter estimation (if sufficient data)
            from captain_offline.blocks.b8_cb_params import estimate_cb_params
            account_id = outcome.get("account", "")
            model_m = outcome.get("model", 4)
            if account_id:
                estimate_cb_params(account_id, model_m)

            # 7. TSM simulation update
            if account_id:
                self._run_tsm_for_account(account_id)

        except Exception as e:
            logger.error("Error processing trade outcome for %s: %s", asset_id, e, exc_info=True)

        write_checkpoint("OFFLINE", "TRADE_OUTCOME_COMPLETE", "trade_processed", "waiting")

    def _handle_signal_outcome(self, outcome: dict):
        """Process a THEORETICAL signal outcome (from shadow monitor).

        Category A learning only: DMA, BOCPD, CUSUM, Kelly/EWMA.
        Category B (CB params, TSM simulation) is skipped because these
        must reflect actual account-specific trading history.

        This keeps strategy parameters (win rate, AIM weights, Kelly fraction)
        synchronized across multi-instance deployments while allowing each
        instance's risk management to adapt to its own account state.
        """
        asset_id = outcome.get("asset", "")
        pnl = outcome.get("pnl", 0)
        logger.info("Theoretical signal outcome: %s pnl=%.2f (Category A learning)",
                     asset_id, pnl)

        write_checkpoint("OFFLINE", "SIGNAL_OUTCOME", "processing",
                         "category_a_only", {"asset": asset_id, "theoretical": True})

        try:
            # 1. DMA meta-weight update (Category A)
            from captain_offline.blocks.b1_dma_update import run_dma_update
            run_dma_update(outcome)

            # 2. BOCPD decay detection (Category A)
            from captain_offline.blocks.b2_bocpd import run_bocpd_update
            pnl_pc = pnl / max(outcome.get("contracts", 1), 1)
            bocpd_det = self._detectors.get(asset_id, (None, None))[0]
            cp_prob, bocpd_det = run_bocpd_update(asset_id, pnl_pc, bocpd_det)

            # 3. CUSUM decay detection (Category A)
            from captain_offline.blocks.b2_cusum import run_cusum_update
            cusum_det = self._detectors.get(asset_id, (None, None))[1]
            cusum_signal, cusum_det = run_cusum_update(asset_id, pnl_pc, cusum_det)

            self._detectors[asset_id] = (bocpd_det, cusum_det)

            # 4. Level escalation check (Category A)
            from captain_offline.blocks.b2_level_escalation import check_level_escalation
            cp_history = bocpd_det.cp_history if bocpd_det else []
            check_level_escalation(asset_id, cp_prob, cp_history, cusum_signal)

            # 5. Kelly/EWMA parameter update (Category A)
            from captain_offline.blocks.b8_kelly_update import run_kelly_update
            run_kelly_update(outcome)

            # NOTE: CB params (b8_cb_params) and TSM simulation are INTENTIONALLY
            # SKIPPED here — they are Category B (account-specific) and must only
            # learn from real trade outcomes in _handle_trade_outcome().

        except Exception as e:
            logger.error("Error processing signal outcome for %s: %s",
                         asset_id, e, exc_info=True)

        write_checkpoint("OFFLINE", "SIGNAL_OUTCOME_COMPLETE",
                         "theoretical_processed", "waiting")

    def _handle_command(self, command: dict):
        """Process commands from Captain Command."""
        cmd_type = command.get("type", "")

        if cmd_type == "ASSET_ADDED":
            asset_id = command.get("asset_id", "")
            if asset_id:
                self._handle_asset_added(asset_id, command)

        elif cmd_type == "INJECTION":
            self._handle_injection(command)

        elif cmd_type == "ADOPTION_DECISION":
            self._handle_adoption(command)

        elif cmd_type == "TSM_CHANGE":
            account_id = command.get("account_id", "")
            if account_id:
                self._run_tsm_for_account(account_id)

        elif cmd_type in ("ACTIVATE_AIM", "DEACTIVATE_AIM"):
            self._handle_aim_activation(command)

        elif cmd_type == "ACTION_RESOLVED":
            from captain_offline.blocks.b9_diagnostic import run_diagnostic
            run_diagnostic(mode="WEEKLY")  # D8 verification

    def _handle_asset_added(self, asset_id: str, data: dict):
        """Bootstrap a new asset."""
        from captain_offline.blocks.bootstrap import asset_bootstrap
        historical_trades = data.get("historical_trades", [])
        regime_labels = data.get("regime_labels", {})
        asset_bootstrap(asset_id, historical_trades, regime_labels)

    def _handle_injection(self, data: dict):
        """Handle strategy injection candidate."""
        from captain_offline.blocks.b4_injection import run_injection_comparison
        run_injection_comparison(
            asset_id=data.get("asset_id", ""),
            new_candidate=data.get("candidate", {}),
            current_strategy=data.get("current_strategy", {}),
            candidate_pnl=data.get("candidate_pnl", []),
            current_pnl=data.get("current_pnl", []),
        )

    def _handle_adoption(self, data: dict):
        """Handle strategy adoption decision."""
        from captain_offline.blocks.b4_injection import TransitionPhaser
        decision = data.get("decision", "REJECT")
        if decision == "REJECT":
            return  # nothing to phase

        phaser = TransitionPhaser(
            asset_id=data.get("asset_id", ""),
            new_strategy=data.get("new_strategy", {}),
            old_strategy=data.get("old_strategy", {}),
            mode=decision,
            total_days=data.get("transition_days", 10),
        )
        phaser.save()  # persist to QuestDB
        self._active_transitions[phaser.asset_id] = phaser
        logger.info("Transition started for %s: mode=%s, %d days",
                     phaser.asset_id, decision, phaser.total_days)

    def _handle_aim_activation(self, command: dict):
        """Activate or deactivate an AIM via user command from GUI."""
        from captain_offline.blocks.b1_aim_lifecycle import _update_aim_status

        aim_id = command.get("aim_id")
        cmd_type = command.get("type", "")
        new_status = "ACTIVE" if cmd_type == "ACTIVATE_AIM" else "SUPPRESSED"

        if aim_id is None:
            logger.warning("AIM activation command missing aim_id")
            return

        # Apply to all assets in the universe
        try:
            from shared.questdb_client import get_cursor
            with get_cursor() as cur:
                cur.execute(
                    """SELECT DISTINCT asset_id FROM p3_d01_aim_model_states
                       WHERE aim_id = %s""",
                    (aim_id,),
                )
                assets = [r[0] for r in cur.fetchall()]

            if not assets:
                # No existing rows — apply to all assets in universe
                with get_cursor() as cur:
                    cur.execute(
                        "SELECT DISTINCT asset_id FROM p3_d00_asset_universe"
                    )
                    assets = [r[0] for r in cur.fetchall()]

            for asset_id in assets:
                _update_aim_status(aim_id, asset_id, new_status)

            logger.info("AIM %s %s for %d assets",
                        aim_id, new_status, len(assets))
        except Exception as exc:
            logger.error("AIM activation failed: %s", exc, exc_info=True)

    def _resume_transitions(self):
        """Resume active transitions from QuestDB on startup."""
        try:
            from captain_offline.blocks.b4_injection import TransitionPhaser
            active = TransitionPhaser.load_active()
            for phaser in active:
                self._active_transitions[phaser.asset_id] = phaser
            if active:
                logger.info("Resumed %d active transitions: %s",
                             len(active), [p.asset_id for p in active])
        except Exception as e:
            logger.error("Failed to resume transitions: %s", e)

    def _restore_detectors(self):
        """G-OFF-011: Restore BOCPD and CUSUM detector state from P3-D04 on startup.

        Calls from_dict() deserializers so accumulated detector state survives restarts.
        """
        try:
            from captain_offline.blocks.b2_bocpd import BOCPDDetector
            from captain_offline.blocks.b2_cusum import CUSUMDetector
            from shared.questdb_client import get_cursor

            with get_cursor() as cur:
                cur.execute(
                    """SELECT asset_id, bocpd_run_length_posterior,
                              cusum_c_up_prev, cusum_c_down_prev,
                              cusum_sprint_length, cusum_allowance,
                              cusum_sequential_limits
                       FROM p3_d04_decay_detector_states
                       LATEST ON last_updated PARTITION BY asset_id"""
                )
                rows = cur.fetchall()

            for row in rows:
                asset_id = row[0]

                # Restore BOCPD from full serialized state
                bocpd_det = None
                if row[1]:
                    try:
                        bocpd_state = json.loads(row[1])
                        bocpd_det = BOCPDDetector.from_dict(bocpd_state)
                    except (json.JSONDecodeError, KeyError, TypeError) as exc:
                        logger.warning("BOCPD restore failed for %s: %s", asset_id, exc)

                # Restore CUSUM from individual columns
                cusum_det = None
                cusum_state = {
                    "c_up": row[2] if row[2] is not None else 0.0,
                    "c_down": row[3] if row[3] is not None else 0.0,
                    "sprint_length": row[4] if row[4] is not None else 0,
                    "allowance": row[5] if row[5] is not None else 0.0,
                    "sequential_limits": {},
                }
                if row[6]:
                    try:
                        cusum_state["sequential_limits"] = json.loads(row[6])
                    except (json.JSONDecodeError, TypeError):
                        pass
                cusum_det = CUSUMDetector.from_dict(cusum_state)

                self._detectors[asset_id] = (bocpd_det, cusum_det)

            if self._detectors:
                logger.info("Restored detector state for %d assets: %s",
                            len(self._detectors), list(self._detectors.keys()))
        except Exception as e:
            logger.error("Failed to restore detector states: %s", e)

    def _init_cusum_calibration(self):
        """G-OFF-010: Run bootstrap calibration for CUSUM detectors with empty limits at init.

        Spec requires calibration at init AND quarterly. This fills the gap
        where sequential_limits would otherwise be empty until the first
        quarterly boundary, forcing fallback to the hardcoded default_limit.
        """
        try:
            from captain_offline.blocks.b2_cusum import (
                calibrate_cusum_limits, calibrate_and_persist, CUSUMDetector,
            )
            from shared.questdb_client import get_cursor

            with get_cursor() as cur:
                cur.execute(
                    "SELECT asset_id FROM p3_d00_asset_universe "
                    "WHERE captain_status = 'ACTIVE'"
                )
                assets = [r[0] for r in cur.fetchall()]

            calibrated = 0
            for asset_id in assets:
                # Skip if detector already has calibrated limits
                bocpd_det, cusum_det = self._detectors.get(asset_id, (None, None))
                if cusum_det and cusum_det.sequential_limits:
                    continue

                # Load trade history for calibration
                with get_cursor() as cur:
                    cur.execute(
                        "SELECT pnl, contracts FROM p3_d03_trade_outcome_log "
                        "WHERE asset = %s",
                        (asset_id,),
                    )
                    rows = cur.fetchall()

                returns = [r[0] / max(r[1], 1) for r in rows if r[1] and r[1] > 0]
                if len(returns) < 20:
                    continue

                # Calibrate and persist to D04
                calibrate_and_persist(asset_id, returns)

                # Update in-memory detector
                limits = calibrate_cusum_limits(returns)
                if cusum_det is None:
                    cusum_det = CUSUMDetector()
                cusum_det.sequential_limits = limits
                cusum_det.initialize(returns)
                self._detectors[asset_id] = (bocpd_det, cusum_det)
                calibrated += 1
                logger.info("Init-time CUSUM calibration for %s: %d sprint lengths",
                            asset_id, len(limits))

            if calibrated:
                logger.info("Init CUSUM calibration complete: %d assets calibrated", calibrated)
        except Exception as e:
            logger.error("Init CUSUM calibration error: %s", e)

    def _advance_transitions(self):
        """Advance all active transitions by one day. Called from daily schedule."""
        completed = []
        for asset_id, phaser in self._active_transitions.items():
            if phaser.completed:
                completed.append(asset_id)
                continue

            done = phaser.advance_day()
            if done:
                phaser.finalize()
                completed.append(asset_id)
                logger.info("Transition finalized for %s (day %d/%d)",
                             asset_id, phaser.current_day, phaser.total_days)
            else:
                logger.debug("Transition advanced for %s: day %d/%d",
                              asset_id, phaser.current_day, phaser.total_days)

        for asset_id in completed:
            del self._active_transitions[asset_id]

    def _dispatch_pending_jobs(self):
        """Check job queue and dispatch pending jobs.

        Handles: AIM14_EXPANSION, P1P2_RERUN (logged as pending — requires
        manual or external pipeline trigger).
        """
        try:
            from shared.questdb_client import get_cursor

            with get_cursor() as cur:
                cur.execute(
                    """SELECT job_id, job_type, asset_id, params
                       FROM p3_offline_job_queue
                       WHERE status = 'PENDING'
                       ORDER BY created_at"""
                )
                jobs = cur.fetchall()

            if not jobs:
                return

            logger.info("Job dispatcher: %d pending jobs found", len(jobs))

            for job_id, job_type, asset_id, params_json in jobs:
                params = json.loads(params_json) if params_json else {}

                # Mark as in-progress
                with get_cursor() as cur:
                    cur.execute(
                        """INSERT INTO p3_offline_job_queue
                           (job_id, job_type, asset_id, status, started_at, last_updated)
                           VALUES (%s, %s, %s, 'RUNNING', now(), now())""",
                        (job_id, job_type, asset_id),
                    )

                try:
                    if job_type == "AIM14_EXPANSION":
                        self._run_aim14_expansion(asset_id)
                        result_status = "COMPLETED"
                        result_msg = "AIM-14 expansion executed"

                    elif job_type == "P1P2_RERUN":
                        # P1/P2 rerun requires external pipeline — log as actionable
                        result_status = "AWAITING_MANUAL"
                        result_msg = (
                            f"P1/P2 rerun required for {asset_id}. "
                            "Run pipeline manually or via automation trigger."
                        )
                        logger.warning("P1/P2 rerun for %s requires manual execution", asset_id)

                    else:
                        result_status = "UNKNOWN_TYPE"
                        result_msg = f"Unrecognised job type: {job_type}"

                except Exception as e:
                    result_status = "FAILED"
                    result_msg = str(e)
                    logger.error("Job %s failed: %s", job_id, e, exc_info=True)

                # Store result
                with get_cursor() as cur:
                    cur.execute(
                        """INSERT INTO p3_offline_job_queue
                           (job_id, job_type, asset_id, status, result,
                            completed_at, last_updated)
                           VALUES (%s, %s, %s, %s, %s, now(), now())""",
                        (job_id, job_type, asset_id, result_status, result_msg),
                    )
                logger.info("Job %s [%s]: %s", job_id, job_type, result_status)

        except Exception as e:
            logger.error("Job dispatcher error: %s", e, exc_info=True)

    def _run_aim14_expansion(self, asset_id: str):
        """Execute AIM-14 auto-expansion for a decayed asset."""
        from captain_offline.blocks.b6_auto_expansion import run_auto_expansion
        from shared.questdb_client import get_cursor

        # Load historical returns for training and holdout
        with get_cursor() as cur:
            cur.execute(
                """SELECT pnl, contracts FROM p3_d03_trade_outcome_log
                   WHERE asset = %s ORDER BY ts""",
                (asset_id,),
            )
            rows = cur.fetchall()

        returns = [r[0] / max(r[1], 1) for r in rows if r[1] and r[1] > 0]
        if len(returns) < 60:
            logger.warning("AIM-14 for %s: insufficient data (%d < 60)", asset_id, len(returns))
            return

        # Split 80/20 for training/holdout
        split = int(len(returns) * 0.8)
        training = returns[:split]
        holdout = returns[split:]

        run_auto_expansion(asset_id, training, holdout)

    def _run_tsm_for_account(self, account_id: str):
        """Load TSM config and run Monte Carlo simulation for an account.

        Called after trade outcomes and on TSM_CHANGE events.
        Loads config from p3_d08_tsm_state and trade returns from p3_d03.
        """
        try:
            from captain_offline.blocks.b7_tsm_simulation import run_tsm_simulation
            from shared.questdb_client import get_cursor

            # Load TSM config for this account
            with get_cursor() as cur:
                cur.execute(
                    """SELECT starting_balance, current_balance, max_drawdown_limit,
                              max_daily_loss, profit_target, risk_goal,
                              evaluation_end_date
                       FROM p3_d08_tsm_state
                       WHERE account_id = %s
                       LATEST ON last_updated PARTITION BY account_id""",
                    (account_id,),
                )
                row = cur.fetchone()

            if not row:
                return  # no TSM config for this account

            tsm_config = {
                "starting_balance": row[0] or 150000,
                "current_balance": row[1] or row[0] or 150000,
                "max_drawdown_limit": row[2],
                "max_daily_loss": row[3],
                "profit_target": row[4],
                "risk_goal": row[5] or "PASS_EVAL",
                "evaluation_end_date": str(row[6]) if row[6] else None,
            }

            # Load trade returns for this account
            with get_cursor() as cur:
                cur.execute(
                    """SELECT pnl FROM p3_d03_trade_outcome_log
                       WHERE account_id = %s ORDER BY ts""",
                    (account_id,),
                )
                rows = cur.fetchall()

            trade_returns = [r[0] for r in rows if r[0] is not None]
            if len(trade_returns) < 10:
                return  # insufficient trade history for simulation

            run_tsm_simulation(account_id, trade_returns, tsm_config)

        except Exception as e:
            logger.error("TSM simulation error for %s: %s", account_id, e, exc_info=True)

    def _run_scheduler(self):
        """Time-based scheduler for periodic tasks."""
        last_daily = None
        last_weekly = None
        last_monthly = None
        last_quarterly = None

        while self.running:
            now = now_et()

            # Daily close (after 16:00 ET, run once)
            if now.hour >= 16 and last_daily != now.date():
                last_daily = now.date()
                self._run_daily()

            # Weekly (Monday)
            if now.weekday() == 0 and now.hour >= 0 and last_weekly != now.isocalendar()[1]:
                last_weekly = now.isocalendar()[1]
                self._run_weekly()

            # Monthly (1st of month)
            if now.day == 1 and now.hour >= 0 and last_monthly != now.month:
                last_monthly = now.month
                self._run_monthly()

            # Quarterly (1st of Jan/Apr/Jul/Oct)
            if now.day == 1 and now.month in (1, 4, 7, 10) and last_quarterly != now.month:
                last_quarterly = now.month
                self._run_quarterly()

            time.sleep(60)  # check every minute

    def _run_daily(self):
        """Daily tasks: drift detection, AIM lifecycle, warmup check."""
        logger.info("Running daily offline tasks...")
        self.plog.info("Daily offline tasks starting (drift, lifecycle, warmup)", source="scheduler")
        write_checkpoint("OFFLINE", "DAILY_CLOSE", "starting", "drift_lifecycle_warmup")

        try:
            from captain_offline.blocks.b1_aim_lifecycle import run_aim_lifecycle
            from captain_offline.blocks.b1_drift_detection import run_drift_detection
            from captain_offline.blocks.bootstrap import asset_warmup_check

            # Get active assets
            from shared.questdb_client import get_cursor
            with get_cursor() as cur:
                cur.execute("SELECT asset_id FROM p3_d00_asset_universe WHERE captain_status IN ('ACTIVE', 'WARM_UP')")
                assets = [r[0] for r in cur.fetchall()]

            for asset_id in assets:
                run_aim_lifecycle(asset_id)
                # Load AIM modifier values from D01 as feature vectors
                with get_cursor() as cur:
                    cur.execute(
                        """SELECT aim_id, current_modifier
                           FROM p3_d01_aim_model_states
                           WHERE asset_id = %s
                           LATEST ON last_updated PARTITION BY aim_id, asset_id""",
                        (asset_id,),
                    )
                    aim_rows = cur.fetchall()
                aim_features = {}
                for r in aim_rows:
                    if r[1]:
                        try:
                            modifier = json.loads(r[1])
                            if isinstance(modifier, dict) and modifier:
                                aim_features[r[0]] = list(modifier.values())
                        except (json.JSONDecodeError, TypeError):
                            pass
                run_drift_detection(asset_id, aim_features)

            asset_warmup_check()

            # Advance any active strategy transitions
            self._advance_transitions()

            # Dispatch any pending jobs (Level 3 triggers, etc.)
            self._dispatch_pending_jobs()

        except Exception as e:
            logger.error("Daily tasks error: %s", e, exc_info=True)

        write_checkpoint("OFFLINE", "DAILY_COMPLETE", "daily_done", "waiting")

    def _run_weekly(self):
        """Weekly tasks: Tier 1 AIM retrain, HDWM diversity, diagnostic."""
        logger.info("Running weekly offline tasks...")
        self.plog.info("Weekly offline tasks starting (retrain, HDWM, diagnostic)", source="scheduler")

        try:
            from captain_offline.blocks.b1_aim_lifecycle import run_tier_retrain, TIER_1_AIMS
            from captain_offline.blocks.b1_hdwm_diversity import run_hdwm_diversity_check
            from captain_offline.blocks.b9_diagnostic import run_diagnostic
            from shared.questdb_client import get_cursor

            with get_cursor() as cur:
                cur.execute("SELECT asset_id FROM p3_d00_asset_universe WHERE captain_status = 'ACTIVE'")
                assets = [r[0] for r in cur.fetchall()]

            # 1. Tier 1 AIM retrain (spec: Weekly)
            for asset_id in assets:
                run_tier_retrain(asset_id, TIER_1_AIMS)

            # 2. HDWM diversity check
            for asset_id in assets:
                run_hdwm_diversity_check(asset_id)

            # 3. System health diagnostic
            run_diagnostic(mode="WEEKLY")

        except Exception as e:
            logger.error("Weekly tasks error: %s", e, exc_info=True)

    def _run_monthly(self):
        """Monthly tasks: Tier 2/3 AIM retrain, sensitivity scan, diagnostic."""
        logger.info("Running monthly offline tasks...")

        try:
            from captain_offline.blocks.b1_aim_lifecycle import run_tier_retrain, TIER_23_AIMS
            from captain_offline.blocks.b5_sensitivity import run_sensitivity_scan
            from captain_offline.blocks.b9_diagnostic import run_diagnostic
            from shared.questdb_client import get_cursor

            # Get active assets
            with get_cursor() as cur:
                cur.execute(
                    "SELECT asset_id FROM p3_d00_asset_universe WHERE captain_status = 'ACTIVE'"
                )
                assets = [r[0] for r in cur.fetchall()]

            # 1. Tier 2/3 AIM retrain (spec: Monthly)
            for asset_id in assets:
                run_tier_retrain(asset_id, TIER_23_AIMS)

            # 2. Sensitivity scan for each active asset
            for asset_id in assets:
                with get_cursor() as cur:
                    cur.execute(
                        """SELECT pnl, contracts FROM p3_d03_trade_outcome_log
                           WHERE asset = %s ORDER BY ts DESC LIMIT 252""",
                        (asset_id,),
                    )
                    rows = cur.fetchall()
                # Per-contract daily returns for recent OOS window
                returns = [
                    r[0] / max(r[1], 1) for r in rows if r[1] and r[1] > 0
                ]
                if len(returns) >= 30:
                    run_sensitivity_scan(asset_id, returns)
                    logger.info("Sensitivity scan completed for %s (%d returns)",
                                asset_id, len(returns))

            run_diagnostic(mode="MONTHLY")

        except Exception as e:
            logger.error("Monthly tasks error: %s", e, exc_info=True)

    def _run_quarterly(self):
        """Quarterly tasks: CUSUM recalibration."""
        logger.info("Running quarterly offline tasks...")

        try:
            from captain_offline.blocks.b2_cusum import calibrate_and_persist
            from shared.questdb_client import get_cursor

            with get_cursor() as cur:
                cur.execute("SELECT asset_id FROM p3_d00_asset_universe WHERE captain_status = 'ACTIVE'")
                assets = [r[0] for r in cur.fetchall()]

            for asset_id in assets:
                # Load in-control returns for calibration
                with get_cursor() as cur:
                    cur.execute(
                        "SELECT pnl, contracts FROM p3_d03_trade_outcome_log WHERE asset = %s",
                        (asset_id,),
                    )
                    rows = cur.fetchall()
                returns = [r[0] / max(r[1], 1) for r in rows if r[1] and r[1] > 0]
                if len(returns) >= 20:
                    calibrate_and_persist(asset_id, returns)

        except Exception as e:
            logger.error("Quarterly tasks error: %s", e, exc_info=True)
