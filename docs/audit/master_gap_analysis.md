# Captain System — Master Gap Analysis

**Generated:** 2026-04-09  
**Spec source:** `docs/audit/spec_reference.md` (13 sections, §1–§13)  
**Code source:** `docs/audit/` (4 Phase 1 reports) + direct codebase verification (23 checks)  
**Methodology:** Spec-to-code cross-reference — every gap has both a spec citation and a code citation

---

## Part 1 — Summary Statistics

| Metric | Count |
|--------|-------|
| Total spec components surveyed | 103 |
| Aligned (code matches spec) | 38 |
| Divergent (code differs from spec) | 32 |
| Stubbed (TODO / placeholder / always-true) | 11 |
| Missing (spec requires, code absent) | 22 |
| **Total unique gaps documented** | **100** |

**By severity:**

| Severity | Count |
|----------|-------|
| CRITICAL | 7 |
| HIGH | 22 |
| MEDIUM | 38 |
| LOW | 33 |

**By pipeline:**

| Area | Gaps |
|------|------|
| Online Pipeline (B1–B9) | 20 |
| Offline Pipeline (B1–B9) | 20 |
| Command Pipeline (B1–B10) | 21 |
| Session/Trigger | 5 |
| QuestDB Schema | 6 |
| AIM Implementation | 8 |
| Kelly / Circuit Breaker | 5 |
| Feedback Loops | 6 |
| GUI / Security | 9 |

---

## Part 2 — Critical Gaps (CRITICAL and HIGH)

### G-001: Circuit Breaker Serial-Correlation Always ±1.0 or NaN

- **Severity:** CRITICAL
- **Spec Ref:** §7 Circuit Breaker Layer 4 — `beta_b = OLS(loss_sequence)`, used to scale L4 basket-expectancy halt threshold
- **Code Ref:** `captain-offline/captain_offline/blocks/b8_cb_params.py:119-120`
- **Gap:** `np.corrcoef([arr[i]], [arr[j]])` computes correlation of two single-element arrays; mathematically always returns ±1.0 or NaN. `beta_b` (rho_bar) fed to the online circuit breaker is therefore degenerate on every run.
- **Impact:** Layer 4 correlation-based halt is mathematically broken — either always fires (1.0) or never fires (NaN). Serial loss correlation protection is non-functional.
- **Dependencies:** G-058 (CB params cross-contamination also corrupts inputs)
- **Complexity:** M

---

### G-002: No Authentication on Any API Endpoint

- **Severity:** CRITICAL
- **Spec Ref:** §10 Supporting Systems — "authenticated REST and WebSocket endpoints; token-based access control"
- **Code Ref:** `captain-command/captain_command/api.py` (all endpoints) — no auth middleware registered
- **Gap:** Every REST and WebSocket endpoint, including financial commands (execute trade, override CB, git-pull), is accessible by any process on the host with no authentication.
- **Impact:** Any code running on the host can trigger trade execution, modify system state, or query all financial data.
- **Dependencies:** G-003 (RCE via git-pull), G-009 (WebSocket impersonation), G-099 (RPT-11 financial export)
- **Complexity:** L

---

### G-003: Unauthenticated Remote Code Execution via git-pull Endpoint

- **Severity:** CRITICAL
- **Spec Ref:** §10 Supporting Systems — secure remote update mechanism
- **Code Ref:** `captain-command/captain_command/api.py` — `/system/git-pull` runs `git pull && docker compose up --build` in subprocess; no authentication
- **Gap:** Any process on the host can POST to `/system/git-pull` triggering a full container rebuild with arbitrary git state. Docker socket mounted inside the container for the rebuild.
- **Impact:** Arbitrary code execution on host; Docker socket escape vector means full host compromise.
- **Dependencies:** G-002, G-095 (Docker socket)
- **Complexity:** M

---

### G-004: Telegram Bot Queries Non-Existent Table Names — /status and /trades Crash

- **Severity:** CRITICAL
- **Spec Ref:** §9 Dataset D00 (`p3_d00_asset_universe`), D03 (`p3_d03_trade_outcome_log`)
- **Code Ref:** `captain-command/captain_command/telegram_bot.py:102` (`p3_d00_asset_registry`), `:112,160` (`p3_d03_trade_outcomes`)
- **Gap:** Two wrong table names in Telegram query strings; correct names are `p3_d00_asset_universe` and `p3_d03_trade_outcome_log`. Both commands crash at runtime with SQL errors.
- **Impact:** `/status` and `/trades` Telegram commands never return data; operator visibility during live sessions is completely absent.
- **Dependencies:** None
- **Complexity:** S

---

### G-005: Replay Engine Queries Wrong Circuit Breaker Table — CB Params Silent Failure

- **Severity:** CRITICAL
- **Spec Ref:** §9 Dataset D25 (`p3_d25_circuit_breaker_params`)
- **Code Ref:** `shared/replay_engine.py:289` — queries `p3_d25_circuit_breaker` (wrong name)
- **Gap:** Replay engine queries a non-existent table. QuestDB returns empty result set with no error; CB modifiers are silently absent from all replay runs.
- **Impact:** Every replay session returns wrong results — CB layer is inactive. AIM A/B validation and what-if analysis both produce incorrect outputs.
- **Dependencies:** G-004 (pattern: wrong table names)
- **Complexity:** S

---

### G-006: Thread-Unsafe Position List — Race on open_positions and shadow_positions

- **Severity:** HIGH
- **Spec Ref:** §5 Online B7 (position monitor), §11 Feedback Loop 1 — correct trade outcome must reach Offline
- **Code Ref:** `captain-online/captain_online/orchestrator.py:61-62,762,769,591-610`
- **Gap:** `open_positions` and `shadow_positions` lists are mutated from the main thread and the command-listener thread with no lock. Concurrent access can silently drop positions or raise `ValueError: list.remove(x): x not in list`.
- **Impact:** Trade outcomes silently lost; feedback loop 1 (AIM meta-learning) and loop 3 (Kelly EWMA) receive incomplete data.
- **Dependencies:** G-052 (trade outcome publish no retry)
- **Complexity:** M

---

### G-007: AIM-03 GEX Contract Multiplier Hardcoded to ES Default

