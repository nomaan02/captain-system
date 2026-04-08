# Captain Offline Audit

## Part 1: Orchestrator + B1-B2

**Auditor:** Claude Opus 4.6 (Session 4a of 8)
**Date:** 2026-04-08
**Scope:** captain-offline main.py, orchestrator, bootstrap, version_snapshot, B1 blocks (AIM lifecycle, HMM, DMA, drift, HDWM), B2 blocks (BOCPD, CUSUM, level escalation)

---

### File: captain-offline/captain_offline/main.py

- **Purpose:** Entry point for Captain Offline process — connects QuestDB/Redis, seeds AIM states, registers signal handlers, launches orchestrator.
- **Key functions/classes:**
  - `_seed_aim_states()` :42 — idempotent D01 seeder for all 16 AIMs across all D00 assets
  - `main()` :99 — startup sequence: QuestDB verify → Redis verify → consumer groups → crash recovery check → AIM seed → orchestrator start
  - `shutdown_handler()` :142 — SIGTERM/SIGINT handler, calls `orchestrator.stop()`
- **Session/schedule refs:** None (startup-only)
- **QuestDB:**
  - `p3_d00_asset_universe` — SELECT asset_id :54
  - `p3_d01_aim_model_states` — SELECT existing pairs :63, INSERT new rows :76-90
- **Redis:**
  - `STREAM_TRADE_OUTCOMES` / `GROUP_OFFLINE_OUTCOMES` — consumer group init :121
  - `STREAM_COMMANDS` / `GROUP_OFFLINE_COMMANDS` — consumer group init :122
- **Stubs/TODOs:** None
- **Notable:**
  - `AlgorithmImports` try/except block at top of every file — QuantConnect compatibility shim, dead code in Docker context
  - Retry logic on QuestDB insert :82-91 uses bare `except Exception` with 0.5s sleep — swallows the original error silently on first failure
  - `TIER1_AIMS` defined here AND in bootstrap.py AND in b1_aim_lifecycle.py (3 duplications)
  - `NUM_AIMS = 16` hardcoded here AND in b1_aim_lifecycle.py (2 duplications)

---

### File: captain-offline/captain_offline/blocks/orchestrator.py

- **Purpose:** Event-driven orchestrator — Redis listener + time-based scheduler dispatching to all Offline blocks.
- **Key functions/classes:**
  - `OfflineOrchestrator` :44 — main class
  - `start()` :52 — resume transitions, start Redis thread, run scheduler
  - `stop()` :69 — set `running = False`
  - `_redis_listener()` :73 — daemon thread: reads 3 streams with consumer groups
  - `_handle_trade_outcome()` :120 — DMA → BOCPD → CUSUM → level escalation → Kelly → CB → TSM (Category A + B)
  - `_handle_signal_outcome()` :174 — DMA → BOCPD → CUSUM → level escalation → Kelly (Category A only, no CB/TSM)
  - `_handle_command()` :231 — dispatches ASSET_ADDED, INJECTION, ADOPTION_DECISION, TSM_CHANGE, ACTIVATE/DEACTIVATE_AIM, ACTION_RESOLVED
  - `_run_scheduler()` :521 — `while running` loop checking time every 60s
  - `_run_daily()` :553 — drift detection, AIM lifecycle, warmup check, advance transitions, dispatch jobs
  - `_run_weekly()` :587 — Tier 1 AIM retrain, HDWM diversity, diagnostic
  - `_run_monthly()` :615 — Tier 2/3 AIM retrain, sensitivity scan, diagnostic
  - `_run_quarterly()` :659 — CUSUM recalibration
  - `_dispatch_pending_jobs()` :368 — processes `p3_offline_job_queue` (AIM14_EXPANSION, P1P2_RERUN)
  - `_run_aim14_expansion()` :441 — loads trade history, splits 80/20, calls `run_auto_expansion`
  - `_run_tsm_for_account()` :467 — loads TSM config + trade returns, runs Monte Carlo
- **Session/schedule refs:**
  - Daily: `now.hour >= 16` (after market close) :532
  - Weekly: Monday (`weekday() == 0`) :537
  - Monthly: 1st of month :542
  - Quarterly: 1st of Jan/Apr/Jul/Oct :547
- **QuestDB:**
  - `p3_d00_asset_universe` — SELECT active/warmup assets :566, active assets :598, :628, :668
  - `p3_d01_aim_model_states` — SELECT for AIM activation :312
  - `p3_d03_trade_outcome_log` — SELECT pnl for AIM-14 :449, monthly sensitivity :640, quarterly CUSUM :675, TSM :506
  - `p3_d08_tsm_state` — SELECT TSM config :480
  - `p3_offline_job_queue` — SELECT pending :378, INSERT status updates :396, :429
- **Redis:**
  - `STREAM_TRADE_OUTCOMES` / `GROUP_OFFLINE_OUTCOMES` — read :90
  - `STREAM_SIGNAL_OUTCOMES` / `GROUP_OFFLINE_SIGNAL_OUTCOMES` — read :98
  - `STREAM_COMMANDS` / `GROUP_OFFLINE_COMMANDS` — read :106
- **Stubs/TODOs:** None
- **Category A vs B:**
  - `_handle_trade_outcome` = Category A + B (all blocks including CB/TSM)
  - `_handle_signal_outcome` = Category A only (DMA, BOCPD, CUSUM, Kelly — no CB/TSM)
  - Correctly documented in docstring :176-182
- **Notable:**
  - **Timezone issue (FINDING-01):** `_run_scheduler()` uses `datetime.now()` :529 which returns LOCAL system time. Spec requires America/New_York for all timestamps. If container TZ differs, daily trigger at `hour >= 16` fires at wrong time. Should use `datetime.now(ZoneInfo("America/New_York"))`.
  - **Drift detection called with empty dict (FINDING-02):** `run_drift_detection(asset_id, {})` :572 — always passes empty features. The function iterates `aim_features.items()` so this is a no-op. Drift detection never actually runs.
  - **Lazy imports inside hot paths:** Every trade outcome triggers 7 lazy imports :133-167. These are cached by Python after first load but still incur dict lookup overhead on every call.
  - **No graceful drain on stop (FINDING-03):** `stop()` sets `running = False` but doesn't join the Redis listener thread or wait for in-flight trade outcomes to complete. A trade outcome being processed when SIGTERM arrives could be interrupted mid-write.
  - **Job queue uses INSERT-as-update pattern:** QuestDB is append-only, so job status "updates" :396-435 create new rows. Readers must use `ORDER BY last_updated DESC LIMIT 1` to get correct status.
  - **Scheduler check interval:** 60s sleep :551 means daily/weekly/monthly tasks can fire up to 60s late. Acceptable for this use case.

---

### File: captain-offline/captain_offline/blocks/bootstrap.py

- **Purpose:** Asset bootstrap from P1/P2 historical trades and daily warmup-to-active transition check.
- **Key functions/classes:**
  - `asset_bootstrap()` :80 — init EWMA (D05), BOCPD/CUSUM (D04), Kelly (D12), Tier 1 AIM status (D01)
  - `asset_warmup_check()` :214 — check 4 conditions: EWMA baseline, Tier 1 AIMs, regime model, P1/P2 validated
  - `_load_locked_strategy()` :36 — load from D00 (currently unused within this file)
  - `_compute_unconditional()` :64 — compute EWMA stats from returns
  - `_derive_session()` :51 — map timezone to session ID
