# Captain Reconciliation Matrix

Generated: 2026-04-09 by Agent A (Coordinator)
Source: `docs/audit/master_gap_analysis.md` (100 gaps) + `docs/audit/spec_reference.md` (13 sections)
Scope: 67 non-LOW gaps (CRITICAL + HIGH + MEDIUM). 33 LOW gaps DEFERRED.

---

## §1 — Finding-Level Matrix

### Session 01 | Phase 1: Critical Fixes

#### G-004 | CRITICAL | Command | Telegram Bot
- **Spec:** §9 D00 (`p3_d00_asset_universe`), D03 (`p3_d03_trade_outcome_log`)
- **Code:** captain-command/captain_command/telegram_bot.py:102,112,160 — uses `p3_d00_asset_registry` and `p3_d03_trade_outcomes`
- **Delta:** Two wrong table names crash `/status` and `/trades` commands at runtime
- **Deps:** None | **Skill:** ln-614 | **Status:** FIXED

#### G-005 | CRITICAL | Cross-Cutting | Replay Engine
- **Spec:** §9 D25 (`p3_d25_circuit_breaker_params`)
- **Code:** shared/replay_engine.py:289 — queries `p3_d25_circuit_breaker`
- **Delta:** Wrong table name; CB silently absent from all replay sessions
- **Deps:** None | **Skill:** ln-614 | **Status:** FIXED

#### G-017 | HIGH | Cross-Cutting | Config
- **Spec:** §1 Session Definitions — LON session, NY_PRE session
- **Code:** shared/constants.py uses `LON`; config/session_registry.json uses `LONDON`; no `NY_PRE` in SESSION_IDS
- **Delta:** Session name mismatch; NKD never enters session; ZN/ZB/MGC timing wrong
- **Deps:** DEC-07 | **Skill:** ln-647 | **Status:** FIXED

#### G-001 | CRITICAL | Offline B8 | CB Params
- **Spec:** §6 CB Layer 4 — `beta_b = OLS(loss_sequence)` sliding window
- **Code:** captain-offline/captain_offline/blocks/b8_cb_params.py:119-120 — `np.corrcoef` on 2-element array
- **Delta:** Always ±1.0 or NaN; Layer 4 mathematically broken
- **Deps:** None | **Skill:** ln-624 | **Status:** FIXED

#### G-013 | HIGH | Offline B8 | CB Params
- **Spec:** §6 CB — per-model parameter estimation keyed by (account_id, model_m)
- **Code:** b8_cb_params.py:40-54 — `model_m` in signature but unused in SQL
- **Delta:** CB params estimated from ALL models; cross-contamination
- **Deps:** G-001 | **Skill:** ln-624 | **Status:** FIXED

#### G-027 | HIGH | Online B1 | Data Ingestion
- **Spec:** §2 B1 REQ-3 — data moderator checks stale data, bad timestamps; flags DATA_HOLD
- **Code:** captain-online/captain_online/blocks/b1_data_ingestion.py:574,578 — both return True unconditionally
- **Delta:** Data quality checks disabled; corrupted data passes downstream
- **Deps:** None | **Skill:** ln-629 | **Status:** FIXED

---

### Session 02 | Phase 2: Learning Loops (A)

#### G-009 | HIGH | Offline B1 | AIM Lifecycle
- **Spec:** §3 AIM Lifecycle — latest state row per AIM drives transitions
- **Code:** captain-offline/captain_offline/blocks/b1_aim_lifecycle.py:55 — `ORDER BY` without `LATEST ON`
- **Delta:** May return stale/historical AIM state row; wrong lifecycle transitions
- **Deps:** None | **Skill:** ln-624 | **Status:** FIXED

#### G-010 | HIGH | Offline B1 | DMA Update
- **Spec:** §4 Offline B1 — latest meta-weight from D02 is base for DMA delta
- **Code:** captain-offline/captain_offline/blocks/b1_dma_update.py:43-56 — `ORDER BY` without `LATEST ON`
- **Delta:** DMA update uses stale weights; weight trajectory corrupted
- **Deps:** G-009 | **Skill:** ln-624 | **Status:** FIXED

#### G-070 | MEDIUM | Multi | QuestDB Queries
- **Spec:** §9 — QuestDB append-only; use `LATEST ON` for dedup
- **Code:** ~10 blocks use `ORDER BY DESC LIMIT 1` instead of `LATEST ON`
- **Delta:** Systematic stale-read risk across entire codebase
- **Deps:** G-009, G-010 | **Skill:** ln-614 | **Status:** FIXED

#### G-008 | HIGH | Offline B9 | Drift Detection
- **Spec:** §4 Offline B9 — ADWIN on AIM features for decay detection
- **Code:** captain-offline/captain_offline/orchestrator.py:572 — `run_drift_detection(asset_id, {})` with empty dict
- **Delta:** Drift detection processes zero features; complete no-op
- **Deps:** None | **Skill:** ln-629 | **Status:** FIXED

#### G-047 | MEDIUM | Offline B1 | Drift Detection
- **Spec:** §4 Offline B9 — uses `river` library for ADWIN
- **Code:** `river` not in captain-offline/requirements.txt
- **Delta:** Primary drift detection path unavailable in Docker container
- **Deps:** G-008 | **Skill:** ln-625 | **Status:** FIXED

#### G-048 | MEDIUM | Offline B1 | Drift Detection
- **Spec:** §4 Offline B9 — persistent ADWIN state
- **Code:** b1_drift_detection.py:115-116 — ADWIN/autoencoder state in module-level dicts
- **Delta:** State lost on every container restart; drift detection resets to cold
- **Deps:** G-047 | **Skill:** ln-629 | **Status:** FIXED

---

### Session 03 | Phase 2: Learning Loops (B)

#### G-011 | HIGH | Offline B2 | Level Escalation
- **Spec:** §6 CB — Level 2 triggers once per changepoint event; debounced
- **Code:** captain-offline/captain_offline/blocks/b2_level_escalation.py:186 — fires every trade where `cp_prob > 0.8`
- **Delta:** No cooldown; Level 2 fires repeatedly during elevated cp_prob
- **Deps:** None | **Skill:** ln-624 | **Status:** VERIFIED