- **Severity:** HIGH
- **Spec Ref:** §3 AIM-03 — Gamma Exposure (GEX) uses per-asset contract multiplier from D00
- **Code Ref:** `captain-online/captain_online/blocks/b1_features.py:955-956` — `_get_contract_multiplier()` always returns `50.0` (ES multiplier)
- **Gap:** All 10 assets use ES multiplier (50). Correct values: MES=5, NQ=20, MNQ=2, M2K=5, MYM=0.5, NKD=5, MGC=10, ZB=1000, ZN=1000. GEX values wrong by factors of 10–200× for all non-ES assets.
- **Impact:** AIM-03 fires incorrect signals for 9 of 10 assets; DMA weighted average corrupted on each non-ES session.
- **Dependencies:** G-070 (AIM-03 cannot fire)
- **Complexity:** S

---

### G-008: Offline Drift Detection is a Complete No-Op

- **Severity:** HIGH
- **Spec Ref:** §4 Offline B9 — Decay/Drift Detection using ADWIN on AIM features
- **Code Ref:** `captain-offline/captain_offline/orchestrator.py:572` — `run_drift_detection(asset_id, {})` called with empty dict; `for aim_id, features in aim_features.items()` never iterates
- **Gap:** `aim_features` is always `{}` at call site. The entire drift detection block executes but processes zero features.
- **Impact:** Feedback Loop 2 (Decay Detection) is completely non-functional. Level 2/3 escalation via BOCPD is never triggered by drift. System cannot detect feature regime shift.
- **Dependencies:** G-072 (river not in requirements anyway)
- **Complexity:** M

---

### G-009: AIM Lifecycle Reads Stale State — Missing LATEST ON

- **Severity:** HIGH
- **Spec Ref:** §3 AIM Lifecycle — "latest state row per AIM drives lifecycle transitions"
- **Code Ref:** `captain-offline/captain_offline/blocks/b1_aim_lifecycle.py:55` — `ORDER BY aim_id, last_updated DESC` without `LATEST ON`
- **Gap:** QuestDB is an append-only time-series DB. `ORDER BY` without `LATEST ON` may return a historical row for an AIM_ID if the dedup logic incorrectly takes the first-seen AIM_ID in the sorted set.
- **Impact:** AIM lifecycle transitions (INSTALLED → COLLECTING → WARM_UP → ELIGIBLE → ACTIVE) may operate on stale state. Incorrect lifecycle state causes wrong learning gate evaluations.
- **Dependencies:** G-010 (DMA update has same bug)
- **Complexity:** S

---

### G-010: DMA Update Reads Stale AIM Weights — Missing LATEST ON

- **Severity:** HIGH
- **Spec Ref:** §4 Offline B1 (DMA Update) — latest meta-weight row from D02 is base for DMA delta
- **Code Ref:** `captain-offline/captain_offline/blocks/b1_dma_update.py:43-56` — `_load_active_aims` uses `ORDER BY aim_id` without `LATEST ON`
- **Gap:** Same pattern as G-009. DMA update overwrites weights using stale base values, corrupting the weight trajectory.
- **Impact:** Feedback Loop 1 (AIM Meta-Learning) accumulates errors on every trade. AIM weights drift from their true values.
- **Dependencies:** G-009, G-082 (LATEST ON missing broadly)
- **Complexity:** S

---

### G-011: Level 2 Escalation Fires Repeatedly With No Cooldown

- **Severity:** HIGH
- **Spec Ref:** §7 Circuit Breaker — "Level 2 escalation triggers once per changepoint event; debounced"
- **Code Ref:** `captain-offline/captain_offline/blocks/b2_level_escalation.py:186` — fires every trade where `cp_probability > 0.8` with no cooldown
- **Gap:** If cp_probability stays elevated (common during a volatile regime), Level 2 fires on every trade outcome. No flag is set to block re-entry until manual reset or probability drops below threshold.
- **Impact:** Repeated Level 2 sizing overrides and alert spam. D12 Kelly params overwritten N times in rapid succession.
- **Dependencies:** G-012 (Level 2 and Level 3 fire simultaneously)
- **Complexity:** S

---

### G-012: Level 2 and Level 3 Escalation Fire Simultaneously

- **Severity:** HIGH
- **Spec Ref:** §7 Circuit Breaker — Level 2 (sizing reduction) and Level 3 (halt + P1/P2 rerun) are mutually exclusive escalation tiers
- **Code Ref:** `captain-offline/captain_offline/blocks/b2_level_escalation.py:186-197` — no `return` or `elif` between Level 2 check (l186) and Level 3 check (l194); both fire when `cp_prob > 0.9`
- **Gap:** Both Level 2 (reduce sizing) and Level 3 (halt + rerun) execute in same pass when cp_probability exceeds 0.9. Conflicting actions result.
- **Impact:** D12 Kelly params reduced AND system halt triggered simultaneously. Undefined system state.
- **Dependencies:** G-011
- **Complexity:** S

---

### G-013: CB Parameters Cross-Contaminated Across Models

- **Severity:** HIGH
- **Spec Ref:** §7 Circuit Breaker — "per-model CB parameter estimation, keyed by (account_id, model_m)"
- **Code Ref:** `captain-offline/captain_offline/blocks/b8_cb_params.py:40-54` — `model_m` parameter present in function signature but unused in SQL; loads ALL trades for account regardless of model
- **Gap:** CB beta_b is estimated from the union of all models' trades, not per-model trades. Models with very different loss serial correlations contaminate each other's CB parameters.
- **Impact:** Per-model CB tuning does not work. High-frequency models with different loss correlation contaminate low-frequency models' CB params and vice versa.
- **Dependencies:** G-001 (CB correlation already broken separately)
- **Complexity:** S

---

### G-014: Monte Carlo and GA Always Produce Deterministic Output