- **Session/schedule refs:** `asset_warmup_check()` called daily from orchestrator :574
- **QuestDB:**
  - `p3_d00_asset_universe` — SELECT locked_strategy :39, exchange_timezone :106, warmup assets :224
  - `p3_d01_aim_model_states` — SELECT/INSERT AIM status :193-208, warmup check :249
  - `p3_d04_decay_detector_states` — INSERT bootstrap BOCPD/CUSUM :149
  - `p3_d05_ewma_states` — INSERT EWMA per regime/session :132, SELECT for Kelly :163
  - `p3_d12_kelly_parameters` — INSERT initial Kelly :183
- **Redis:** None
- **Stubs/TODOs:** None
- **Notable:**
  - `TIER1_AIMS` defined as list `[4, 6, 8, 11, 12, 15]` :32 — third copy (also in main.py as set, b1_aim_lifecycle.py as list)
  - `_load_locked_strategy()` :36 is defined but never called within this file (dead code locally, though it may be used externally)
  - **Session filtering simplified (FINDING-04):** :122 `session == default_session` means only one session bucket gets regime-filtered data, others get unconditional fallback. Works but loses per-session granularity for multi-session assets (e.g., NKD on APAC).
  - `warmup_check` :285 uses `checks.index(False)` which would throw ValueError if all checks are True, but that branch is unreachable due to the `if all(checks)` guard above.

---

### File: captain-offline/captain_offline/blocks/version_snapshot.py

- **Purpose:** Versioning policy — saves component state snapshots to P3-D18 before any mutation.
- **Key functions/classes:**
  - `snapshot_before_update()` :51 — save state snapshot, return version_id UUID
  - `get_latest_version()` :82 — retrieve most recent snapshot for a component
  - `_compute_hash()` :45 — SHA-256 integrity hash
- **Session/schedule refs:** None (called on-demand before mutations)
- **QuestDB:**
  - `p3_d18_version_history` — INSERT :72, SELECT :86
- **Redis:** None
- **Stubs/TODOs:** None
- **Notable:**
  - `MAX_VERSIONS_PER_COMPONENT = 50` :24 defined but never enforced — no pruning logic exists. Hot storage will grow unbounded.
  - `get_latest_version()` is defined but never called anywhere in the audited files — potential dead code unless used by diagnostic or external tooling.

---

### File: captain-offline/captain_offline/blocks/b1_aim_lifecycle.py

- **Purpose:** AIM state machine: INSTALLED → COLLECTING → WARM_UP → ELIGIBLE → ACTIVE, with suppression/recovery. Dual warm-up gates (DEC-05): feature gate + learning gate.
- **Key functions/classes:**
  - `run_aim_lifecycle()` :204 — process all 16 AIMs for an asset through state machine
  - `run_tier_retrain()` :314 — scheduled retrain for ACTIVE/BOOTSTRAPPED AIMs
  - `feature_warmup_days()` :160 — per-AIM feature gate days (from AIM_Extractions.md)
  - `learning_warmup_required()` :187 — per-AIM learning gate trades
  - `warmup_required()` :199 — **DEPRECATED** wrapper
  - `_load_aim_states()` :47 — load from D01
  - `_load_meta_weight()` :74 — load inclusion_probability from D02
  - `_load_meta_weight_history()` :374 — load days_below_threshold for suppression/recovery
  - `_update_aim_status()` :87 — write status to D01
  - `_update_warmup_progress()` :98 — write to D01 + D00
  - `data_pipeline_connected()` :117 — simplified: just checks asset exists in D00
  - `observations_collected()` :132 — count trade outcomes in D03
  - `feature_days_accumulated()` :143 — count distinct trading days
- **Session/schedule refs:** Called daily from `_run_daily()` :570, weekly via `run_tier_retrain` :602-603
- **QuestDB:**
  - `p3_d01_aim_model_states` — SELECT :50, INSERT :91, :104, :355
  - `p3_d02_aim_meta_weights` — SELECT :78, :381
  - `p3_d00_asset_universe` — SELECT :125, UPDATE via `update_d00_fields` :114
  - `p3_d03_trade_outcome_log` — SELECT count :136, distinct dates :152
- **Redis:** None
- **Stubs/TODOs:**
  - `data_pipeline_connected()` :117-129 — simplified stub, always returns True if asset in universe
  - Retrain placeholder :351-353 — comment about future AIM trainer registry
  - `warmup_required()` :199 — deprecated function kept for backward compatibility
- **Category A vs B:** Lifecycle state changes apply to ALL signals (learned from trade outcome counts which include theoretical).
- **Notable:**
  - **`_load_aim_states` ordering issue (FINDING-05):** Query at :55 uses `ORDER BY aim_id, last_updated DESC` but QuestDB doesn't guarantee this ordering for append-only tables without `LATEST ON`. The dedup logic at :218-222 takes first occurrence per aim_id, which could be stale.
  - `_load_meta_weight_history()` :374-391 uses a **simplified heuristic** for recovery: if `days_below > 0` then `consecutive_above = 0`, else `10`. This means recovery always triggers immediately when weight rises above threshold — no real 10-trade window tracked.
  - `AIM_STATUS_VALUES` imported from `shared.constants` :31 but never used in this file.
  - `NUM_AIMS = 16` :37 — second copy (also in main.py)

---

### File: captain-offline/captain_offline/blocks/b1_aim16_hmm.py

- **Purpose:** Train 3-state HMM (LOW_OPP / NORMAL / HIGH_OPP) on session observations for AIM-16 opportunity regime classification.
- **Key functions/classes:**
  - `train_aim16_hmm()` :203 — main training function with cold-start logic
  - `save_hmm_state()` :292 — persist to P3-D26
  - `_baum_welch()` :89 — Baum-Welch EM algorithm
  - `_gaussian_emission()` :80 — diagonal Gaussian emission probability
  - `_initialize_from_labels()` :52 — supervised init from PnL percentiles
  - `_label_from_pnl()` :193 — assign labels based on P25/P75
- **Session/schedule refs:** Not directly scheduled — called from AIM lifecycle/retrain
- **QuestDB:**
  - `p3_d26_hmm_opportunity_state` — INSERT :296
- **Redis:** None
- **Stubs/TODOs:** None
- **Notable:**
  - **Custom HMM instead of hmmlearn (FINDING-06):** `hmmlearn>=0.3` is in requirements.txt but never imported. Instead, a full hand-rolled Baum-Welch implementation exists here (~200 lines). Either use `hmmlearn` or remove it from requirements.
  - **O(T*K^2) nested loops (FINDING-07):** Forward-backward at :113-155 and the final forward pass at :248-254 use pure Python triple-nested loops. For T=240, K=3 this is ~2160 iterations per pass — acceptable now but won't scale if K or T grow.
  - Cold-start blending at :266-272 modifies `current_state_probs` AFTER the variable `opp_weight_raw` was already computed from unblended values at :262. `opp_weight_raw` is unused after that — no bug, but misleading.

---

### File: captain-offline/captain_offline/blocks/b1_dma_update.py

- **Purpose:** Dynamic Model Averaging — update AIM inclusion probabilities after each trade outcome using magnitude-weighted likelihood (SPEC-A9).
- **Key functions/classes:**
  - `run_dma_update()` :130 — main entry point
  - `_compute_likelihood()` :98 — magnitude-weighted likelihood computation
  - `_load_active_aims()` :40 — load current weights from D02
  - `_load_ewma_regime()` :66 — load regime-level EWMA stats