#### G-012 | HIGH | Offline B2 | Level Escalation
- **Spec:** §6 CB — Level 2 and Level 3 are mutually exclusive escalation tiers
- **Code:** b2_level_escalation.py:186-197 — no `return`/`elif` between Level 2 and Level 3 checks
- **Delta:** Both Level 2 and Level 3 fire when cp_prob > 0.9; conflicting actions
- **Deps:** G-011 | **Skill:** ln-624 | **Status:** VERIFIED

#### G-028 | HIGH | Online B7 | Position Monitor
- **Spec:** §11 Feedback Loop 1 — trade outcome must reliably reach Offline via Redis
- **Code:** captain-online/captain_online/blocks/b7_position_monitor.py:336-360 — no retry on Redis publish failure
- **Delta:** Trade outcomes silently dropped on Redis blip; biased learning sample
- **Deps:** None | **Skill:** ln-628 | **Status:** VERIFIED

#### G-006 | HIGH | Online B7 | Orchestrator
- **Spec:** §2 B7, §11 Loop 1 — correct trade outcome delivery
- **Code:** captain-online/captain_online/orchestrator.py:61-62,762,769 — position lists mutated from 2 threads without lock
- **Delta:** Race condition; trade outcomes silently dropped
- **Deps:** None | **Skill:** ln-628 | **Status:** VERIFIED

#### G-044 | MEDIUM | Offline Orch | Shutdown
- **Spec:** §12 Lifecycle — graceful shutdown joins all threads
- **Code:** captain-offline/captain_offline/orchestrator.py:69 — `stop()` doesn't join Redis listener thread
- **Delta:** Mid-write outcome interrupted on SIGTERM; partial data in QuestDB
- **Deps:** None | **Skill:** ln-629 | **Status:** VERIFIED

#### G-014 | HIGH | Offline B6/B7 | MC + GA
- **Spec:** §4 B6 — stochastic GA exploration for new strategy candidates
- **Code:** b7_tsm_simulation.py:118; b6_auto_expansion.py:230 — `SEED=42` globally
- **Delta:** MC and GA fully deterministic; same output every run regardless of market state
- **Deps:** None | **Skill:** ln-624 | **Status:** VERIFIED

---

### Session 04 | Phase 3: Security Hardening

#### G-002 | CRITICAL | Command | All Endpoints
- **Spec:** §10 — authenticated REST and WebSocket endpoints; token-based access control
- **Code:** captain-command/captain_command/api.py — no auth middleware registered
- **Delta:** Zero authentication on any endpoint including financial commands
- **Deps:** DEC-01 | **Skill:** ln-621 | **Status:** FIXED

#### G-003 | CRITICAL | Command | API
- **Spec:** §10 — secure remote update mechanism
- **Code:** api.py `/system/git-pull` — unauthenticated shell execution
- **Delta:** Arbitrary code execution; Docker socket enables host escape
- **Deps:** G-002, DEC-02 | **Skill:** ln-621 | **Status:** FIXED

#### G-021 | HIGH | Command B7 | Notifications
- **Spec:** §10 — parameterized SQL queries throughout
- **Code:** captain-command/captain_command/blocks/b7_notifications.py:433-436 — f-string SQL interpolation
- **Delta:** SQL injection in `_get_users_by_roles()` via role list
- **Deps:** None | **Skill:** ln-621 | **Status:** FIXED

#### G-055 | MEDIUM | Command B11 | WebSocket
- **Spec:** §8 — user_id verified against session token
- **Code:** api.py WebSocket endpoint — `user_id` from query param, no verification
- **Delta:** Client can impersonate any user via self-declared user_id
- **Deps:** G-002 | **Skill:** ln-621 | **Status:** FIXED

#### G-020 | HIGH | Command Infra | Docker
- **Spec:** §10 — minimal container attack surface; least privilege
- **Code:** captain-command/Dockerfile:9-14 — Docker CLI installed; socket mounted
- **Delta:** Full Docker daemon access from container; host escape vector
- **Deps:** G-003, DEC-02 | **Skill:** ln-621 | **Status:** FIXED

#### G-089 | MEDIUM | All | Docker
- **Spec:** §10 — containers run as non-root
- **Code:** All Dockerfiles — no `USER` directive; all run as root
- **Delta:** Containers run as root; compromised process gets root access
- **Deps:** None | **Skill:** ln-621 | **Status:** FIXED

#### G-056 | MEDIUM | Command B3 | API Errors
- **Spec:** §10 — generic error responses; no internal details exposed
- **Code:** api.py + b6_reports.py:137,396 — `str(exc)` in responses
- **Delta:** Stack traces and internal paths leaked to API callers
- **Deps:** None | **Skill:** ln-621 | **Status:** FIXED

---

### Session 05 | Phase 4: Timezone + Session Infrastructure

#### G-024 | HIGH | Offline Orch | Scheduler
- **Spec:** §1 REQ-4 — timezone is always America/New_York; ASSERT at session start
- **Code:** captain-offline/captain_offline/orchestrator.py:529 — `datetime.now()` (system local)
- **Delta:** Daily blocks fire at wrong time if container TZ != ET
- **Deps:** None | **Skill:** ln-647 | **Status:** FIXED

#### G-029 | MEDIUM | Online B1 | Data Ingestion
- **Spec:** §1 REQ-4 — always ET timezone
- **Code:** captain-online/captain_online/blocks/b1_data_ingestion.py:436,642; b1_features.py:546
- **Delta:** `datetime.now()` without ET in 3 online locations
- **Deps:** None | **Skill:** ln-647 | **Status:** FIXED

#### G-051 | MEDIUM | Offline ALL | Timezone
- **Spec:** §1 REQ-4 — always ET timezone
- **Code:** ~20 sites across captain-offline orchestrator + B3-B9
- **Delta:** `datetime.now()` without ET throughout offline blocks
- **Deps:** G-024 | **Skill:** ln-647 | **Status:** FIXED

#### G-036 | MEDIUM | Online B1 | Features
- **Spec:** §1 — per-session open times (LON=03:00, APAC=18:00)
- **Code:** captain-online/captain_online/blocks/b1_features.py:1073-1082 — always returns 9:30 ET
- **Delta:** `_get_session_open_time()` wrong for LON/APAC assets
- **Deps:** G-017 | **Skill:** ln-641 | **Status:** FIXED

#### G-065 | MEDIUM | Config | Session Registry
- **Spec:** §1 — ZN/ZB session mapping
- **Code:** config/session_registry.json maps ZN/ZB to `NY_PRE`; CLAUDE.md says `NY`
- **Delta:** Conflicting session assignment for ZN/ZB
- **Deps:** G-017, DEC-07 | **Skill:** ln-647 | **Status:** FIXED