- **Severity:** HIGH
- **Spec Ref:** §4 Offline B6 (Auto-Expansion) — "stochastic GA exploration to discover new strategy candidates"
- **Code Ref:** `captain-offline/captain_offline/blocks/b7_tsm_simulation.py:118-119`; `b6_auto_expansion.py:230-231` — `SEED=42` globally set before both MC and GA runs
- **Gap:** Fixed global seed makes both the Monte Carlo pass_probability and GA candidate mutations fully deterministic. Every invocation of B6/B7 returns the same output regardless of current market state.
- **Impact:** Auto-expansion never discovers genuinely new strategy candidates. Strategy space exploration is a no-op after first run.
- **Dependencies:** None
- **Complexity:** S

---

### G-015: Thread-Unsafe GUI Financial Data Globals

- **Severity:** HIGH
- **Spec Ref:** §6 Command B2 — "real-time GUI data served to multiple concurrent WebSocket clients"
- **Code Ref:** `captain-command/captain_command/blocks/b2_gui_data_server.py` — module-level globals (positions, balances, signals, etc.) modified from orchestrator thread and FastAPI request threads simultaneously without locks
- **Gap:** Multiple concurrent read/write paths on shared financial state dicts with no synchronization. Python dict writes can interleave under CPython GIL for compound operations.
- **Impact:** GUI clients can receive partially-updated or inconsistent financial snapshots during live trading.
- **Dependencies:** G-016
- **Complexity:** M

---

### G-016: Thread-Unsafe WebSocket Connection Registry on Trade Path

- **Severity:** HIGH
- **Spec Ref:** §6 Command B2 — "broadcast trade notifications to all active WebSocket clients"
- **Code Ref:** `captain-command/captain_command/api.py` — `_active_connections` dict accessed from multiple threads without lock
- **Gap:** Trade notifications triggered from orchestrator thread concurrently with WebSocket connect/disconnect events from API threads. Dict can be mutated during iteration.
- **Impact:** Race condition on trade execution path — concurrent WS broadcasts can corrupt or drop trade notifications.
- **Dependencies:** G-015
- **Complexity:** M

---

### G-017: Session Name Mismatch — LON vs LONDON

- **Severity:** HIGH
- **Spec Ref:** §1 Session Definitions — LON session for London-hours assets (NKD is LON)
- **Code Ref:** `shared/constants.py` uses `LON`; `config/session_registry.json` uses `LONDON`; `SESSION_IDS` has no entry for `NY_PRE`
- **Gap:** Session name comparison `asset.session == SESSION_IDS["LON"]` vs JSON key `"LONDON"` never matches. Assets mapped to LON/LONDON session never trigger in session controller. `NY_PRE` (ZN, ZB, MGC) has no ID entry.
- **Impact:** NKD never enters APAC session. ZN/ZB/MGC may not trigger at correct session open. Three assets trade at wrong time or not at all.
- **Dependencies:** G-065 (ZN/ZB session config conflict)
- **Complexity:** S

---

### G-018: No Timeout or Rate Limiting on TopstepX API Calls

- **Severity:** HIGH
- **Spec Ref:** §10 Supporting Systems — "TopstepX REST client handles rate limiting and timeout gracefully"
- **Code Ref:** `shared/topstep_client.py` (all endpoints) — no `timeout=` on any `requests.post()` call; no throttling between requests
- **Gap:** A hung TopstepX API server blocks the calling thread indefinitely. No 429 retry logic. Under 10-asset parallel data fetch, this can block B1 for arbitrarily long periods.
- **Impact:** A single TopstepX API outage during pre-session data ingestion hangs the entire online process indefinitely. B1 `<9s` latency spec violated without bound.
- **Dependencies:** None
- **Complexity:** M

---

### G-019: Hardcoded Payout MDD Threshold in Reconciliation

- **Severity:** HIGH
- **Spec Ref:** §6 Command B8 — "payout recommendation based on configurable MDD% from D17 system_params"
- **Code Ref:** `captain-command/captain_command/blocks/b8_reconciliation.py:336` — `f_target_max = 0.03` hardcoded
- **Gap:** Payout target MDD threshold is hardcoded to 3%; not loaded from D17 or any config. Cannot be changed without code modification.
- **Impact:** Payout recommendations wrong for any account type other than TopstepX 150K default. Silently blocks or permits payouts at wrong thresholds.
- **Dependencies:** None
- **Complexity:** S

---

### G-020: Docker Socket Mounted Inside Command Container

- **Severity:** HIGH
- **Spec Ref:** §10 Supporting Systems — "minimal container attack surface; containers run with least privilege"
- **Code Ref:** `captain-command/Dockerfile:9-14` — Docker CLI + Compose installed; Docker socket (`/var/run/docker.sock`) mounted
- **Gap:** The captain-command container has full Docker daemon access. If the container is compromised (e.g., via G-003 git-pull RCE), an attacker can spawn arbitrary containers with any privileges on the host.
- **Impact:** Container escape to full host access.
- **Dependencies:** G-003
- **Complexity:** M

---

### G-021: SQL Injection in Notifications Block

- **Severity:** HIGH
- **Spec Ref:** §10 Supporting Systems — "parameterized SQL queries throughout"
- **Code Ref:** `captain-command/captain_command/blocks/b7_notifications.py:433-436` — f-string SQL: `role_list = ",".join(f"'{r}'" for r in roles)` in `_get_users_by_roles()`
- **Gap:** Role values interpolated directly into SQL string. If role values are ever sourced from external input, this is a SQL injection vulnerability.
- **Impact:** SQL injection leading to data exfiltration or database corruption if role input is ever user-controlled.
- **Dependencies:** G-002 (no auth means any caller can trigger this path)
- **Complexity:** S

---

### G-022: Reconciliation Detects But Never Fixes D08 Balance

- **Severity:** HIGH
- **Spec Ref:** §6 Command B8 — "reconciliation corrects D08 (topstep_state) balance when broker and local state diverge"
- **Code Ref:** `captain-command/captain_command/blocks/b8_reconciliation.py:483-515` — `_update_account_balance()` and `_update_topstep_state()` only log to `session_event_log`; no new D08 row inserted
- **Gap:** Reconciliation detects mismatches and logs them but never writes a correction row to D08. Same mismatch is re-detected on every subsequent run. D08 permanently diverges from broker reality.
- **Impact:** Feedback Loop 6 (SOD Compounding) reads stale D08 balance. Capital silo sizing is permanently wrong after first divergence.
- **Dependencies:** None
- **Complexity:** M