- **Session/schedule refs:** Called on every trade/signal outcome from orchestrator :134, :195
- **QuestDB:**
  - `p3_d02_aim_meta_weights` — SELECT :43, INSERT :201
  - `p3_d05_ewma_states` — SELECT :73
- **Redis:** None
- **Stubs/TODOs:** None
- **Category A vs B:** Category A — learns from ALL signals (both real trades and theoretical).
- **Notable:**
  - **`_load_active_aims` dedup logic (FINDING-08):** :53-56 iterates rows in `ORDER BY aim_id` and takes first unseen aim_id. Without `LATEST ON` or `ORDER BY last_updated DESC`, this may not pick the latest row per AIM in QuestDB's append-only model.
  - Forgetting factor `DEFAULT_LAMBDA = 0.99` :31 matches spec. Configurable via parameter but no D17 lookup implemented yet.
  - DMA formula at :177 is `(prob^lambda) * likelihood` — matches spec correctly.

---

### File: captain-offline/captain_offline/blocks/b1_drift_detection.py

- **Purpose:** Per-AIM concept drift detection using AutoEncoder reconstruction error monitored by ADWIN. On drift: reduce weight 50%, renormalize.
- **Key functions/classes:**
  - `run_drift_detection()` :168 — daily entry point
  - `ADWINDetector` :36 — wrapper around `river.drift.ADWIN` with fallback
  - `SimpleAutoEncoder` :84 — mean/std-based reconstruction error (placeholder)
  - `_renormalise_weights()` :133 — renormalize all AIM weights after drift reduction
  - `_get_adwin()` :119, `_get_autoencoder()` :126 — in-memory state accessors
- **Session/schedule refs:** Called daily from `_run_daily()` :572
- **QuestDB:**
  - `p3_d02_aim_meta_weights` — SELECT :138, INSERT :159, :207
- **Redis:** None
- **Stubs/TODOs:**
  - `SimpleAutoEncoder` :84-110 — placeholder for real neural autoencoder
  - `_adwin_states` / `_autoencoder_states` :115-116 — in-memory only, comment says "in production, persist to P3-D04"
- **Notable:**
  - **Effectively dead (FINDING-02 confirmed):** Orchestrator calls `run_drift_detection(asset_id, {})` — empty dict means the `for aim_id, features in aim_features.items()` loop :177 never executes. Feature extraction pipeline not wired.
  - **`river` not in requirements.txt (FINDING-09):** `b1_drift_detection.py` :49 imports `river.drift.ADWIN` at runtime. `river` is NOT listed in `captain-offline/requirements.txt`. The fallback detector :55-81 handles this but the primary path is never available in Docker.
  - **Module-level mutable state (FINDING-10):** `_adwin_states` and `_autoencoder_states` :115-116 are module-level dicts. Not persisted across container restarts. Lost on every deploy.
  - `_renormalise_weights` :146-148 dedup comment says "take first = latest due to QuestDB ordering" but QuestDB doesn't guarantee this without explicit ordering.

---

### File: captain-offline/captain_offline/blocks/b1_hdwm_diversity.py

- **Purpose:** Weekly diversity maintenance — if all AIMs in a seed type are SUPPRESSED, force-reactivate the one with highest recent_effectiveness.
- **Key functions/classes:**
  - `run_hdwm_diversity_check()` :93 — main entry point
  - `_reactivate_aim()` :71 — set ACTIVE status + equal weight
  - `_get_aim_status()` :33, `_get_recent_effectiveness()` :46 — D01/D02 lookups
  - `_count_active_aims()` :59 — count ACTIVE AIMs
  - `SEED_TYPES` :22 — 6 seed type groups (15 AIMs, AIM-16 excluded)
- **Session/schedule refs:** Called weekly from `_run_weekly()` :607
- **QuestDB:**
  - `p3_d01_aim_model_states` — SELECT :37, :63, INSERT :78
  - `p3_d02_aim_meta_weights` — SELECT :50, INSERT :84
- **Redis:** None
- **Stubs/TODOs:** None
- **Notable:**
  - Well-structured and focused. AIM-16 correctly excluded from seed types :29.
  - `_count_active_aims` at :59 counts ALL rows with status='ACTIVE', not just latest per AIM. In QuestDB's append-only model this could overcount. Should use distinct aim_id count or dedup.

---

### File: captain-offline/captain_offline/blocks/b2_bocpd.py

- **Purpose:** Bayesian Online Changepoint Detection — maintains run-length posterior, outputs changepoint probability per trade.
- **Key functions/classes:**
  - `BOCPDDetector` :71 — main detector class
  - `BOCPDDetector.update()` :93 — core Adams & MacKay recursion
  - `BOCPDDetector.to_dict()` / `from_dict()` :142-156 — serialization
  - `run_bocpd_update()` :159 — entry point, persists to D04
  - `_student_t_pdf()` :48 — Student-t predictive probability
  - `_update_nig()` :62 — Normal-Inverse-Gamma update
  - `NIGPrior` :40 — dataclass for NIG sufficient stats
- **Session/schedule refs:** Called on every trade/signal outcome from orchestrator :137-140, :199-202
- **QuestDB:**
  - `p3_d04_decay_detector_states` — INSERT :178
- **Redis:** None
- **Stubs/TODOs:** None
- **Category A vs B:** Category A — learns from ALL signals.
- **Notable:**
  - **Memory: O(max_run_length) priors (FINDING-11):** `self.priors` :80 maintains 501 NIGPrior objects. Lightweight (4 floats each, ~16KB), but the list is recreated on every `update()` call :128-133.
  - `from_dict()` :151-156 restores only `cp_probability` and `cp_history` — the NIG priors and run_length_posterior are NOT restored. A detector loaded from persistence starts with fresh priors, losing learned distribution parameters.
  - `cp_history` capped at 100 entries :183 — good memory management.
  - Clean implementation of the Adams & MacKay algorithm.

---

### File: captain-offline/captain_offline/blocks/b2_cusum.py

- **Purpose:** Two-sided CUSUM with bootstrap-calibrated sequential control limits. Complementary to BOCPD for mean-shift detection.
- **Key functions/classes:**
  - `CUSUMDetector` :35 — two-sided CUSUM detector
  - `CUSUMDetector.update()` :53 — per-trade update, returns BREACH/OK
  - `calibrate_cusum_limits()` :100 — P3-PG-07 bootstrap calibration (B=2000, ARL_0=200)
  - `calibrate_and_persist()` :157 — calibrate + save to D04
  - `run_cusum_update()` :182 — entry point, persists to D04
- **Session/schedule refs:** `calibrate_and_persist` called quarterly from `_run_quarterly()` :681
- **QuestDB:**
  - `p3_d04_decay_detector_states` — INSERT :171, :199
- **Redis:** None
- **Stubs/TODOs:** None
- **Category A vs B:** Category A — learns from ALL signals.
- **Notable:**
  - **Bootstrap calibration uses `random.choices` (FINDING-12):** :128 uses `random.choices(in_control_pnl, k=n)` — sampling WITH replacement, which is correct for bootstrap but not seeded. Results differ across runs. Consider using `np.random.default_rng()` with a fixed seed for reproducibility.
  - CUSUM allowance formula `k = std/2` :51 matches spec.
  - Clean separation between per-trade updates (PG-06) and quarterly calibration (PG-07).

---

### File: captain-offline/captain_offline/blocks/b2_level_escalation.py