#### G-007 | HIGH | Online B1 | AIM-03 GEX
- **Spec:** §3 AIM-03 — per-asset contract multiplier from D00
- **Code:** captain-online/captain_online/blocks/b1_features.py:955-956 — hardcoded 50.0 (ES)
- **Delta:** Wrong by 10-200x for 9 of 10 assets
- **Deps:** None | **Skill:** ln-641 | **Status:** FIXED

---

### Session 06 | Phase 4: Online Reliability

#### G-023 | HIGH | Online B1 | Data Ingestion
- **Spec:** §1 — B1 latency budget <9s; parallel asset data fetch
- **Code:** captain-online/captain_online/blocks/b1_data_ingestion.py:497-558 — synchronous sequential REST
- **Delta:** Up to 90 sequential calls; 90-180s latency on slow API day
- **Deps:** G-018 | **Skill:** ln-653 | **Status:** VERIFIED

#### G-018 | HIGH | Cross-Cutting | TopstepX Client
- **Spec:** §10 — TopstepX REST handles rate limiting and timeout gracefully
- **Code:** shared/topstep_client.py — no `timeout=` on any `requests.post()`; no 429 logic
- **Delta:** Hung API blocks thread indefinitely; no rate limit handling
- **Deps:** None | **Skill:** ln-653 | **Status:** VERIFIED

#### G-030 | MEDIUM | Online B7 | Position Monitor
- **Spec:** §2 B7 — VIX spike, regime shift, and API commission checks
- **Code:** b7_position_monitor.py:419-427 — all stubs returning True/None
- **Delta:** Three monitoring checks are no-ops
- **Deps:** None | **Skill:** ln-629 | **Status:** FIXED (PARTIAL: VIX z-score gap + wrong table name)

#### G-031 | MEDIUM | Online B7 | Shadow Monitor
- **Spec:** §2 B7 — per-asset point values from D00
- **Code:** b7_shadow_monitor.py:217-221 — POINT_VALUES dict hardcoded
- **Delta:** Breaks if assets change; doesn't match D00
- **Deps:** None | **Skill:** ln-641 | **Status:** FIXED (PARTIAL: wrong table name prefix)

#### G-032 | MEDIUM | Online B7 | Shadow Monitor
- **Spec:** §2 B7 — expired shadow positions publish TIMEOUT outcome
- **Code:** b7_shadow_monitor.py:87-93 — expired positions silently dropped
- **Delta:** No TIMEOUT outcome published; shadow learning incomplete
- **Deps:** None | **Skill:** ln-629 | **Status:** VERIFIED

#### G-033 | MEDIUM | Online B7 | Position Monitor
- **Spec:** §11 Loop 5 — atomic capital/CB state updates
- **Code:** b7_position_monitor.py:279-296 — non-atomic D16/D23 updates
- **Delta:** Concurrent close races drift capital silo
- **Deps:** None | **Skill:** ln-628 | **Status:** VERIFIED

---

### Session 07 | Phase 5: AIM Implementation

#### G-075 | MEDIUM | Online B1 | AIM-12
- **Spec:** §3 AIM-12 — spread_z from `p3_spread_history`
- **Code:** b1_features.py:700-706 — table not in init_questdb.py
- **Delta:** spread_z always None on fresh DB; AIM-12 non-functional
- **Deps:** None | **Skill:** ln-614 | **Status:** FIXED (table already in init_questdb.py:647-664)

#### G-069 | MEDIUM | QuestDB | Schema
- **Spec:** §9 — all tables created by init scripts
- **Code:** b1_features.py:700-706,1270 — `p3_spread_history` written/read but absent from init_questdb.py
- **Delta:** Undocumented table; must be added to init script and schema docs
- **Deps:** None | **Skill:** ln-614 | **Status:** FIXED (table + comment present in init_questdb.py:647-664)

#### G-073 | MEDIUM | Online B1 | AIM-07 COT
- **Spec:** §3 AIM-07 — COT Sentiment from CFTC data
- **Code:** b1_features.py (COT section) — `cot_smi` and `cot_speculator_z` never populated
- **Delta:** AIM-07 always fires on null; no data source
- **Deps:** DEC-08 | **Skill:** ln-641 | **Status:** FIXED (AIM-07 disabled in dispatch + features per DEC-08)

#### G-074 | MEDIUM | Online B1 | AIM-01/02
- **Spec:** §3 AIM-01/02 — applicable to multiple assets
- **Code:** aim_compute.py + b1_features.py — features ES-only
- **Delta:** Non-ES assets get null/0 inputs for AIM-01/02
- **Deps:** None | **Skill:** ln-641 | **Status:** FIXED (D30 realised vol fallback for all assets; ES-only docstrings removed)

#### G-076 | MEDIUM | Offline B5 | AIM-13
- **Spec:** §3 AIM-13 — modifier is a float written to D01
- **Code:** captain-offline/captain_offline/blocks/b5_sensitivity.py:232-238 — writes JSON dict `{"asset_id": val}`
- **Delta:** Downstream parse errors; modifier not a plain float
- **Deps:** None | **Skill:** ln-641 | **Status:** FIXED (write FRAGILE_MODIFIER float directly, not json.dumps dict)

#### G-077 | MEDIUM | Cross-Cutting | AIM-08
- **Spec:** §3 AIM-08 — CORR_STRESS = z-score of rolling correlation
- **Code:** shared/aim_feature_loader.py:193 — raw Pearson correlation used as z-score proxy
- **Delta:** `corr_z > 1.5` tier mathematically unreachable; AIM-08 never fires high stress
- **Deps:** None | **Skill:** ln-641 | **Status:** FIXED (replay path: rolling 20d correlation series + z_score instead of raw Pearson r)

---

### Session 08 | Phase 5: Offline Pipeline Alignment

#### G-045 | MEDIUM | Offline Orch | Bootstrap
- **Spec:** §4 Offline Orch — multi-session bootstrap applies regime filtering to all sessions
- **Code:** captain-offline/captain_offline/bootstrap.py:122 — only `default_session` filtered
- **Delta:** Non-default sessions get unfiltered data in bootstrap
- **Deps:** None | **Skill:** ln-629 | **Status:** FIXED