---

### G-023: B1 Data Ingestion Violates <9s Latency Budget

- **Severity:** HIGH
- **Spec Ref:** §1 Config — "B1 latency budget: <9s total"; §2 Online B1 — parallel asset data fetch
- **Code Ref:** `captain-online/captain_online/blocks/b1_data_ingestion.py:497-558` — synchronous sequential REST calls for 10 assets × 3 calls each
- **Gap:** Up to 90 sequential REST calls on the main thread before any blocking call returns. With 1-2s per call, total B1 latency can reach 90–180s on a slow API day.
- **Impact:** Pre-session data pipeline misses session open by many minutes. No signals issued for a session start.
- **Dependencies:** G-018 (no timeout makes this unbounded)
- **Complexity:** L

---

### G-024: Offline Scheduler Uses Naive datetime.now() — Wrong Timezone

- **Severity:** HIGH
- **Spec Ref:** §1 Config REQ-4 — "timezone is always America/New_York; ASSERT at session start"
- **Code Ref:** `captain-offline/captain_offline/orchestrator.py:529` — `datetime.now()` (system local time) used for `hour >= 16` daily trigger
- **Gap:** If Docker container system timezone is UTC (default) or any non-ET zone, the daily scheduled blocks (19:00 ET = midnight UTC during EDT) fire at wrong times. Session boundary resets miss the 19:00 ET cutoff.
- **Impact:** Daily SOD reset (Feedback Loop 6) fires at wrong time. Kelly/EWMA/CB updates after session close may not run before next session open.
- **Dependencies:** G-081 (same root cause affects B3-B9)
- **Complexity:** S

---

### G-025: b3_pseudotrader.py — God Module (1,432 Lines, 6 Responsibilities)

- **Severity:** HIGH
- **Spec Ref:** §4 Offline B3 — single-responsibility pseudotrader replay block
- **Code Ref:** `captain-offline/captain_offline/blocks/b3_pseudotrader.py` — 1,432 lines; 15+ functions; implements P3-PG-09 + 09B + 09C + account-aware replay + lifecycle replay + two-forecast path
- **Gap:** Block is a god module violating SRP. Cyclomatic complexity >20 in core functions. Impossible to unit test individual responsibilities without pulling in all 6 others.
- **Impact:** Bug fixes in one path risk breaking other paths. Cannot be audited or tested in isolation. The most complex offline block has the lowest test coverage.
- **Dependencies:** None
- **Complexity:** XL

---

### G-026: Reconciliation Hardcode primary_user in TSM Linking

- **Severity:** HIGH
- **Spec Ref:** §1 Config REQ-6 — "multi-user from day one; never hardcode single-user assumptions"
- **Code Ref:** `captain-command/captain_command/main.py:131` — `best["user_id"] = "primary_user"` hardcoded during TSM linking at startup
- **Gap:** Command startup always links the best TSM account to `primary_user`. Multi-user deployments never link secondary users correctly.
- **Impact:** Multi-user capital siloing broken. Instance B (parity=1) may share TSM state with Instance A.
- **Dependencies:** None
- **Complexity:** S

---

### G-027: Data Moderator Stale/Bad-Timestamp Detection Disabled

- **Severity:** HIGH
- **Spec Ref:** §2 Online B1 REQ-3 — data moderator checks for stale data and invalid timestamps; flags as DATA_HOLD
- **Code Ref:** `captain-online/captain_online/blocks/b1_data_ingestion.py:574,578` — `_check_data_source_for_feature()` and `_has_valid_timestamp()` both return `True` unconditionally
- **Gap:** Data quality checks always pass. Stale prices, future-dated timestamps, and corrupted data fields are accepted and passed downstream.
- **Impact:** AIMs compute signals on corrupted data. P2_HIGH incidents for bad data are never raised. System proceeds blindly on bad market data.
- **Dependencies:** None
- **Complexity:** M

---

### G-028: B7 Trade Outcome Redis Publish — No Retry or Dead-Letter

- **Severity:** HIGH
- **Spec Ref:** §11 Feedback Loop 1 — "trade outcome must reliably reach Offline via Redis"
- **Code Ref:** `captain-online/captain_online/blocks/b7_position_monitor.py:336-360` — Redis publish failure logged but no retry or dead-letter queue
- **Gap:** If Redis is temporarily unavailable when a position closes, the trade outcome message is silently dropped. No retry, no queue, no crash.
- **Impact:** Feedback Loop 1 (AIM meta-learning), Loop 3 (Kelly EWMA), and Loop 4 (beta_b) all miss the trade. System learns from a biased sample. Survivorship bias accumulates over time.
- **Dependencies:** G-006 (race also risks dropping outcomes)
- **Complexity:** M

---

---

## Part 3 — Gaps by Section

### Section 1: Online Pipeline Gaps (B1–B9)