- **Purpose:** Decay escalation: Level 2 (sizing reduction) and Level 3 (halt + P1/P2 rerun + AIM-14 expansion) triggered by BOCPD/CUSUM signals.
- **Key functions/classes:**
  - `check_level_escalation()` :173 — entry point called after every BOCPD+CUSUM update
  - `trigger_level2()` :109 — sizing reduction (factor from 1.0 to 0.5)
  - `trigger_level3()` :149 — halt signals, enqueue P1/P2 rerun + AIM-14 jobs
  - `_compute_reduction_factor()` :42 — reduction formula
  - `_set_sizing_override()` :72 — write to D12
  - `_set_captain_status_decayed()` :85 — write DECAYED to D00
  - `_enqueue_job()` :126 — add job to `p3_offline_job_queue`
  - `_publish_alert()` :91 — publish to Redis `captain:alerts`
  - `_log_decay_event()` :54 — append decay event to D04
- **Session/schedule refs:** Called on every trade/signal outcome (via orchestrator :152, :214)
- **QuestDB:**
  - `p3_d04_decay_detector_states` — INSERT :65
  - `p3_d12_kelly_parameters` — INSERT :77
  - `p3_d00_asset_universe` — UPDATE via `update_d00_fields` :88
  - `p3_offline_job_queue` — INSERT :138
- **Redis:**
  - `CH_ALERTS` (`captain:alerts`) — PUBLISH :104
- **Stubs/TODOs:** None
- **Category A vs B:** Escalation runs on ALL signals (triggered by BOCPD/CUSUM which are Category A).
- **Notable:**
  - **Level 2 fires on every threshold exceedance (FINDING-13):** `check_level_escalation` :186-187 triggers Level 2 EVERY time `cp_probability > 0.8`. No debouncing or cooldown. If cp_prob stays at 0.85 for 10 trades, Level 2 fires 10 times, writing 10 sizing overrides, 10 decay events, 10 alerts.
  - **Level 2 can fire alongside Level 3 (FINDING-14):** No `return` or `elif` between Level 2 check :186 and Level 3 check :194. If cp_prob > 0.9 sustained, both levels fire simultaneously.
  - `_set_sizing_override` :77-82 writes `kelly_full=0.0` with `regime='ALL', session=0` — this creates a special "override" row that downstream must know to check. The pattern isn't documented.

---

## Findings Summary

### Critical / High

| ID | Severity | File | Line | Finding |
|----|----------|------|------|---------|
| FINDING-01 | HIGH | orchestrator.py | 529 | `datetime.now()` uses system TZ, not America/New_York. Scheduler triggers at wrong time if container TZ differs. |
| FINDING-02 | HIGH | orchestrator.py | 572 | Drift detection called with empty features dict — function is a no-op. Feature extraction not wired. |
| FINDING-05 | HIGH | b1_aim_lifecycle.py | 55 | `_load_aim_states` ORDER BY doesn't guarantee latest row per AIM in QuestDB append-only model. |
| FINDING-08 | HIGH | b1_dma_update.py | 43-56 | `_load_active_aims` same issue — may read stale weights without LATEST ON or DESC ordering. |
| FINDING-13 | HIGH | b2_level_escalation.py | 186 | Level 2 fires on every trade with cp_prob > 0.8 — no debounce. Creates alert/DB spam. |

### Medium

| ID | Severity | File | Line | Finding |
|----|----------|------|------|---------|
| FINDING-03 | MEDIUM | orchestrator.py | 69 | No graceful drain — stop() doesn't join Redis thread or wait for in-flight processing. |
| FINDING-04 | MEDIUM | bootstrap.py | 122 | Session filtering simplified — only default_session gets regime-filtered data. |
| FINDING-06 | MEDIUM | b1_aim16_hmm.py | all | `hmmlearn` in requirements.txt but never used; full hand-rolled HMM instead. |
| FINDING-09 | MEDIUM | b1_drift_detection.py | 49 | `river` package imported but NOT in requirements.txt. Fallback always used. |
| FINDING-10 | MEDIUM | b1_drift_detection.py | 115-116 | ADWIN/autoencoder state in module-level dicts — lost on container restart. |
| FINDING-14 | MEDIUM | b2_level_escalation.py | 186-197 | Level 2 and Level 3 can fire simultaneously — no mutual exclusion. |

### Low

| ID | Severity | File | Line | Finding |
|----|----------|------|------|---------|
| FINDING-07 | LOW | b1_aim16_hmm.py | 113 | O(T*K^2) Python loops — fine for K=3,T=240 but won't scale. |
| FINDING-11 | LOW | b2_bocpd.py | 80 | 501 NIG priors recreated per update — lightweight but wasteful. |
| FINDING-12 | LOW | b2_cusum.py | 128 | Bootstrap calibration not seeded — non-reproducible across runs. |

### Dependencies & Reuse

| Finding | Details |
|---------|---------|
| Unused dep: `hmmlearn>=0.3` | Listed in requirements.txt but never imported. Custom Baum-Welch used instead. |
| Unused dep: `scikit-learn>=1.3` | Listed in requirements.txt, no imports found in any audited file. |
| Unused dep: `pydantic>=2.0` | Listed in requirements.txt, no imports found in any audited file. |
| Missing dep: `river` | Used in b1_drift_detection.py but not in requirements.txt. Fallback masks the gap. |
| Duplicate constant: `TIER1_AIMS` | Defined in main.py :39 (set), bootstrap.py :32 (list), b1_aim_lifecycle.py :308 (list). Should be in shared/constants.py. |
| Duplicate constant: `NUM_AIMS` | Defined in main.py :38 and b1_aim_lifecycle.py :37. Should be in shared/constants.py. |
| QuantConnect shim: `AlgorithmImports` | Try/except in all 22 files. Dead code in Docker — QuantConnect runs are not part of this repo. |

### Dead Code

| Item | File | Line | Notes |
|------|------|------|-------|
| `AlgorithmImports` try/except | All 12 files | :1-6 | QuantConnect shim — unreachable in Docker |
| `_load_locked_strategy()` | bootstrap.py | 36 | Defined but never called in this file |
| `warmup_required()` | b1_aim_lifecycle.py | 199 | Deprecated wrapper, kept for backward compat |
| `AIM_STATUS_VALUES` import | b1_aim_lifecycle.py | 31 | Imported but never used |
| `get_latest_version()` | version_snapshot.py | 82 | Not called in any audited file |
| `MAX_VERSIONS_PER_COMPONENT` | version_snapshot.py | 24 | Defined but pruning never implemented |
| Drift detection in practice | b1_drift_detection.py | all | Module exists but orchestrator feeds it empty data |
| `opp_weight_raw` | b1_aim16_hmm.py | 262 | Computed but never used |

---

## Scheduled Tasks Inventory

| Task | Trigger | Timing | Orchestrator Method |
|------|---------|--------|---------------------|
| Drift detection | Daily | After 16:00 (system TZ) | `_run_daily()` :571-572 |
| AIM lifecycle | Daily | After 16:00 | `_run_daily()` :570 |
| Warmup check | Daily | After 16:00 | `_run_daily()` :574 |
| Transition advance | Daily | After 16:00 | `_run_daily()` :577 |
| Job dispatch | Daily | After 16:00 | `_run_daily()` :580 |
| Tier 1 AIM retrain | Weekly | Monday | `_run_weekly()` :602 |
| HDWM diversity | Weekly | Monday | `_run_weekly()` :607 |
| Weekly diagnostic | Weekly | Monday | `_run_weekly()` :610 |
| Tier 2/3 AIM retrain | Monthly | 1st of month | `_run_monthly()` :633 |
| Sensitivity scan | Monthly | 1st of month | `_run_monthly()` :637 |
| Monthly diagnostic | Monthly | 1st of month | `_run_monthly()` :654 |
| CUSUM recalibration | Quarterly | 1st of Jan/Apr/Jul/Oct | `_run_quarterly()` :664 |