#### G-046 | MEDIUM | Offline B1 | AIM-16 HMM
- **Spec:** §3 AIM-16 — HMM implementation
- **Code:** b1_aim16_hmm.py — hand-rolled Baum-Welch; `hmmlearn` in requirements unused
- **Delta:** Spec-referenced library unused; hand-rolled may diverge
- **Deps:** DEC-05 | **Skill:** ln-625 | **Status:** FIXED

#### G-049 | MEDIUM | Offline B5 | Sensitivity
- **Spec:** §3 AIM-13 — modifier written as float
- **Code:** b5_sensitivity.py:232-238 — JSON dict not float
- **Delta:** Same as G-076; fix both together
- **Deps:** G-076 | **Skill:** ln-641 | **Status:** FIXED

#### G-050 | MEDIUM | Offline B9 | Diagnostic
- **Spec:** §4 B9 — bounded action queue
- **Code:** b9_diagnostic.py:833-882 — action queue loaded/stored with no size cap
- **Delta:** Unbounded growth; memory risk on long-running container
- **Deps:** None | **Skill:** ln-654 | **Status:** FIXED

#### G-052 | MEDIUM | Offline B8 | Kelly Update
- **Spec:** §5 Kelly — shrinkage row linkage documented for online consumer
- **Code:** b8_kelly_update.py:179-205 — join strategy undocumented
- **Delta:** Online consumer must guess join strategy; fragile coupling
- **Deps:** None | **Skill:** ln-643 | **Status:** FIXED

#### G-034 | MEDIUM | Online B3 | AIM Aggregation
- **Spec:** §2 B3 — AIM aggregation block
- **Code:** b3_aim_aggregation.py — pure re-export shim to aim_compute
- **Delta:** Dead indirection layer; adds confusion without value
- **Deps:** None | **Skill:** ln-626 | **Status:** FIXED

---

### Session 09 | Phase 6: Command Pipeline + QuestDB

#### G-022 | HIGH | Command B8 | Reconciliation
- **Spec:** §7 Command B8 — reconciliation corrects D08 balance on divergence
- **Code:** captain-command/captain_command/blocks/b8_reconciliation.py:483-515 — logs but never writes D08 correction
- **Delta:** D08 permanently diverges from broker; SOD compounding wrong
- **Deps:** None | **Skill:** ln-643 | **Status:** FIXED

#### G-019 | HIGH | Command B8 | Reconciliation
- **Spec:** §7 B8 — payout MDD threshold from D17 system_params
- **Code:** b8_reconciliation.py:336 — hardcoded `f_target_max = 0.03`
- **Delta:** Cannot change without code modification; wrong for non-150K accounts
- **Deps:** None | **Skill:** ln-643 | **Status:** FIXED

#### G-054 | MEDIUM | Command B11 | Replay Runner
- **Spec:** §7 B11 — replay sessions cleaned up on completion
- **Code:** captain-command/captain_command/blocks/b11_replay_runner.py:206-218 — completed sessions never removed from `_active_sessions`
- **Delta:** Memory leak; completed sessions accumulate
- **Deps:** None | **Skill:** ln-654 | **Status:** FIXED

#### G-057 | MEDIUM | Command B7 | Notifications
- **Spec:** §7 B7 — publishes to `captain:alerts` Redis channel
- **Code:** b7_notifications.py:7 — CH_ALERTS unused in B7
- **Delta:** Notifications never reach Redis alerts channel
- **Deps:** None | **Skill:** ln-643 | **Status:** FIXED

#### G-058 | MEDIUM | Command B9 | Incident Response
- **Spec:** §7 B9 — incident response handler
- **Code:** b9_incident_response.py:257 — `NameError` on `exc` outside try/except
- **Delta:** Dead code; would crash if reached
- **Deps:** None | **Skill:** ln-626 | **Status:** FIXED

#### G-059 | MEDIUM | Command | Telegram
- **Spec:** §10 — secrets not in logs or memory
- **Code:** captain-command/captain_command/telegram_bot.py:600 — bot token in URL strings
- **Delta:** Token in HTTP access logs and memory
- **Deps:** None | **Skill:** ln-621 | **Status:** FIXED

---

### Session 10 | Phase 6: Concurrency + CB + Feedback

#### G-015 | HIGH | Command B2 | GUI Data Server
- **Spec:** §7 B2 — real-time GUI data to multiple concurrent clients
- **Code:** captain-command/captain_command/blocks/b2_gui_data_server.py — globals without locks
- **Delta:** Partially-updated financial snapshots served to GUI
- **Deps:** None | **Skill:** ln-628 | **Status:** FIXED

#### G-016 | HIGH | Command B2 | API
- **Spec:** §7 B2 — broadcast trade notifications to all WebSocket clients
- **Code:** api.py `_active_connections` — dict mutated from multiple threads
- **Delta:** Dict mutation during iteration on trade path; notifications dropped
- **Deps:** G-015 | **Skill:** ln-628 | **Status:** FIXED

#### G-078 | MEDIUM | Cross-Cutting | AIM-16
- **Spec:** §3 AIM-16 — in dispatch table (or removed per DEC-06)
- **Code:** shared/aim_compute.py:637-649 — `_aim16_hmm()` defined but not dispatched
- **Delta:** Dead function; needs removal or reconnection
- **Deps:** DEC-06 | **Skill:** ln-626 | **Status:** FIXED

#### G-079 | MEDIUM | Cross-Cutting | AIM Features
- **Spec:** §3 — all 16 AIMs functional in replay
- **Code:** shared/aim_feature_loader.py — 7 features unavailable in replay
- **Delta:** pcr_z, gex, cot_smi, cot_speculator_z, event_proximity, events_today, cl_basis missing
- **Deps:** G-073, G-074 | **Skill:** ln-641 | **Status:** FIXED

#### G-080 | MEDIUM | Online | CB Layers
- **Spec:** §6 — 5 CB layers
- **Code:** b5c_circuit_breaker.py:11 — 7 layers (L0-L6 including L5/L6 safety)
- **Delta:** Code has extra layers; needs spec alignment or V3 amendment
- **Deps:** DEC-03 | **Skill:** ln-641 | **Status:** FIXED

#### G-081 | MEDIUM | Multi | Kelly
- **Spec:** §5 — DRY principle
- **Code:** b4_kelly_sizing.py:292; b5_trade_selection.py:192; b6_signal_output.py:310
- **Delta:** `_get_ewma_for_regime()` duplicated 3x; divergence risk
- **Deps:** None | **Skill:** ln-623 | **Status:** FIXED