| Gap ID | Severity | Block | File:Line | Gap Description |
|--------|----------|-------|-----------|-----------------|
| G-006 | HIGH | B7 | orchestrator.py:61-62 | Race on open_positions / shadow_positions with no lock |
| G-007 | HIGH | B1 | b1_features.py:955-956 | AIM-03 GEX contract multiplier hardcoded to ES for all assets |
| G-023 | HIGH | B1 | b1_data_ingestion.py:497-558 | Sequential synchronous REST fetches violate <9s latency budget |
| G-027 | HIGH | B1 | b1_data_ingestion.py:574,578 | Data moderator stale/bad-timestamp checks always return True |
| G-028 | HIGH | B7 | b7_position_monitor.py:336-360 | Trade outcome Redis publish has no retry or dead-letter fallback |
| G-029 | MEDIUM | B1 | b1_data_ingestion.py:436,642; b1_features.py:546 | `datetime.now()` without ET timezone in 3 locations |
| G-030 | MEDIUM | B7 | b7_position_monitor.py:419-427 | VIX spike, regime-shift, and API commission checks are all stubs |
| G-031 | MEDIUM | B7 | b7_shadow_monitor.py:217-221 | Shadow monitor POINT_VALUES dict hardcoded — breaks if assets change |
| G-032 | MEDIUM | B7 | b7_shadow_monitor.py:87-93 | Expired shadow positions (>8h) silently dropped, no TIMEOUT outcome published |
| G-033 | MEDIUM | B7 | b7_position_monitor.py:279-296 | Non-atomic capital/CB state updates — concurrent close races drift capital silo |
| G-034 | MEDIUM | B3 | aim_compute.py / b3_aim_aggregation.py | b3_aim_aggregation.py is pure re-export shim — dead indirection layer |
| G-035 | MEDIUM | B4 | b4_kelly_sizing.py:461 + 5 others | `_parse_json()` duplicated 6× across blocks (8 lines each) |
| G-036 | MEDIUM | B1 | b1_features.py:1073-1082 | `_get_session_open_time()` always returns 9:30 ET — wrong for LON/APAC assets |
| G-037 | MEDIUM | B2 | b2_regime_probability.py:150-154 | Regime classifier returns 50/50 for C1-C3 assets — classifier is a no-op |
| G-038 | MEDIUM | B9 | b9_capacity_evaluation.py:108-117 | D00 queried per-asset inside loop — N+1 query for 10 assets |
| G-039 | MEDIUM | B9 | b9_capacity_evaluation.py:160-177 | Fetches ALL D17 session_log entries; filters by session_id in Python |
| G-040 | MEDIUM | B9 | b9_capacity_evaluation.py:124 | ASSET_CLASS_HOMOGENEITY constraint uses `"detail"` key; others use `"message"` |
| G-041 | LOW | B2 | b2_regime_probability.py:132-139 | Dead VRP fallback block — always falls through; unreachable code |
| G-042 | LOW | B2 | b2_regime_probability.py:75,83 | `regime_probs[asset_id]` set at l75 then unconditionally overwritten at l83 |
| G-043 | LOW | B7 | b7_shadow_monitor.py:225-232 | Shadow monitor `_get_live_price()` has no REST fallback if WebSocket drops |

---

### Section 2: Offline Pipeline Gaps (B1–B9)

| Gap ID | Severity | Block | File:Line | Gap Description |
|--------|----------|-------|-----------|-----------------|
| G-001 | CRITICAL | B8 | b8_cb_params.py:119-120 | CB serial correlation always ±1.0 or NaN — Layer 4 mathematically broken |
| G-008 | HIGH | B9 | orchestrator.py:572 | Drift detection called with empty feature dict — complete no-op |
| G-009 | HIGH | B1 | b1_aim_lifecycle.py:55 | AIM lifecycle reads stale state — `ORDER BY` without `LATEST ON` |
| G-010 | HIGH | B1 | b1_dma_update.py:43-56 | DMA update reads stale weights — `ORDER BY` without `LATEST ON` |
| G-011 | HIGH | B2 | b2_level_escalation.py:186 | Level 2 escalation fires on every trade, no cooldown |
| G-012 | HIGH | B2 | b2_level_escalation.py:186-197 | Level 2 and Level 3 escalation both fire simultaneously when cp_prob > 0.9 |
| G-013 | HIGH | B8 | b8_cb_params.py:40-54 | CB params estimated from all models — `model_m` unused in SQL |
| G-014 | HIGH | B6/B7 | b7_tsm_simulation.py:118; b6_auto_expansion.py:230 | SEED=42 makes Monte Carlo and GA fully deterministic |
| G-024 | HIGH | Orch | orchestrator.py:529 | Offline scheduler uses `datetime.now()` (not ET) for daily block trigger |
| G-025 | HIGH | B3 | b3_pseudotrader.py (entire) | God module — 1,432 lines, 6 responsibilities, cyclomatic complexity >20 |
| G-044 | MEDIUM | Orch | orchestrator.py:69 | `stop()` does not join Redis listener thread — mid-write outcome interrupted on SIGTERM |
| G-045 | MEDIUM | Orch | bootstrap.py:122 | Multi-session bootstrap only applies regime filtering to `default_session` |
| G-046 | MEDIUM | B1 | b1_aim16_hmm.py (entire) | `hmmlearn` in requirements.txt but block uses hand-rolled Baum-Welch instead |
| G-047 | MEDIUM | B1 | b1_drift_detection.py:49 | `river` (ADWIN) not in requirements.txt — primary drift path never available in Docker |
| G-048 | MEDIUM | B1 | b1_drift_detection.py:115-116 | ADWIN and autoencoder state in module-level dicts — lost on every container restart |
| G-049 | MEDIUM | B5 | b5_sensitivity.py:232-238 | AIM-13 modifier written as JSON dict `{"asset_id": 0.85}` not float into D01 |
| G-050 | MEDIUM | B9 | b9_diagnostic.py:833-882 | Action queue loaded and re-stored entirely with no size cap — unbounded growth |
| G-051 | MEDIUM | ALL | orchestrator.py + B3-B9 (~20 sites) | `datetime.now()` without ET timezone throughout offline blocks |
| G-052 | MEDIUM | B8 | b8_kelly_update.py:179-205 | Kelly shrinkage row linkage undocumented — online consumer must know join strategy |
| G-053 | LOW | B2 | b2_bocpd.py:80 | 501 NIGPrior objects recreated on every `update()` call — unnecessary allocations |

---

### Section 3: Command Pipeline Gaps (B1–B10)