## Event Handler Inventory

| Stream/Channel | Event | Handler | Action |
|----------------|-------|---------|--------|
| `stream:trade_outcomes` | trade outcome | `_handle_trade_outcome()` | DMA + BOCPD + CUSUM + level escalation + Kelly + CB + TSM |
| `stream:signal_outcomes` | theoretical outcome | `_handle_signal_outcome()` | DMA + BOCPD + CUSUM + level escalation + Kelly (Category A only) |
| `stream:commands` | ASSET_ADDED | `_handle_asset_added()` | `asset_bootstrap()` |
| `stream:commands` | INJECTION | `_handle_injection()` | `run_injection_comparison()` |
| `stream:commands` | ADOPTION_DECISION | `_handle_adoption()` | Create/persist TransitionPhaser |
| `stream:commands` | TSM_CHANGE | `_run_tsm_for_account()` | TSM Monte Carlo simulation |
| `stream:commands` | ACTIVATE_AIM/DEACTIVATE_AIM | `_handle_aim_activation()` | Update D01 status for all assets |
| `stream:commands` | ACTION_RESOLVED | `run_diagnostic("WEEKLY")` | D8 verification diagnostic |

## Cross-Service Dependencies

**QuestDB tables read:**
- `p3_d00_asset_universe` (assets, status, strategy, timezone)
- `p3_d01_aim_model_states` (AIM status, warmup)
- `p3_d02_aim_meta_weights` (DMA weights, effectiveness)
- `p3_d03_trade_outcome_log` (PnL, contracts, regime)
- `p3_d05_ewma_states` (win rate, avg win/loss)
- `p3_d08_tsm_state` (TSM config per account)

**QuestDB tables written:**
- `p3_d01_aim_model_states` (status transitions)
- `p3_d02_aim_meta_weights` (DMA updates)
- `p3_d04_decay_detector_states` (BOCPD, CUSUM, decay events)
- `p3_d05_ewma_states` (bootstrap init)
- `p3_d12_kelly_parameters` (bootstrap, sizing override)
- `p3_d18_version_history` (snapshots)
- `p3_d26_hmm_opportunity_state` (HMM state)
- `p3_offline_job_queue` (Level 3 jobs)

**Redis streams consumed:**
- `stream:trade_outcomes` (group: `offline_trade_outcomes`)
- `stream:signal_outcomes` (group: `offline_signal_outcomes`)
- `stream:commands` (group: `offline_commands`)

**Redis channels published:**
- `captain:alerts` (decay alerts from level_escalation)

---

## Session 4a Summary

- **Files audited:** 12
- **Key findings:** 14 total (5 HIGH, 6 MEDIUM, 3 LOW)
  1. Scheduler uses system TZ, not America/New_York (HIGH)
  2. Drift detection is a no-op — empty features passed (HIGH)
  3. QuestDB queries missing LATEST ON for dedup (HIGH, 2 instances)
  4. Level 2 escalation fires every trade without debounce (HIGH)
  5. No graceful drain on shutdown (MEDIUM)
  6. `hmmlearn` unused, `river` missing from requirements (MEDIUM, 2 dep issues)
  7. In-memory drift state not persisted (MEDIUM)
  8. Level 2/3 can fire simultaneously (MEDIUM)
  9. Bootstrap session filtering simplified (MEDIUM)
  10. Bootstrap non-reproducible (LOW)
- **Stub count:** 5 (drift autoencoder, drift state persistence, AIM retrain hook, data_pipeline_connected, version pruning)
- **Dead code:** 8 items (AlgorithmImports shim x12 files, 5 unused functions/constants, drift module effectively dead, unused variable)
- **Dependency issues:** 3 unused deps (hmmlearn, scikit-learn, pydantic), 1 missing dep (river), 2 duplicate constants (TIER1_AIMS x3, NUM_AIMS x2)
- **Scheduled tasks:** 12 periodic tasks across daily/weekly/monthly/quarterly
- **Event handlers:** 8 event types across 3 Redis streams
- **Cross-service deps:** 8 QuestDB tables read, 8 written, 3 Redis streams consumed, 1 channel published

---

## Part 2: B3-B9

**Auditor:** Claude Opus 4.6 (Session 4b of 8)
**Date:** 2026-04-08
**Scope:** Pseudotrader simulation, injection comparison, sensitivity scan, auto-expansion GA, TSM Monte Carlo, CB parameter estimation, Kelly update, system diagnostics

---

### File: captain-offline/captain_offline/blocks/b3_pseudotrader.py

- **Purpose:** Counterfactual replay engine — P3-PG-09 (basic comparison), P3-PG-09B (CB replay at intraday resolution), P3-PG-09C (CB grid search), account-aware replay with constraint enforcement, multistage EVAL->XFA->LIVE lifecycle replay, two-forecast structure (P3-D27 Sec 5).
- **Key functions/classes:**
  - `run_pseudotrader()` :441 — basic A/B comparison of baseline vs proposed P&L (Sharpe, DD, PBO, DSR)
  - `run_account_aware_replay()` :169 — constraint-enforced replay (DLL, MDD, scaling, trading hours, consistency, capital unlock)
  - `run_signal_replay_comparison()` :515 — full SignalReplayEngine-based comparison (sizing or strategy replay)
  - `run_cb_pseudotrader()` :619 — 4-layer CB replay at intraday granularity
  - `run_cb_grid_search()` :758 — grid search over (c, lambda) with PBO filter
  - `run_multistage_replay()` :815 — EVAL->XFA->LIVE lifecycle via MultiStageTopstepAccount
  - `generate_forecast()` :1073 — standardized backtest forecast per P3-D27 schema
  - `generate_dual_forecasts()` :1349 — produces both Forecast A (full history) and Forecast B (rolling 252-day)
  - `_enforce_trading_hours()` :90 — trading hours constraint checker
  - `_lookup_scaling_tier()` :133 — XFA contract scaling tier lookup
  - `_compute_sharpe()` :40, `_compute_max_drawdown()` :52, `_compute_win_rate()` :65 — metric helpers
  - `_compute_sortino()` :954, `_compute_calmar()` :967, `_compute_profit_factor()` :975 — forecast metrics
  - `_build_system_state_snapshot()` :1026 — pipeline state capture for forecast versioning
- **Session/schedule refs:** Called by orchestrator on trade outcomes (event-driven) and by B4/B6 for injection comparison
- **QuestDB:**
  - `p3_d11_pseudotrader_results` — INSERT :413-424, :494-505, :737-748, :923-938 (4 write points)
  - `p3_d27_pseudotrader_forecasts` — INSERT :1393-1418 (forecast storage)
  - `p3_d02_aim_meta_weights` — SELECT via SignalReplayEngine :1057-1063