---

### Session 11 | Phase 7: Code Quality + Remaining

#### G-025 | HIGH | Offline B3 | Pseudotrader
- **Spec:** §4 B3 — single-responsibility block
- **Code:** b3_pseudotrader.py — 1,432 lines, 6 responsibilities, CC>20
- **Delta:** God module; impossible to test in isolation
- **Deps:** DEC-04 | **Skill:** ln-623 | **Status:** UNRESOLVED

#### G-026 | HIGH | Command Main | Multi-User
- **Spec:** §1 REQ-6 — multi-user from day one; never hardcode single-user
- **Code:** captain-command/captain_command/main.py:131 — `primary_user` hardcoded
- **Delta:** Multi-user TSM linking broken
- **Deps:** None | **Skill:** ln-641 | **Status:** UNRESOLVED

#### G-035 | MEDIUM | Online B4 | DRY
- **Spec:** DRY principle
- **Code:** b4_kelly_sizing.py:461 + 5 others — `_parse_json()` duplicated 6x
- **Delta:** 8-line function copied into 6 blocks
- **Deps:** None | **Skill:** ln-623 | **Status:** UNRESOLVED

#### G-037 | MEDIUM | Online B2 | Regime Classifier
- **Spec:** §2 B2 — regime probabilities per asset
- **Code:** b2_regime_probability.py:150-154 — returns 50/50 for C1-C3 assets
- **Delta:** Classifier is a no-op for 3 classifier tiers
- **Deps:** None | **Skill:** ln-624 | **Status:** UNRESOLVED

#### G-038 | MEDIUM | Online B9 | Capacity Evaluator
- **Spec:** §2 B9 — efficient data access
- **Code:** b9_capacity_evaluation.py:108-117 — D00 queried per-asset in loop
- **Delta:** N+1 query for 10 assets
- **Deps:** None | **Skill:** ln-651 | **Status:** UNRESOLVED

#### G-039 | MEDIUM | Online B9 | Capacity Evaluator
- **Spec:** §2 B9 — efficient data access
- **Code:** b9_capacity_evaluation.py:160-177 — fetches ALL D17 session_log; filters in Python
- **Delta:** Entire table loaded when only current session needed
- **Deps:** None | **Skill:** ln-651 | **Status:** UNRESOLVED

#### G-040 | MEDIUM | Online B9 | Capacity Evaluator
- **Spec:** — consistent constraint API
- **Code:** b9_capacity_evaluation.py:124 — uses `"detail"` key; others use `"message"`
- **Delta:** Inconsistent constraint response format
- **Deps:** None | **Skill:** ln-643 | **Status:** UNRESOLVED

---

### Session 12 | Phase 7: Session Infrastructure + Naming

#### G-066 | MEDIUM | Online | Session Controller
- **Spec:** §2 — B9 session controller block
- **Code:** No `b9_session_controller.py`; B9 is capacity evaluator
- **Delta:** Session trigger logic absent as named block
- **Deps:** DEC-09 | **Skill:** ln-629 | **Status:** UNRESOLVED

#### G-067 | MEDIUM | Online | OR Tracker Naming
- **Spec:** §2 — B8 OR tracker
- **Code:** `or_tracker.py` has no block prefix; spec calls it B8
- **Delta:** Naming inconsistency; no functional gap
- **Deps:** None | **Skill:** NONE | **Status:** UNRESOLVED

#### G-068 | MEDIUM | Online | Compliance Gate
- **Spec:** §2 — compliance gate block
- **Code:** compliance_gate.json exists; no block enforcing it
- **Delta:** Compliance gate config exists but no runtime enforcement
- **Deps:** DEC-10 | **Skill:** ln-641 | **Status:** UNRESOLVED

---

### Session 13 | Verification Sweep (no implementation)

Full audit skill run against completed codebase. No code changes.

---

### DEFERRED — LOW Severity (33 gaps)

**NOTE — Deferred with intent (revisit post-stabilization):**
- **G-025** (HIGH, Pseudotrader god module) — DEC-04 resolved as DEFER. Must be revisited after live trading is stable. Track in post-launch tech debt pass alongside LOW items below.

| Gap ID | Area | Description |
|--------|------|-------------|
| G-041 | Online B2 | Dead VRP fallback block — unreachable code |
| G-042 | Online B2 | regime_probs set then unconditionally overwritten |
| G-043 | Online B7 | Shadow monitor no REST fallback if WebSocket drops |
| G-053 | Offline B2 | 501 NIGPrior objects recreated per update() call |
| G-060 | Command Orch | Sync report gen in scheduler thread can block |
| G-061 | Command Orch | TOCTOU on config file reads |
| G-062 | Command B7 | Telegram rate limit dicts accessed from 2 threads |
| G-063 | Command B9 | P1_CRITICAL missing email routing per spec |
| G-064 | Command B6 | RPT-11 financial export no authorization check |
| G-071 | QuestDB | Doc claims 29 tables; init has 38 CREATE TABLE |
| G-072 | QuestDB | Every get_cursor() opens fresh TCP; no pooling |
| G-082 | Kelly | MDD fallback `or 4500.0` magic number |
| G-083–G-088 | Feedback | Meta-gaps — fixed by constituent gap fixes |
| Others | Various | Remaining LOW items from appendices |

---

## §2 — Decision Register

### DEC-01: API Authentication Approach
- **Gaps:** G-002, G-055
- **Options:**
  - A) JWT token middleware (standard, stateless, supports multi-user)
  - B) API key header (simpler, sufficient for localhost-only)
  - C) Session-based auth with cookie (requires session store)
- **Recommendation:** B — localhost-only deployment; API key from .env; upgrade to JWT when multi-user goes live
- **Resolution:** A — JWT token middleware. Full stateless auth with token issuer.
- **Status:** RESOLVED

### DEC-02: git-pull Endpoint Handling
- **Gaps:** G-003, G-020
- **Options:**
  - A) Remove endpoint entirely; use `captain-update.sh` for deployments
  - B) Gate behind auth + signed commits + remove Docker socket
  - C) Replace with webhook-triggered CI/CD
- **Recommendation:** A — `captain-update.sh` already exists and is the documented update path
- **Resolution:** A — Remove endpoint entirely. Docker CLI + socket mount also removed.
- **Status:** RESOLVED