| Gap ID | Severity | Block | File:Line | Gap Description |
|--------|----------|-------|-----------|-----------------|
| G-002 | CRITICAL | ALL | api.py (all endpoints) | No authentication on any API endpoint |
| G-003 | CRITICAL | B? | api.py `/system/git-pull` | Unauthenticated RCE — runs container rebuild on any POST |
| G-019 | HIGH | B8 | b8_reconciliation.py:336 | Payout MDD threshold hardcoded to 0.03; not loaded from D17 |
| G-020 | HIGH | Infra | captain-command/Dockerfile:9-14 | Docker socket mounted inside container |
| G-021 | HIGH | B7 | b7_notifications.py:433-436 | SQL injection in `_get_users_by_roles()` via f-string interpolation |
| G-022 | HIGH | B8 | b8_reconciliation.py:483-515 | Reconciliation logs mismatches but never writes D08 correction row |
| G-015 | HIGH | B2 | b2_gui_data_server.py | Thread-unsafe module-level globals for financial data |
| G-016 | HIGH | B2 | api.py (`_active_connections`) | Thread-unsafe WebSocket connection dict on trade path |
| G-026 | HIGH | Main | main.py:131 | `primary_user` hardcoded in TSM linking — multi-user broken |
| G-054 | MEDIUM | B11 | b11_replay_runner.py:206-218 | Completed replay sessions never removed from `_active_sessions` — memory leak |
| G-055 | MEDIUM | B11 | api.py WebSocket endpoint | `user_id` passed as query param with no verification — self-declared identity |
| G-056 | MEDIUM | B3 | api.py + b6_reports.py:137,396 | Internal exception messages leaked to API callers via `str(exc)` |
| G-057 | MEDIUM | B7 | b7_notifications.py:7 | B7 block does not publish to `captain:alerts` Redis channel (CH_ALERTS unused in B7) |
| G-058 | MEDIUM | B9 | b9_incident_response.py:257 | `NameError` on `exc` — dead code outside try/except references caught exception |
| G-059 | MEDIUM | B4 | telegram_bot.py:600 | Telegram bot token appears in URL strings (memory + HTTP access log exposure) |
| G-060 | LOW | Orch | orchestrator.py (scheduler) | Synchronous report generation/reconciliation in scheduler thread can block it |
| G-061 | LOW | Orch | orchestrator.py (config reads) | TOCTOU on config file reads — no atomic guarantee |
| G-062 | LOW | B7 | telegram_bot.py:39,246 | `_rate_window` and `_mute_until` dicts accessed from 2 threads without lock |
| G-063 | LOW | B9 | b9_incident_response.py:41 | `P1_CRITICAL` severity routes to GUI+Telegram only; Email missing per spec |
| G-064 | LOW | B6 | b6_reports.py (RPT-11) | RPT-11 (financial export) has no authorization check |
| G-065 | LOW | B11 | b11_replay_runner.py:230-235 | `config_overrides` TP/SL loop duplicated 3× (start_replay, run_whatif, batch) |

---

### Section 4: Session/Trigger Gaps

| Gap ID | Severity | Area | File:Line | Gap Description |
|--------|----------|------|-----------|-----------------|
| G-017 | HIGH | Config | shared/constants.py vs config/session_registry.json | Session name mismatch `LON` vs `LONDON`; `NY_PRE` has no SESSION_IDS entry |
| G-065 | MEDIUM | Config | config/session_registry.json | ZN/ZB mapped to `NY_PRE` (06:00 ET) in JSON but CLAUDE.md locked strategy lists them as `NY` |
| G-066 | MEDIUM | Online | captain-online/captain_online/blocks/ | No `b9_session_controller.py`; B9 is capacity evaluator — session trigger logic absent |
| G-067 | MEDIUM | Online | or_tracker.py (named, not b8_or_tracker.py) | OR tracker naming inconsistency; spec refers to it as B8 but file has no block prefix |
| G-068 | MEDIUM | Online | captain-online (no b5_compliance_gate.py) | Compliance gate block absent; compliance_gate.json config exists but no block enforcing it per spec naming |

---

### Section 5: QuestDB Schema Gaps

| Gap ID | Severity | Table | File:Line | Gap Description |
|--------|----------|-------|-----------|-----------------|
| G-004 | CRITICAL | D00, D03 | telegram_bot.py:102,112,160 | Telegram uses `p3_d00_asset_registry` and `p3_d03_trade_outcomes` — both wrong table names; crashes at runtime |
| G-005 | CRITICAL | D25 | shared/replay_engine.py:289 | Replay queries `p3_d25_circuit_breaker` (not `_params`) — silent empty result in all replay runs |
| G-069 | MEDIUM | Undoc | b1_features.py:700-706,1270 | `p3_spread_history` written and read but absent from schema docs and `init_questdb.py` |
| G-070 | MEDIUM | Multi | b1_aim_lifecycle.py, b1_dma_update.py, + ~10 more | `ORDER BY last_updated DESC LIMIT 1` used instead of `LATEST ON` across multiple blocks |
| G-071 | LOW | Meta | scripts/init_questdb.py header; CLAUDE.md | Documentation claims 29–30 tables; actual `init_questdb.py` has 38 `CREATE TABLE` statements |
| G-072 | LOW | D16/D23 | questdb_client.py:21,33 | Every `get_cursor()` opens a fresh TCP connection — no pooling; no query timeout |

---

### Section 6: AIM Implementation Gaps

| Gap ID | Severity | AIM | File:Line | Gap Description |
|--------|----------|-----|-----------|-----------------|
| G-007 | HIGH | AIM-03 | b1_features.py:955-956 | GEX contract multiplier hardcoded to ES; wrong for 9 of 10 assets |
| G-073 | MEDIUM | AIM-07 | b1_features.py (COT section) | COT stubs — `cot_smi` and `cot_speculator_z` never populated; AIM-07 always fires on null |
| G-074 | MEDIUM | AIM-01/02 | aim_compute.py + b1_features.py | AIM-01 and AIM-02 features ES-only — other assets get null/0 inputs |
| G-075 | MEDIUM | AIM-12 | b1_features.py:700-706 | AIM-12 requires `p3_spread_history` table not created by init_questdb.py — `spread_z` is always None on fresh DB |
| G-076 | MEDIUM | AIM-13 | b5_sensitivity.py:232-238 | AIM-13 modifier written as JSON dict not float — downstream parse errors |
| G-077 | MEDIUM | AIM-08 | shared/aim_feature_loader.py:193 | AIM-08 CORR_STRESS uses raw Pearson correlation as z-score proxy — `corr_z > 1.5` tier mathematically unreachable |
| G-078 | MEDIUM | AIM-16 | shared/aim_compute.py:637-649 | `_aim16_hmm()` defined but not in dispatch table (removed per DEC-06) — dead function |
| G-079 | MEDIUM | All | shared/aim_feature_loader.py | 7 features unavailable in replay: pcr_z, gex, cot_smi, cot_speculator_z, event_proximity, events_today, cl_basis |

---

### Section 7: Kelly / Circuit Breaker Gaps