- **Redis:** None
- **Stubs/TODOs:** None
- **Notable:**
  - **GOD MODULE**: 1432 lines with 15+ public/private functions spanning 6 distinct responsibilities (basic replay, CB replay, grid search, multistage, forecasting, helpers). Should be split into at least 3 modules.
  - `run_account_aware_replay()` :169 is a ~250-line god function with 8 constraint checks, capital unlock logic, MDD tracking, and metric computation all inline.
  - `generate_forecast()` :1073 is ~240 lines — another god function.
  - `_compute_sharpe`, `_compute_pbo`, `_compute_dsr` duplicated here and in b5/b6 (should use shared.statistics).
  - `_enforce_trading_hours()` :114-128 — fragile string manipulation to parse "15:55 EST" format; no pytz/zoneinfo usage.
  - Magic numbers: `252` (trading days) used 7 times, `$4500` MDD, `$150000` balance, `$226.60` fee, `0.5` PBO/DSR thresholds.
  - AlgorithmImports shim :1-5 — dead code.
  - `run_cb_pseudotrader` :733 — ADOPT decision requires BOTH sharpe AND dd improvement, more conservative than spec which says sharpe > 0 AND pbo < 0.5.

- **Pseudotrader analysis:**
  - B3 simulates trades by replaying historical trade-level data through constraint filters (DLL, MDD, scaling, hours, consistency).
  - Data sources: P3-D03 (trade outcomes) fed as `trades` list, P3-D25 (CB params), SignalReplayEngine for full replay.
  - Outcome reporting: all results stored to P3-D11 with result_id prefix (PT-, AAR-, CB-, MSR-, FCT-). Dual forecasts also stored in P3-D27.
  - Two replay modes: pre-computed P&L comparison (run_pseudotrader) and full signal replay (run_signal_replay_comparison).

---

### File: captain-offline/captain_offline/blocks/b4_injection.py

- **Purpose:** Injection comparison (P3-PG-10) and transition phasing (P3-PG-11) for strategy replacement.
- **Key functions/classes:**
  - `run_injection_comparison()` :108 — P3-PG-10 decision logic (ADOPT/PARALLEL_TRACK/REJECT)
  - `_compute_aim_adjusted_edge()` :45 — AIM-weighted expected edge
  - `_load_aim_weights()` :67 — D02 weight loader
  - `_store_injection()` :83 — D06 writer
  - `TransitionPhaser` :171 — linear ramp transition class
  - `TransitionPhaser.get_weights()` :194 — day-based weight interpolation
  - `TransitionPhaser.blend_signal()` :206 — signal blending for transition
  - `TransitionPhaser.advance_day()` :232 — day progression
  - `TransitionPhaser.finalize()` :241 — complete transition, update D00
  - `TransitionPhaser.load_active()` :274 — classmethod to resume active transitions
- **Session/schedule refs:** Called by B6 auto-expansion when viable candidates found; orchestrator daily for transition advancement
- **QuestDB:**
  - `p3_d02_aim_meta_weights` — SELECT :70-74
  - `p3_d06_injection_history` — INSERT :88-105
  - `p3_d06b_active_transitions` — INSERT :262-272, SELECT :280-287
  - `p3_d00_asset_universe` — UPDATE (via shared.questdb_client.update_d00_fields) :245
- **Redis:** None
- **Stubs/TODOs:** None
- **Notable:**
  - `_load_aim_weights()` :67-80 — no LATEST ON; manual dedup with dict check (same pattern as FINDING-05/08 from Part 1).
  - `TransitionPhaser.load_active()` :280-287 — ORDER BY last_updated DESC without LATEST ON; manual dedup with `seen` set.
  - `_store_injection()` :95 — injection_id uses `datetime.now()` not ET-aware.
  - Lazy import of numpy inside `_compute_aim_adjusted_edge()` :57 — loaded on every call.
  - AlgorithmImports shim :1-5 — dead code.
  - Decision thresholds well-named as constants :36-42.
  - `TransitionPhaser.save()` :260-272 — appends new rows (QuestDB append-only) rather than upserting.

---

### File: captain-offline/captain_offline/blocks/b5_sensitivity.py

- **Purpose:** AIM-13 parameter sensitivity scanner — monthly perturbation grid (P3-PG-12).
- **Key functions/classes:**
  - `run_sensitivity_scan()` :150 — main scan: perturb [-20%..+20%], compute Sharpe stability, PBO, DSR
  - `_backtest_perturbed()` :71 — signal replay with delta perturbation, fallback to r*(1+delta) scaling
  - `_compute_sharpe()` :48 — duplicated from b3
  - `_compute_pbo()` :58, `_compute_dsr()` :64 — delegates to shared.statistics
- **Session/schedule refs:** Monthly (1st of month) via orchestrator scheduled task
- **QuestDB:**
  - `p3_d13_sensitivity_scan_results` — INSERT :220-228
  - `p3_d01_aim_model_states` — INSERT :232-238 (AIM-13 modifier when FRAGILE)
- **Redis:** None
- **Stubs/TODOs:** None
- **Notable:**
  - `_compute_sharpe()` :48 — duplicated from b3_pseudotrader.py (same implementation).
  - `datetime.now().isoformat()` :217 — not ET-aware.
  - AIM-13 modifier write :232-238 — inserts into D01 with `current_modifier` set to `json.dumps({asset_id: FRAGILE_MODIFIER})`. This stores a JSON string where other D01 rows likely expect a float. **Schema mismatch.**
  - `_backtest_perturbed()` :71-147 — well-structured with signal replay primary path and scaling fallback.
  - Perturbation grid constants well-defined :33-45.
  - AlgorithmImports shim :1-5 — dead code.

---

### File: captain-offline/captain_offline/blocks/b6_auto_expansion.py

- **Purpose:** AIM-14 GA-based strategy search triggered by Level 3 decay (P3-PG-13).
- **Key functions/classes:**
  - `run_auto_expansion()` :218 — GA evolution (100 pop, 50 gen) + OOS validation
  - `_evaluate_candidate()` :115 — fitness via signal replay with parameter-scaling fallback
  - `_random_candidate()` :70, `_crossover()` :81, `_mutate()` :93, `_tournament_select()` :109 — GA primitives
  - `_compute_pbo()` :206, `_compute_dsr()` :212 — delegated to shared.statistics (duplicated wrappers)
  - `Candidate` :59 — dataclass for strategy parameter vector
- **Session/schedule refs:** Triggered by Level 3 decay detection in orchestrator
- **QuestDB:**
  - `p3_d00_asset_universe` — SELECT :307-312 (load current strategy)
  - `p3_d06_injection_history` — WRITE (via b4_injection.run_injection_comparison)
- **Redis:** None
- **Stubs/TODOs:** None
- **Notable:**
  - `random.seed(SEED)` + `np.random.seed(SEED)` :230-231 with SEED=42 — makes GA fully deterministic. Every run produces identical candidates for same input. **No stochastic exploration across runs.**
  - `_evaluate_candidate()` :181 — `random.gauss(0, 0.01)` noise is also deterministic due to global seed.
  - `_compute_pbo` / `_compute_dsr` :206-215 — wrapper functions duplicated from b3 and b5.
  - D00 query :307-312 — `ORDER BY last_updated DESC LIMIT 1` instead of LATEST ON.
  - Viable candidates are immediately piped to B4 injection comparison :302-327 — good wiring.
  - Population of 100 × 50 generations = 5000 evaluations. Each calls SignalReplayEngine or scaling fallback. **Potentially slow** (minutes to hours depending on trade count).
  - AlgorithmImports shim :1-5 — dead code.

---

### File: captain-offline/captain_offline/blocks/b7_tsm_simulation.py

- **Purpose:** Monte Carlo TSM simulation (P3-PG-14) — pass probability estimation via block bootstrap (10K paths).
- **Key functions/classes:**
  - `run_tsm_simulation()` :100 — main MC entry: bootstrap, simulate, alert
  - `_block_bootstrap_path()` :44 — block bootstrap with random block sizes [3,5,7]
  - `_simulate_path()` :59 — single path: MDD breach, MLL breach, profit target check