### DEC-03: CB Layer Count (5 spec vs 7 code)
- **Gaps:** G-080
- **Options:**
  - A) Remove L5/L6 safety layers to match spec
  - B) Keep 7 layers; document as V3 amendment
- **Recommendation:** B — extra safety layers are defensive and beneficial
- **Resolution:** B — Keep 7 layers, document L5/L6 as V3 amendment.
- **Status:** RESOLVED

### DEC-04: Pseudotrader God Module Refactor Scope
- **Gaps:** G-025
- **Options:**
  - A) Full 6-way split (XL effort, ~2 sessions)
  - B) Extract 3 biggest concerns only (L effort, 1 session)
  - C) Defer to after live trading stabilized
- **Recommendation:** C — P1 priority is reaching live trading, not refactoring
- **Resolution:** C — Defer until after live trading stabilized. Track alongside other deferred items for post-stabilization pass.
- **Status:** RESOLVED

### DEC-05: hmmlearn vs Hand-Rolled Baum-Welch
- **Gaps:** G-046
- **Options:**
  - A) Switch to hmmlearn (in requirements, tested library)
  - B) Keep hand-rolled, remove hmmlearn from requirements
- **Recommendation:** A — use the tested library
- **Resolution:** A — Switch to hmmlearn. Remove hand-rolled Baum-Welch.
- **Status:** RESOLVED

### DEC-06: AIM-16 HMM Dispatch Table
- **Gaps:** G-078
- **Question:** Was AIM-16 removal from dispatch table intentional? Spec says Block 5 Offline.
- **Options:**
  - A) Re-add to shared dispatch table
  - B) Keep removed — it runs in Offline B5 only, not shared compute
  - C) Remove dead function entirely
- **Recommendation:** Needs Nomaan input
- **Resolution:** A — Re-add to shared dispatch table. Online B3 needs HMM inference for session budget allocation.
- **Status:** RESOLVED

### DEC-07: ZN/ZB Session Mapping
- **Gaps:** G-065
- **Question:** ZN/ZB → `NY_PRE` (session_registry.json) or `NY` (CLAUDE.md locked strategies)?
- **Options:**
  - A) NY_PRE (06:00 ET, follows JSON config)
  - B) NY (09:30 ET, follows CLAUDE.md/spec)
- **Recommendation:** Needs Nomaan input — which matches Isaac's spec?
- **Resolution:** B — ZN/ZB → NY session (09:30 ET). Update session_registry.json to match.
- **Status:** RESOLVED

### DEC-08: COT Data Feed for AIM-07
- **Gaps:** G-073
- **Options:**
  - A) Implement real CFTC COT data feed (L effort)
  - B) Stub with documented placeholder values
  - C) Disable AIM-07 until data available
- **Recommendation:** C — AIM-07 is Tier 2; disable until data source resolved
- **Resolution:** C — Disable AIM-07 until COT data pipeline exists.
- **Status:** RESOLVED

### DEC-09: Session Controller Block
- **Gaps:** G-066
- **Question:** Does session trigger logic exist in orchestrator (just not as named B9)?
- **Options:**
  - A) Create standalone b9_session_controller.py
  - B) Document that orchestrator handles this; rename gap to "naming only"
- **Recommendation:** B (likely)
- **Resolution:** A — Create standalone b9_session_controller.py.
- **Status:** RESOLVED

### DEC-10: Compliance Gate Block
- **Gaps:** G-068
- **Question:** Is compliance_gate.json enforced elsewhere?
- **Options:**
  - A) Create compliance gate block
  - B) Document that compliance checks exist in other blocks
- **Recommendation:** B (likely)
- **Resolution:** A — Create compliance gate enforcement block.
- **Status:** RESOLVED

---

## §3 — Execution Phases

| Phase | Name | Sessions | Gap Count | Priority |
|-------|------|----------|-----------|----------|
| 1 | Critical Fixes | 01 | 6 | P1 — Fix before any live session |
| 2 | Learning Loops | 02–03 | 12 | P2 — Fix before trusting learning |
| 3 | Security Hardening | 04 | 7 | P3 — Fix before any network exposure |
| 4 | Session + Online | 05–06 | 12 | P4 — Fix before multi-session trading |
| 5 | AIM + Offline | 07–08 | 12 | P5 — AIM compliance + Offline alignment |
| 6 | Command + CB | 09–10 | 12 | P6 — Command pipeline + concurrency |
| 7 | Quality + Verify | 11–13 | 10 + audit | P7 — Cleanup + full verification sweep |

---

## §4 — Session Split Plan

| Session | Phase | Gaps | Post-Session Skills |
|---------|-------|------|---------------------|
| 01 | 1 | G-004, G-005, G-017, G-001, G-013, G-027 | ln-614, ln-624 |
| 02 | 2 | G-009, G-010, G-070, G-008, G-047, G-048 | ln-624, ln-625 |
| 03 | 2 | G-011, G-012, G-028, G-006, G-044, G-014 | ln-628, ln-629 |
| 04 | 3 | G-002, G-003, G-021, G-055, G-020, G-089, G-056 | ln-621, ln-643 |
| 05 | 4 | G-024, G-029, G-051, G-036, G-065, G-007 | ln-647, ln-641 |
| 06 | 4 | G-023, G-018, G-030, G-031, G-032, G-033 | ln-653, ln-629 |
| 07 | 5 | G-075, G-069, G-073, G-074, G-076, G-077 | ln-614, ln-641 |
| 08 | 5 | G-045, G-046, G-049, G-050, G-052, G-034 | ln-625, ln-626 |
| 09 | 6 | G-022, G-019, G-054, G-057, G-058, G-059 | ln-643, ln-654 |
| 10 | 6 | G-015, G-016, G-078, G-079, G-080, G-081 | ln-628, ln-641 |
| 11 | 7 | G-025, G-026, G-035, G-037, G-038, G-039, G-040 | ln-623, ln-651 |
| 12 | 7 | G-066, G-067, G-068 | ln-629, ln-641 |
| 13 | 7 | (verification only — no implementation) | ln-620, ln-621, ln-630, ln-625, ln-626 |

---

## §5 — Audit Skills Integration Map