| Gap ID | Severity | Layer | File:Line | Gap Description |
|--------|----------|-------|-----------|-----------------|
| G-001 | CRITICAL | CB L4 | b8_cb_params.py:119-120 | CB rho_bar (serial correlation) always ±1.0 or NaN — Layer 4 non-functional |
| G-013 | HIGH | CB L4 | b8_cb_params.py:40-54 | CB params cross-contaminated across models — per-model tuning disabled |
| G-080 | MEDIUM | CB L0-L6 | b5c_circuit_breaker.py:11 | Spec describes 5 CB layers; implementation has 7 (L0–L6 including safety layers L5/L6) — needs spec alignment or V3 amendment confirmation |
| G-081 | MEDIUM | Kelly | b4_kelly_sizing.py:292; b5_trade_selection.py:192; b6_signal_output.py:310 | `_get_ewma_for_regime()` duplicated 3× — inconsistent if one diverges |
| G-082 | LOW | Kelly L2 | b5c_circuit_breaker.py:304 | MDD fallback `or 4500.0` hardcoded — magic number; should come from D17 or named constant |

---

### Section 8: Feedback Loop Gaps

The spec defines 6 feedback loops (§11). Current status of each:

| Gap ID | Loop # | Severity | Gap Description |
|--------|--------|----------|-----------------|
| G-083 | Loop 1: AIM Meta-Learning | HIGH | **Partially broken** — G-028 (no retry on Redis publish) + G-006 (race on position list) mean outcomes are silently lost; G-009/G-010 (stale LATEST ON) corrupt DMA base values |
| G-084 | Loop 2: Decay Detection | HIGH | **Broken** — G-008 (drift detection no-op; called with empty feature dict); ADWIN state lost on restart (G-048) |
| G-085 | Loop 3: Kelly EWMA | MEDIUM | **Partially broken** — G-028 (trade outcomes silently lost); G-052 (shrinkage row linkage undocumented); G-051 (wrong timestamps contaminate EWMA window) |
| G-086 | Loop 4: beta_b Learning | CRITICAL | **Broken** — G-001 (CB correlation always ±1.0) and G-013 (cross-model contamination) make beta_b estimates meaningless |
| G-087 | Loop 5: Intraday CB State | MEDIUM | **Partially broken** — G-033 (non-atomic D16/D23 updates during concurrent position close) |
| G-088 | Loop 6: SOD Compounding | HIGH | **At risk** — G-024 (wrong timezone means SOD reset may fire at wrong time); G-022 (reconciliation never fixes D08 balance); G-017 (session name mismatch may prevent session trigger) |

---

### Section 9: GUI / Security Gaps

| Gap ID | Severity | Area | File:Line | Gap Description |
|--------|----------|------|-----------|-----------------|
| G-002 | CRITICAL | Auth | api.py (all) | Zero authentication on any REST or WebSocket endpoint |
| G-003 | CRITICAL | RCE | api.py `/system/git-pull` | Unauthenticated shell execution endpoint triggers container rebuild |
| G-020 | HIGH | Container | captain-command/Dockerfile | Docker socket in container — full host escape vector |
| G-021 | HIGH | SQL | b7_notifications.py:433-436 | SQL injection via role list f-string interpolation |
| G-055 | MEDIUM | Auth | api.py (WebSocket) | `user_id` self-declared in query param — client can impersonate any user |
| G-056 | MEDIUM | Info | api.py + b6_reports.py | Internal exception details leaked via `str(exc)` in API responses |
| G-089 | MEDIUM | Container | All Dockerfiles | No `USER` directive — all containers run as root |
| G-059 | MEDIUM | Secrets | telegram_bot.py:600 | Bot token appears in URL strings in memory and HTTP access logs |
| G-064 | LOW | Auth | b6_reports.py (RPT-11) | Financial export endpoint (RPT-11) has no authorization check |

---

## Part 4 — Recommended Implementation Order

Dependency-sorted, critical-first. Items in the same Priority tier can be parallelized.