- **Session/schedule refs:** Called by orchestrator on trade outcomes (Category B — own trades only)
- **QuestDB:**
  - `p3_d08_tsm_state` — INSERT :173-179 (pass_probability, simulation_date)
- **Redis:**
  - `CH_ALERTS` — PUBLISH :185-194 (TSM_ALERT when pass_prob below threshold)
- **Stubs/TODOs:** None
- **Notable:**
  - `random.seed(SEED)` + `np.random.seed(SEED)` :118-119 with SEED=42 — **MC always returns same pass_probability for same input**. Defeats the purpose of Monte Carlo stochastic simulation.
  - `results` list :147 stores all 10K path results but only `pass_count` is used. Memory waste (~10K dicts created and discarded).
  - `datetime.now()` :192 — not ET-aware.
  - `date.today()` :134 — remaining days calculation not ET-aware.
  - Alert thresholds well-structured per risk_goal :160-171.
  - Block bootstrap :44-56 correctly preserves autocorrelation.
  - AlgorithmImports shim :1-5 — dead code.

---

### File: captain-offline/captain_offline/blocks/b8_cb_params.py

- **Purpose:** Circuit breaker parameter estimation via OLS regression (P3-PG-16C).
- **Key functions/classes:**
  - `estimate_cb_params()` :131 — main entry: OLS for beta_b, significance gate, sigma, rho_bar
  - `_ols_regression()` :57 — hand-rolled OLS: y = alpha + beta*x
  - `_compute_same_day_correlation()` :102 — pairwise same-day trade correlation
  - `_load_trades_by_account_model()` :40 — trade loader
  - `_save_params()` :207 — D25 writer
- **Session/schedule refs:** Called by orchestrator on trade outcomes (Category B — own trades only)
- **QuestDB:**
  - `p3_d03_trade_outcome_log` — SELECT :43-49
  - `p3_d25_circuit_breaker_params` — INSERT :210-218
- **Redis:** None
- **Stubs/TODOs:** None
- **Notable:**
  - **CRITICAL BUG**: `_compute_same_day_correlation()` :119-120 — `np.corrcoef([arr[i]], [arr[j]])` computes correlation of two single-element arrays. Correlation of two scalars is always ±1.0 or NaN. **This is statistically degenerate and produces meaningless rho_bar values.**
  - **BUG**: `_load_trades_by_account_model()` :40-54 — parameter `model_m` is accepted but **never used in the SQL query**. Loads ALL trades for account regardless of model.
  - `_ols_regression()` :57-99 — hand-rolled OLS when `scipy.stats.linregress` (already a dependency) does the same thing in one call.
  - `scipy.stats` :89 — lazy import inside `_ols_regression()`, re-imported on every regression call.
  - Significance gate :176-177 correctly zeros beta_b when p > 0.05 or n < 100.
  - Cold start :141-148 correctly sets beta_b=0, rho_bar=0 per spec.
  - AlgorithmImports shim :1-5 — dead code.

- **CB params analysis:**
  - Estimates 4 parameters: r_bar (unconditional mean), beta_b (loss serial correlation), sigma (per-trade vol), rho_bar (same-day correlation).
  - beta_b > 0 means losses predict losses (shut basket); beta_b < 0 means mean reversion (keep open).
  - rho_bar calculation is broken (see CRITICAL BUG above) — all values will be ±1 or NaN.

---

### File: captain-offline/captain_offline/blocks/b8_kelly_update.py

- **Purpose:** Kelly parameter updates after trade outcomes (P3-PG-15) — per-contract EWMA + Kelly recalculation.
- **Key functions/classes:**
  - `run_kelly_update()` :130 — main entry: normalize, EWMA update, Kelly recompute, shrinkage
  - `_get_cp_prob()` :42 — BOCPD changepoint probability loader
  - `_compute_adaptive_alpha()` :55 — SPEC-A12 adaptive decay (cp_prob -> EWMA span)
  - `_load_ewma()` :63 — D05 cell loader
  - `_save_ewma()` :84 — D05 writer
  - `_compute_kelly()` :96 — classic Kelly: f* = p - (1-p)/b
  - `_compute_shrinkage()` :108 — sample-size based: max(0.3, 1 - 1/sqrt(N))
  - `_count_asset_trades()` :119 — trade counter for shrinkage
- **Session/schedule refs:** Called by orchestrator on EVERY trade outcome (Category A — all signals)
- **QuestDB:**
  - `p3_d04_decay_detector_states` — SELECT :45-50 (cp_prob)
  - `p3_d05_ewma_states` — SELECT :66-72, INSERT :86-93
  - `p3_d12_kelly_parameters` — INSERT :185-191, :199-205
  - `p3_d03_trade_outcome_log` — SELECT (count) :122-126
- **Redis:** None
- **Stubs/TODOs:** None
- **Notable:**
  - `_load_ewma()` :66-72 — uses `ORDER BY last_updated DESC LIMIT 1` instead of LATEST ON.
  - Kelly recomputation :179-191 writes D12 rows with `shrinkage_factor=None` for all 6 regime/session combos. Asset-level shrinkage written separately :199-205 as regime="ALL", session=0 — **Online may not know to join these two row types.**
  - Hardcoded regimes `["LOW_VOL", "HIGH_VOL"]` and sessions `[1, 2, 3]` :179-180 — should come from config.
  - Uses `version_snapshot.snapshot_before_update()` :158, :175 — good crash recovery practice.
  - SQLite WAL checkpoint :209-212 — correct per spec P3-PG-15.
  - AlgorithmImports shim :1-5 — dead code.

- **Kelly update analysis (7 steps):**
  1. Per-contract normalization :148 (pnl / contracts)
  2. Adaptive EWMA alpha from BOCPD cp_prob :151 (SPEC-A12)
  3. EWMA update :163-168 (win_rate, avg_win, avg_loss)
  4. Save EWMA to D05 :172
  5. Recompute Kelly for all 6 regime/session cells :179-191
  6. Update shrinkage factor :194-205 (asset-level)
  7. SQLite WAL checkpoint :209-212

---

### File: captain-offline/captain_offline/blocks/b9_diagnostic.py

- **Purpose:** 8-dimension system health diagnostic with QUEUE_ACTION helper (P3-PG-16B).
- **Key functions/classes:**
  - `run_diagnostic()` :822 — main entry (WEEKLY or MONTHLY mode)
  - `compute_d1()` :116 — Strategy Portfolio Health (diversity, freshness, OO scores)
  - `compute_d2()` :191 — Feature Portfolio Health (distinct features, decay flags)
  - `compute_d3()` :264 — Model Staleness (P1/P2 ages, regime model, AIM retrain)
  - `compute_d4()` :344 — AIM Effectiveness (active, dormant, dominant, warmup)
  - `compute_d5()` :457 — Edge Trajectory (30/60/90d edge, trend, regime — monthly only)
  - `compute_d6()` :510 — Data Coverage Gaps (AIM missing rates, data holds)
  - `compute_d7()` :616 — Research Pipeline (injection recency, unresolved Level 3)
  - `compute_d8()` :700 — Resolution Verification (resolved items verified, stale detection)
  - `_queue_action()` :76 — deduplicating action item builder
  - `_check_constraint_resolution()` :742 — verification logic per constraint type
  - `_compute_windowed_edge()` :423, `_compute_regime_edge()` :440 — edge calculators