| Phase | Post-Fix Skills | Purpose |
|-------|----------------|---------|
| 1 Critical | ln-614-docs-fact-checker, ln-624-code-quality-auditor | Table names correct; CB math sound |
| 2 Learning | ln-624-code-quality-auditor, ln-625-dependencies-auditor, ln-628-concurrency-auditor, ln-629-lifecycle-auditor | QuestDB queries; deps; thread safety; shutdown |
| 3 Security | ln-621-security-auditor, ln-643-api-contract-auditor | Auth; SQL injection; API contracts |
| 4 Session | ln-647-env-config-auditor, ln-641-pattern-analyzer, ln-653-runtime-performance-auditor, ln-629-lifecycle-auditor | Config alignment; session_match; latency; lifecycle |
| 5 AIM+Offline | ln-614-docs-fact-checker, ln-641-pattern-analyzer, ln-625-dependencies-auditor, ln-626-dead-code-auditor | Schema facts; AIM compliance; deps; dead code |
| 6 Command+CB | ln-643-api-contract-auditor, ln-654-resource-lifecycle-auditor, ln-628-concurrency-auditor, ln-641-pattern-analyzer | API contracts; resource leaks; thread safety; patterns |
| 7 Verify | ln-620-codebase-auditor, ln-621-security-auditor, ln-630-test-auditor, ln-625-dependencies-auditor, ln-626-dead-code-auditor | Full suite vs Phase 1 baseline |

---

## §6 — Dashboard

| Status | Count |
|--------|-------|
| UNRESOLVED | 6 |
| DECISION_NEEDED | 0 |
| DEFERRED | 33 |
| FIXED | 51 |
| VERIFIED | 10 |
| **TOTAL** | **100** |

---

## §7 — Changelog

(Empty — executors populate after each session.)