| Priority | Gap IDs | Description | Blocked By | Complexity |
|----------|---------|-------------|------------|------------|
| **P1 — Fix before any live session** | | | | |
| 1 | G-004 | Fix Telegram table names (`p3_d00_asset_registry` → `p3_d00_asset_universe`, `p3_d03_trade_outcomes` → `p3_d03_trade_outcome_log`) | None | S |
| 2 | G-005 | Fix replay engine CB table name (`p3_d25_circuit_breaker` → `p3_d25_circuit_breaker_params`) | None | S |
| 3 | G-017 | Fix session name mismatch: unify `LON`/`LONDON` in constants.py + session_registry.json; add `NY_PRE` SESSION_IDS entry | None | S |
| 4 | G-001 | Fix CB serial correlation calculation — use sliding window array, not single-element pairs | None | M |
| 5 | G-013 | Fix CB params SQL to filter by `model_m` | G-001 | S |
| 6 | G-027 | Implement data moderator checks (stale-data and bad-timestamp detection) | None | M |
| **P2 — Fix before trusting learning loops** | | | | |
| 7 | G-009 | Add `LATEST ON` to AIM lifecycle state query | None | S |
| 8 | G-010 | Add `LATEST ON` to DMA weight query | None | S |
| 9 | G-070 | Audit all QuestDB queries for `ORDER BY DESC LIMIT 1` → replace with `LATEST ON` | G-009, G-010 | M |
| 10 | G-008 | Wire aim_features to drift detection orchestrator call | None | M |
| 11 | G-011 | Add Level 2 cooldown flag (reset on manual or probability-drop) | None | S |
| 12 | G-012 | Add `return` after Level 2 block or convert to `elif` | G-011 | S |
| 13 | G-028 | Add Redis publish retry with exponential backoff for trade outcome messages | None | M |
| 14 | G-083 | (G-006) Add threading.Lock around open_positions and shadow_positions | None | M |
| **P3 — Security hardening (before any exposure beyond localhost)** | | | | |
| 15 | G-002 | Implement token-based authentication middleware for all API endpoints | None | L |
| 16 | G-003 | Remove or gate the `/system/git-pull` endpoint behind auth + separate mechanism | G-002 | M |
| 17 | G-021 | Parameterize role list query in `_get_users_by_roles()` | None | S |
| 18 | G-055 | Validate `user_id` in WebSocket connections against session token | G-002 | M |
| 19 | G-020 | Remove Docker socket mount; replace git-pull with safer update mechanism | G-003 | M |
| 20 | G-089 | Add `USER` directive (non-root) to all Dockerfiles | None | S |
| 21 | G-056 | Replace `str(exc)` in API error responses with generic messages | None | S |
| **P4 — Fix before multi-session trading** | | | | |
| 22 | G-024 | Replace `datetime.now()` with `datetime.now(ZoneInfo("America/New_York"))` across all offline blocks | None | M |
| 23 | G-051 | Same timezone fix across B3–B9 blocks (20 sites) | G-024 | M |
| 24 | G-029 | Same timezone fix for B1 data ingestion (3 sites) | None | S |
| 25 | G-036 | Fix session open time function to return correct open time for LON and APAC assets | None | S |
| 26 | G-065 | Resolve ZN/ZB session mapping conflict (NY_PRE vs NY) | G-017 | S |
| 27 | G-007 | Fix `_get_contract_multiplier()` — load per-asset multipliers from D00 or constants | None | S |
| **P5 — Fix AIM gaps** | | | | |
| 28 | G-075 | Create `p3_spread_history` table in init_questdb.py; populate seed data | None | M |
| 29 | G-073 | Implement COT data feed or stub with documented placeholder values | None | L |
| 30 | G-074 | Extend AIM-01/02 features to all applicable assets or document ES-only limitation | None | M |
| 31 | G-076 | Fix AIM-13 modifier write — change JSON dict `{"asset_id": val}` to plain float | None | S |
| 32 | G-077 | Fix AIM-08 CORR_STRESS — compute rolling z-score of correlation, not raw correlation | None | M |
| **P6 — Reliability and performance** | | | | |
| 33 | G-022 | Fix reconciliation to insert a correction row into D08 | None | M |
| 34 | G-019 | Load payout MDD threshold from D17 instead of hardcoding 0.03 | None | S |
| 35 | G-018 | Add `timeout=` to all `requests.post()` calls; add 429 retry logic | None | M |
| 36 | G-023 | Convert B1 REST fetches to parallel async calls | G-018 | L |
| 37 | G-047 | Add `river` to captain-offline requirements.txt | None | S |
| 38 | G-048 | Persist ADWIN and autoencoder state to QuestDB on each update | G-047 | M |
| 39 | G-054 | Fix replay session registry — evict completed sessions from `_active_sessions` | None | S |
| 40 | G-015 | Add threading.Lock to GUI data server module globals | None | M |
| 41 | G-016 | Add threading.Lock or use asyncio primitives for WebSocket connection set | G-015 | M |
| **P7 — Code quality / DRY** | | | | |
| 42 | G-025 | Refactor b3_pseudotrader.py — extract 6 responsibilities into separate modules | None | XL |
| 43 | G-035 | Extract `_parse_json()`, `_get_ewma_for_regime()`, `_load_system_param()`, `_resolve_fee()` to shared module | None | M |
| 44 | G-014 | Remove global SEED=42 in B6/B7; use `random.seed(time.time())` or per-run entropy | None | S |
| 45 | G-026 | Replace `"primary_user"` hardcode with `user_id` from config/env | None | S |

---

## Appendix A — Block Name Discrepancies

The following block files do not match the spec block naming convention (B1–B9/B10 prefix):

| Spec Block | Expected Filename | Actual Filename | Impact |
|------------|-------------------|-----------------|--------|
| Online B8 (OR Tracker) | `b8_or_tracker.py` | `or_tracker.py` | No functional gap; cosmetic only |
| Offline B8 (Kelly/EWMA) | `b8_kelly_ewma_update.py` | `b8_kelly_update.py` | No functional gap; naming only |
| Offline B9 (Decay Detection) | `b9_decay_detection.py` | `b9_diagnostic.py` | **Functional gap** — B9 in code is a diagnostic tool, not the decay detection block |
| Command B10 (Reconciliation) | `b10_reconciliation.py` | `b8_reconciliation.py` | Command block numbering differs from spec |

---

## Appendix B — Observability Checklist (ln-627)

| Check | Status | Evidence |
|-------|--------|---------|
| Structured logging | PARTIAL | `logging.getLogger()` throughout; not structlog; no JSON structured output |
| Health endpoints | PRESENT | `GET /api/health` in captain-command api.py:98 |
| Metrics collection | ABSENT | No Prometheus, StatsD, or CloudWatch instrumentation |
| Request tracing / correlation IDs | ABSENT | No correlation IDs in logs; no OpenTelemetry |
| Log levels | PRESENT | INFO/WARNING/ERROR/DEBUG used throughout |

---

## Appendix C — Lifecycle Checklist (ln-629)

| Check | Status | Evidence |
|-------|--------|---------|
| Bootstrap initialization order | PRESENT | All three main.py files: config → DB → blocks → start |
| Graceful shutdown (SIGTERM) | PARTIAL | SIGTERM handler registered in all 3 main.py; offline orch does not join Redis listener thread (G-044) |
| Resource cleanup on exit | PARTIAL | Shutdown handler exists; QuestDB/Redis connections not explicitly closed (online LCA-03) |
| Signal handling (SIGINT) | PRESENT | Both SIGTERM and SIGINT handled |
| Liveness/readiness probes | PARTIAL | `/api/health` exists in Command only; Online and Offline have no probe endpoint |

---

## Appendix D — Code Principles Checklist (ln-623)

| Principle | Status | Worst Violation | Gap ID |
|-----------|--------|-----------------|--------|
| DRY | POOR | `_parse_json()` copied 6×; 4 utility functions each duplicated 3–6× | G-035 |
| KISS | POOR | b3_pseudotrader.py — 1,432-line god module | G-025 |
| YAGNI | MEDIUM | Dead HMM function; dead QuantConnect shims in all blocks | G-078 |
| Error handling | MEDIUM | Redis publish failure silent; exceptions leak to API | G-028, G-056 |
| Centralized error handling | MEDIUM | No centralized error handler in online or offline processes | — |
| DI / centralized init | GOOD | Blocks instantiated centrally in orchestrators | — |