- **Session/schedule refs:** WEEKLY (D1-D4, D6-D8) and MONTHLY (all D1-D8 including D5) via orchestrator
- **QuestDB:**
  - `p3_d00_asset_universe` — SELECT :119-122, :275-277, :308, :652, :753
  - `p3_d01_aim_model_states` — SELECT :291-295, :515-518, :779-783
  - `p3_d02_aim_meta_weights` — SELECT :348-351
  - `p3_d04_decay_detector_states` — SELECT :539-543, :630-634
  - `p3_d05_ewma_states` — SELECT :427-431, :443-447
  - `p3_d06_injection_history` — SELECT :268-270, :620-621, :661-668, :804
  - `p3_d13_sensitivity_scan_results` — SELECT :217-220
  - `p3_d17_system_monitor_state` — SELECT :576-581
  - `p3_d22_system_health_diagnostic` — SELECT :833-834, INSERT :872-882
- **Redis:** None
- **Stubs/TODOs:** None
- **Notable:**
  - `datetime.now()` used ~15 times throughout (lines 85, 86, 95, 425, 564, 702, 730, 858, etc.) — **none ET-aware**. Timestamps in action queue and cutoff calculations will be wrong if container TZ differs.
  - Many queries lack LATEST ON — manual dedup with `seen` sets (D01 :299, D02 :366-367, D04 dedup not done).
  - `_check_constraint_resolution()` :811 — `except Exception: pass` swallows all errors silently, including DB connection failures.
  - `compute_d3()` :332-337 — weighted mean uses same proxy (days_since_injection) for both weight 0.3 and 0.2 slots, double-counting P1/P2 freshness.
  - D5 :499-503 — normalization divisors (0.02, 0.01) for edge scores are magic numbers without named constants.
  - Action queue grows unbounded :833-882 — loaded fully, all dimensions append items, re-stored. No pruning or size cap.
  - AlgorithmImports shim :1-5 — dead code.

---

### Findings Summary (B3-B9)

| ID | Severity | File | Line(s) | Description |
|----|----------|------|---------|-------------|
| FINDING-15 | **CRITICAL** | b8_cb_params.py | 119-120 | `np.corrcoef` on single-element arrays always returns ±1 or NaN. rho_bar calculation is statistically degenerate — produces meaningless values that feed into Layer 4 CB decisions. |
| FINDING-16 | **HIGH** | b8_cb_params.py | 40-54 | `model_m` parameter unused in SQL query. Loads ALL trades for account, not filtered by model. CB params are per-model but estimated from cross-model data. |
| FINDING-17 | **HIGH** | b3_pseudotrader.py | (entire) | God module: 1432 lines, 15+ functions, 6 distinct responsibilities. Violates SRP and makes testing/maintenance difficult. |
| FINDING-18 | **HIGH** | b7_tsm_simulation.py, b6_auto_expansion.py | 118-119, 230-231 | Fixed SEED=42 makes Monte Carlo and GA deterministic across runs. MC always returns same pass_probability; GA always finds same candidates. Defeats stochastic exploration. |
| FINDING-19 | **MEDIUM** | b5_sensitivity.py | 232-238 | AIM-13 modifier written as JSON `{asset_id: 0.85}` into D01.current_modifier. Other D01 rows expect a plain float. Schema mismatch may cause downstream parse errors. |
| FINDING-20 | **MEDIUM** | b4, b5, b7, b9 | (many) | `datetime.now()` without ET timezone used throughout B3-B9 blocks (~20 occurrences). Same root cause as FINDING-01 from Part 1. |
| FINDING-21 | **MEDIUM** | b3, b5, b6 | — | `_compute_sharpe`, `_compute_pbo`, `_compute_dsr` duplicated across 3 files. Shared wrappers already exist in shared.statistics. |
| FINDING-22 | **MEDIUM** | b7_tsm_simulation.py | 147 | 10K simulation result dicts stored in list but only pass_count used. ~10K unnecessary dict allocations per run. |
| FINDING-23 | **MEDIUM** | b8_kelly_update.py | 179-205 | Kelly writes D12 with shrinkage_factor=None. Asset-level shrinkage stored as separate row (regime=ALL, session=0). Online consumer may not know to join. |
| FINDING-24 | **MEDIUM** | b9_diagnostic.py | 833-882 | Action queue loaded from QuestDB and re-stored in entirety. No size limit — grows unbounded as dimensions create new items each run. |
| FINDING-25 | **LOW** | b3_pseudotrader.py | 169-438 | `run_account_aware_replay` is 250+ lines — god function combining 8 constraint checks, capital unlock, and metric computation. |
| FINDING-26 | **LOW** | b6_auto_expansion.py | 181, 230 | `random.gauss(0, 0.01)` noise added after fixed global seed. "Random" noise is deterministic — provides no benefit. |
| FINDING-27 | **LOW** | b4, b8_kelly, b9 | (many) | Multiple blocks use `ORDER BY last_updated DESC LIMIT 1` instead of LATEST ON for QuestDB append-only dedup. Same pattern as FINDING-05/08. |

### Stubs (B3-B9)

None — all B3-B9 blocks are fully implemented.

### Dead Code (B3-B9)

| # | File | Item | Line(s) |
|---|------|------|---------|
| 1 | All 8 files | `AlgorithmImports` try/except shim | :1-5 each |
| 2 | b8_cb_params.py | `model_m` parameter in `_load_trades_by_account_model` | :40 |
| 3 | b7_tsm_simulation.py | `results` list (only pass_count used) | :146-147 |

### Dependency Analysis (B3-B9)

**Actively used by B3-B9:**
| Package | Used In | Purpose |
|---------|---------|---------|
| numpy | b3, b5, b6, b7, b8_cb, b8_kelly | Array ops, statistics, random |
| scipy.stats | b8_cb_params.py :89 | t-distribution p-value (lazy import) |
| json (stdlib) | All files | QuestDB JSON serialization |

**From requirements.txt — still unused in B3-B9:**
| Package | Status |
|---------|--------|
| hmmlearn | Never imported anywhere in captain-offline (confirmed Part 1) |
| scikit-learn | Never imported anywhere in captain-offline (confirmed Part 1) |
| pydantic | Never imported anywhere in captain-offline (confirmed Part 1) |

**Custom implementations vs library alternatives:**
| Custom Code | Alternative | File | Assessment |
|-------------|-------------|------|------------|
| `_ols_regression()` | `scipy.stats.linregress` | b8_cb_params.py :57 | scipy already imported; linregress is simpler and tested |
| `_compute_sharpe()` x3 | `shared.statistics` | b3, b5, b6 | Wrapper already exists in shared module |
| `_compute_pbo()` x3 | Direct call to `shared.statistics.compute_pbo` | b3, b5, b6 | Already delegates; wrapper is unnecessary indirection |

### Code Quality

**Complexity hotspots:**
1. `b3_pseudotrader.py` — 1432 lines, highest complexity file in the entire offline process
2. `run_account_aware_replay()` — ~250 lines, cyclomatic complexity >20 (8 constraint branches, nested loops)
3. `generate_forecast()` — ~240 lines, builds complex output dict with inline calculations
4. `b9_diagnostic.py` — 889 lines, 8 dimension functions each with multiple QuestDB queries

**Magic numbers requiring named constants:**
- `252` (trading days/year) — used 7 times across b3, b5, b6
- `4500` (default MDD limit) — b3 :191
- `150000` (default balance) — b3 :197, :816, b7 :121
- `0.5` (PBO/DSR threshold) — used 10+ times across b3, b5, b6
- `0.02`, `0.01` — D5 edge normalization in b9 :500-502