| Date | Session | Action | Gap IDs | Notes |
|------|---------|--------|---------|-------|
| 2026-04-09 | 01 | FIXED | G-004 | Telegram bot table names: asset_registry→asset_universe, trade_outcomes→trade_outcome_log |
| 2026-04-09 | 01 | FIXED | G-005 | Replay engine CB table: circuit_breaker→circuit_breaker_params |
| 2026-04-09 | 01 | FIXED | G-017 | LONDON→LON in 8 files, NY_PRE added to SESSION_IDS, ZN/ZB→NY per DEC-07 |
| 2026-04-09 | 01 | FIXED | G-001 | CB rho_bar: replaced per-scalar np.corrcoef with paired-vector Pearson correlation |
| 2026-04-09 | 01 | FIXED | G-013 | Added model_m filter to CB trade query SQL |
| 2026-04-09 | 01 | FIXED | G-027 | Implemented _check_data_source_for_feature and _has_valid_timestamp with real checks |
| 2026-04-09 | 02 | FIXED | G-009 | b1_aim_lifecycle.py: 4 queries migrated to LATEST ON last_updated PARTITION BY aim_id, asset_id |
| 2026-04-09 | 02 | FIXED | G-010 | b1_dma_update.py: _load_active_aims and _load_ewma_regime migrated to LATEST ON |
| 2026-04-09 | 02 | FIXED | G-070 | Systematic LATEST ON migration: 33 queries across 22 files converted |
| 2026-04-09 | 02 | FIXED | G-008 | orchestrator.py _run_daily: load AIM modifiers from D01 instead of passing empty dict |
| 2026-04-09 | 02 | FIXED | G-047 | Added river>=0.21 to captain-offline/requirements.txt |
| 2026-04-09 | 02 | FIXED | G-048 | ADWIN/autoencoder state persistence via D04.adwin_states with pickle+JSON serialization |
| 2026-04-09 | 03 | FIXED | G-011 | Level 2 debounce: _level2_active dict tracks per-asset changepoint events, fires once per event |
| 2026-04-09 | 03 | FIXED | G-012 | Level 3 check moved before Level 2 with early return — mutually exclusive tiers |
| 2026-04-09 | 03 | FIXED | G-028 | _publish_trade_outcome: 3-attempt retry with exponential backoff (0.5s, 1s, 2s) |
| 2026-04-09 | 03 | FIXED | G-006 | threading.Lock guards open_positions + shadow_positions across main and listener threads |
| 2026-04-09 | 03 | FIXED | G-044 | stop() joins _redis_thread with 5s timeout; thread ref stored in __init__ |
| 2026-04-09 | 03 | FIXED | G-014 | Removed SEED=42 from b7_tsm_simulation.py and b6_auto_expansion.py — system entropy used |
| 2026-04-09 | 03-V | VERIFIED | G-011, G-012, G-028, G-006, G-044, G-014 | Validation Cycle 03: all 6 ALIGNED. G-NEW-007/008 lock scope + G-NEW-010/011 shutdown concerns tracked as follow-ups |
| 2026-04-09 | 04 | FIXED | G-002 | JWT auth middleware (DEC-01): PyJWT + BaseHTTPMiddleware, /auth/token login endpoint, Bearer validation on all non-exempt routes |
| 2026-04-09 | 04 | FIXED | G-003 | Removed /system/git-pull endpoint entirely (DEC-02) — 108 lines of RCE-capable code deleted |
| 2026-04-09 | 04 | FIXED | G-021 | SQL injection: f-string role interpolation replaced with $N parameterized placeholders |
| 2026-04-09 | 04 | FIXED | G-055 | WebSocket auth: token query param validated against JWT, user_id must match sub claim |
| 2026-04-09 | 04 | FIXED | G-020 | Docker CLI + Compose plugin removed from Dockerfile, Docker socket + repo bind mounts removed from docker-compose.yml |
| 2026-04-09 | 04 | FIXED | G-089 | Non-root USER appuser (UID 1000) added to all 4 Dockerfiles with proper directory ownership |
| 2026-04-09 | 04 | FIXED | G-056 | str(exc) in 12 HTTP responses replaced with generic messages; full exceptions logged server-side |
| 2026-04-09 | 05 | FIXED | G-024 | Offline scheduler: datetime.now() → now_et() (ZoneInfo America/New_York). Added now_et() helper to shared/constants.py |
| 2026-04-09 | 05 | FIXED | G-029 | Online B1: 3 datetime.now() → now_et() in b1_data_ingestion.py and b1_features.py |
| 2026-04-09 | 05 | FIXED | G-051 | Offline-wide: 16 datetime.now() → now_et() across 5 files (b2, b4, b5, b7, b9) — zero naive timestamps in captain-offline |
| 2026-04-09 | 05 | FIXED | G-036 | _get_session_open_time(): reads per-session or_start from session_registry.json instead of hardcoded 09:30 |
| 2026-04-09 | 05 | FIXED | G-065 | ZN/ZB already mapped to NY in Session 01 (G-017); status updated from UNRESOLVED to FIXED |
| 2026-04-09 | 05 | FIXED | G-007 | _get_contract_multiplier(): queries D00 point_value per asset instead of hardcoded 50.0 (ES) |
| 2026-04-09 | 06 | FIXED | G-023 | _prefetch_market_data(): ThreadPoolExecutor(max_workers=10) fetches price/volume for all assets concurrently; _run_data_moderator uses pre-fetched data |
| 2026-04-09 | 06 | FIXED | G-018 | _post(): timeout=10, 429 retry with exponential backoff (1s/2s/4s), Retry-After header support; authenticate() timeout=10 |
| 2026-04-09 | 06 | FIXED | G-030 | VIX spike: vix_provider + D17 threshold; regime shift: module-level cache set by orchestrator after B2; commission: wired to get_expected_fee() + D17 fallback |
| 2026-04-09 | 06 | FIXED | G-031 | _get_point_value(): replaced hardcoded POINT_VALUES dict with D00 asset_universe LATEST ON query, fallback to 50.0 |
| 2026-04-09 | 06 | FIXED | G-032 | Expired shadows now call _resolve_shadow("TIMEOUT", live_price) instead of silently dropping; Offline Category A learning gets complete signal universe |
| 2026-04-09 | 06 | FIXED | G-033 | _update_capital_and_cb(): D16 + D23 reads and writes in single cursor context; replaces separate _update_capital_silo + _update_intraday_cb_state calls |
| 2026-04-09 | 06-V | VERIFIED | G-023, G-018, G-032, G-033 | Validation Cycle 06: 4 ALIGNED, 2 PARTIAL. G-030 PARTIAL: VIX uses flat threshold not z-score + wrong table `system_params`. G-031 PARTIAL: wrong table `asset_universe`. Both runtime-breaking. |
| 2026-04-09 | 07 | FIXED | G-075 | Already resolved — p3_spread_history table present in init_questdb.py:647-664 with correct schema |
| 2026-04-09 | 07 | FIXED | G-069 | Already resolved — table + comment documented in init_questdb.py:647-664 |
| 2026-04-09 | 07 | FIXED | G-073 | DEC-08: AIM-07 disabled — removed from dispatch table (aim_compute.py), features set to None (b1_features.py), feature map cleared |
| 2026-04-09 | 07 | FIXED | G-074 | D30-based realised vol fallback for all assets in _get_realised_vol + _get_trailing_overnight_vrp; replay path in aim_feature_loader.py updated; ES-only docstrings removed |
| 2026-04-09 | 07 | FIXED | G-076 | b5_sensitivity.py:238: json.dumps({asset_id: FRAGILE_MODIFIER}) → plain FRAGILE_MODIFIER float |
| 2026-04-09 | 07 | FIXED | G-077 | aim_feature_loader.py: replay path builds rolling 20d correlation series + z_score() instead of using raw Pearson r |
| 2026-04-09 | 08 | FIXED | G-045 | bootstrap.py: removed `session == default_session` filter so regime filtering applies to all sessions in multi-session bootstrap |
| 2026-04-09 | 08 | FIXED | G-046 | b1_aim16_hmm.py: replaced hand-rolled Baum-Welch (~150 lines) with hmmlearn.hmm.GaussianHMM per DEC-05 resolution |
| 2026-04-09 | 08 | FIXED | G-049 | Already resolved by G-076 (Session 07) — FRAGILE_MODIFIER passed as plain float, not JSON dict |
| 2026-04-09 | 08 | FIXED | G-050 | b9_diagnostic.py: MAX_ACTION_QUEUE_SIZE=1000; oldest entries dropped when exceeded before D22 store |
| 2026-04-09 | 08 | FIXED | G-052 | b8_kelly_update.py: comprehensive docstring documenting D12 join strategy (per-cell kelly_full + shrinkage row at regime=ALL,session=0) |
| 2026-04-09 | 08 | FIXED | G-034 | Removed dead b3_aim_aggregation.py shim; inlined imports to shared.aim_compute in orchestrator.py and replay_full_pipeline.py |
| 2026-04-09 | 09 | FIXED | G-022 | _update_account_balance: reads latest D08 snapshot, inserts corrected row with updated current_balance (QuestDB append). Event log audit trail preserved. |
| 2026-04-09 | 09 | FIXED | G-019 | f_target_max read from D17 via _get_d17_param() with 0.03 fallback; f_target_max added to seed_system_params.py risk category |
| 2026-04-09 | 09 | FIXED | G-054 | start_replay + start_batch_replay: completed/error/stopped sessions removed from _active_sessions on new replay start. Prevents unbounded dict growth. |
| 2026-04-09 | 09 | FIXED | G-057 | route_notification publishes JSON payload to CH_ALERTS (captain:alerts) Redis channel after GUI/Telegram delivery |
| 2026-04-09 | 09 | FIXED | G-058 | get_incident_detail: moved return inside except block to fix NameError on exc; error message uses generic string (no exception leakage) |
| 2026-04-09 | 09 | FIXED | G-059 | telegram_bot.py send_message: self._token masked with *** in exception strings before logging |
| 2026-04-09 | 10 | FIXED | G-015 | threading.Lock (_state_lock) guards _user_stream, _account_data, _pipeline_stage. build_dashboard_snapshot snapshots atomically, passes to sub-functions |
| 2026-04-09 | 10 | FIXED | G-016 | threading.Lock (_ws_lock) guards _ws_sessions dict. gui_push snapshots under lock; connect/disconnect/cleanup all acquire lock |
| 2026-04-09 | 10 | FIXED | G-078 | AIM-16 _aim16_hmm re-added to dispatch table in aim_compute.py per DEC-06 resolution A |
| 2026-04-09 | 10 | FIXED | G-079 | 7 replay-unavailable features (pcr_z, gex, cot_smi, cot_speculator_z, event_proximity, events_today, cl_basis) stubbed as None in aim_feature_loader.py |
| 2026-04-09 | 10 | FIXED | G-080 | CB L5/L6 documented as V3 amendment per DEC-03 resolution B. Original spec has 5 layers; code keeps 7 |
| 2026-04-09 | 10 | FIXED | G-081 | get_ewma_for_regime() extracted to shared/statistics.py; local copies removed from b4_kelly_sizing.py, b5_trade_selection.py, b6_signal_output.py |
