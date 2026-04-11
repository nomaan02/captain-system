# Execution Orchestrator — Gap Analysis Fix Plan

**Created:** 2026-04-11
**Source:** GAP_ANALYSIS.md (204 gaps, 12 CRITICAL after DEC-11/DEC-12)
**Constraint:** One block at a time per the CLAUDE.md rules; read spec before implementing
**Decisions:** DEC-04 REVOKED (pseudotrader now mandatory); DEC-11 (defer TVTP); DEC-12 (defer RBAC)

---

## Phase Summary

| Phase | Title | Scope | Sessions | CRITICALs Resolved | Status |
|-------|-------|-------|----------|---------------------|--------|
| 0 | Quick Wins | Kelly L4 formula + GUI WebSocket sanitize | 1 | 2 | PENDING |
| 1 | Pseudotrader Wiring | Wire B3 into orchestrator, implement replay | 3 | 2 | PENDING |
| 2 | Fill Monitoring + Data Integrity | Slippage monitor, data feed checks, incidents | 2 | 3 | PENDING |
| 3 | Crash Recovery + Shared Infra | Journal branching, Redis recovery, QuestDB pool | 2 | 1 | PENDING |
| 4 | Remaining CRITICALs | Sensitivity fix, RPT-12, version rollback | 2 | 3 | PENDING |
| 5 | Offline HIGH Fixes | B1-B9 HIGH gaps (20 findings) | 3 | 0 | PENDING |
| 6 | Online HIGH Fixes | B1-B7 HIGH gaps (14 findings) | 2 | 0 | PENDING |
| 7 | Command HIGH Fixes | Notifications, compliance, api.py (15 findings) | 2 | 0 | PENDING |
| 8 | Cross-Cutting Sweeps | datetime, primary_user, heartbeat, LATEST ON | 2 | 0 | PENDING |
| 9 | MEDIUM/LOW Polish | Remaining 93 MEDIUM + 40 LOW | Ongoing | 0 | PENDING |
| **TOTAL** | | | **~19 sessions** | **11** + 1 overlap | |

**Note:** 12th CRITICAL (G-XCT-015) overlaps with G-ONL-028 resolved in Phase 0.

---

## Phase 0 — Quick Wins

**Goal:** Eliminate the 2 easiest CRITICALs in a single session (<1 hour).

### Session 0.1 — Formula Fix + Sanitization

| # | Finding | File | Change |
|---|---------|------|--------|
| 1 | G-ONL-017 | `b4_kelly_sizing.py:132-141` | Replace robust formula: `f_robust = mu / (mu**2 + var) if mu > 0 else 0`. Remove delegation to `b1_features.py:468-481` distributional-robust path. |
| 2 | G-ONL-028 / G-XCT-015 | `b1_core_routing.py:80-82` | Add `signal = sanitise_for_api(signal)` before `gui_push_fn()` call. Or create `sanitise_for_gui()` with a display-safe field set. |

**Spec refs to read first:** Doc 33 PG-24 L4 (Kelly robust), Doc 20 PG-26 (signal sanitization)
**Test:** Run unit tests for Kelly sizing; verify GUI WebSocket no longer includes aim_breakdown/regime_probs.

**CRITICALs resolved:** G-ONL-017, G-ONL-028/G-XCT-015 (2 unique)

---

## Phase 1 — Pseudotrader Wiring [USER PRIORITY]

**Goal:** Wire B3 pseudotrader into the Offline orchestrator so parameter updates are validated before commit. Revokes DEC-04.

**Spec refs:** Doc 28 (pseudotrader system), Doc 32 PG-09/09B/09C (offline pseudocode)

### Session 1.1 — Orchestrator Integration

| # | Finding | File | Change |
|---|---------|------|--------|
| 1 | G-OFF-015 | `captain-offline/blocks/orchestrator.py` | Import `run_pseudotrader` from `b3_pseudotrader.py`. Add pre-commit gate: before writing D02/D05/D12 updates, call pseudotrader with current vs proposed params. If REJECT, discard proposed update and log. |
| 2 | — | `captain-offline/blocks/orchestrator.py` | Wire pseudotrader into 3 event paths: (a) post-DMA-update, (b) post-Kelly-update, (c) injection comparison (already wired via B4). |
| 3 | — | `captain-offline/blocks/orchestrator.py` | Add fast-path threshold: skip pseudotrader for updates where `abs(proposed - current) < epsilon` to avoid latency on trivial changes. |

### Session 1.2 — Signal Replay Integration

| # | Finding | File | Change |
|---|---------|------|--------|
| 1 | G-OFF-016 | `b3_pseudotrader.py:441-512` | Replace pre-computed P&L path with `SignalReplayEngine`-based replay as primary. Keep pre-computed as labeled fast fallback. |
| 2 | — | `b3_pseudotrader.py` | Implement `captain_online_replay(d, using=params)` wrapper that loads historical day `d` from D03/bar_cache, replays B1-B6 with given params, returns signal + theoretical outcome. |
| 3 | G-OFF-024 | `b3_pseudotrader.py` | Wire P3-D03 (trade_outcome_log) as data source instead of pre-computed JSON files. |

### Session 1.3 — Account-Aware Replay + Depth Fixes

| # | Finding | File | Change |
|---|---------|------|--------|
| 1 | G-OFF-021 | `b3_pseudotrader.py:619-755` | Add `account_config` input to `run_cb_pseudotrader()`. Implement the 11-step per-day replay loop from Doc 28 PG-09B: SOD reset, DLL check, MDD check, hours enforcement, size constraint, consistency check, capital unlock. |
| 2 | G-OFF-019 | `b3_pseudotrader.py:169-438` | Add per-account-type iteration: load all active accounts from D08, replay each with its own constraints. |
| 3 | G-OFF-020 | `b3_pseudotrader.py:169-438` | Add bankruptcy check: `if running_balance <= 0: break` with account failure event. |
| 4 | G-OFF-022 | `b3_pseudotrader.py:475` | Fix DSR n_trials: pass actual number of candidates tested, not hardcoded 1. |
| 5 | G-OFF-023 | `b3_pseudotrader.py:619-755` | Compute actual DSR in CB pseudotrader instead of hardcoding 0.0. |

**Deferred to Phase 5 (HIGH, not CRITICAL):**
- G-OFF-017: SHA256 deterministic tick stream (synthetic regression tests)
- G-OFF-018: LEGACY vs IDEAL mode labelling

**CRITICALs resolved:** G-OFF-015, G-OFF-016 (2)

---

## Phase 2 — Fill Monitoring + Data Integrity [USER PRIORITY]

**Goal:** Implement fill slippage monitoring (G-ONL-042), data feed monitoring (G-CMD-003), and incident creation for balance mismatches (G-CMD-004).

**Spec refs:** Doc 33 PG-29 (capacity eval), Doc 34 PG-41 (data validation), Doc 34 PG-39 (reconciliation)

### Session 2.1 — Fill Slippage Monitor

| # | Finding | File | Change |
|---|---------|------|--------|
| 1 | G-ONL-042 | `b9_capacity_evaluation.py` | Add `compute_fill_quality(user_id, session_id)` function implementing 5 spec metrics: `fill_quality = mean(abs(fill.price - expected.price))`, `slippage_bps = fill_quality / mean(expected_prices) * 10000`, `avg_fill_time`, `fill_rate = fills / signals`, `volume_participation = our_volume / market_volume`. |
| 2 | G-ONL-042 | `b9_capacity_evaluation.py` | Keep existing capacity planning model as `compute_capacity_model()` — it serves a different purpose. Both functions called at session end. |
| 3 | G-ONL-043 | `b9_capacity_evaluation.py` | Add NOTIFY with priority="MEDIUM" when `slippage_bps > slippage_threshold`. Publish to CH_ALERTS. |
| 4 | G-ONL-044 | `b9_capacity_evaluation.py` | Fix naive `datetime.now()` → `now_et()`. Fix `LIKE %s` query → proper parameterized WHERE. Add `LATEST ON` to D17 query. |

**Data sources:** Fills from B7 position_monitor (D03 trade_outcome_log has fill data). Signal prices from B6 output cached in orchestrator. Market volume from B1 data ingestion.

### Session 2.2 — Data Feed Monitoring + Balance Incident

| # | Finding | File | Change |
|---|---------|------|--------|
| 1 | G-CMD-003 | `b10_data_validation.py` | Add `monitor_data_freshness()`: periodic check of last data timestamp per asset. If `now - last_data > max_staleness`, call `create_incident("DATA_STALENESS", "P3_MEDIUM", ...)`. Import B9. |
| 2 | G-CMD-016/017 | `b10_data_validation.py` | Add `validate_completeness(data)`: check required fields exist. Add `validate_format(data)`: schema validation. Both call `create_incident()` on failure. |
| 3 | G-CMD-043 | `b10_data_validation.py` | Wire B9 incident_response import. Replace dict returns with incident creation. |
| 4 | G-CMD-004 | `b8_reconciliation.py:109-111` | Replace GUI notification with `create_incident("RECONCILIATION", "P2_HIGH", "FINANCE", f"Balance mismatch for {ac}...")`. Import B9. Keep GUI notification as secondary alert. |

**CRITICALs resolved:** G-ONL-042, G-CMD-003, G-CMD-004 (3)

---

## Phase 3 — Crash Recovery + Shared Infrastructure

**Goal:** Make crash recovery functional and fix shared module reliability gaps.

### Session 3.1 — Crash Recovery Branching

| # | Finding | File | Change |
|---|---------|------|--------|
| 1 | G-XCT-012 | `captain-offline/main.py:129-132` | Branch on `last["checkpoint"]` and `last["next_action"]`. Resume from last known state instead of fresh start. Key checkpoints: WEEKLY_START→resume weekly tasks, TRADE_OUTCOME→resume learning pipeline. |
| 2 | G-XCT-012 | `captain-online/main.py:107-110` | Branch on checkpoint. Key: STREAMS_STARTED→skip re-auth, SESSION_ACTIVE→resume signal pipeline, SESSION_COMPLETE→wait for next session. |
| 3 | G-XCT-012 | `captain-command/main.py:305-308` | Branch on checkpoint. Key: ORCHESTRATOR_STARTED→skip init, RECONCILIATION→resume SOD reset. |
| 4 | G-SHR-018 | `shared/journal.py` | No code change needed — journal infrastructure works. The fix is in the 3 main.py files above. |

### Session 3.2 — Shared Module Reliability

| # | Finding | File | Change |
|---|---------|------|--------|
| 1 | G-SHR-002/003 | `shared/redis_client.py` | Add `recover_pending(stream, group, consumer)` using XPENDING + XCLAIM. Call on startup. Add read_stream mode "0" for pending on startup, then ">" for new. |
| 2 | G-SHR-004 | `shared/questdb_client.py` | Replace per-call `psycopg2.connect()` with `psycopg2.pool.SimpleConnectionPool(minconn=1, maxconn=5)`. Add `connect_timeout=10`. Add retry with exponential backoff (3 attempts). |
| 3 | G-SHR-015 | `shared/vault.py` | Add `threading.Lock` around load→modify→save in `store_api_key()`. Or use `fcntl.flock` for cross-process safety. |
| 4 | G-SHR-012 | `shared/account_lifecycle.py` | Add LIVE stage total balance check: `if balance <= 0: trigger failure`. Add to end_of_day alongside daily DD check. |
| 5 | G-SHR-019/020 | `shared/journal.py` | Add journal cleanup (retain last 1000 entries per component). Add `threading.Lock` around `_initialized` flag. |

**CRITICALs resolved:** G-XCT-012 (1)

---

## Phase 4 — Remaining CRITICALs

**Goal:** Close out the final 3 CRITICAL gaps.

### Session 4.1 — Sensitivity Fix + RPT-12

| # | Finding | File | Change |
|---|---------|------|--------|
| 1 | G-OFF-029 | `b5_sensitivity.py:169-177` | Restructure perturbation loop: `for param in base_params: for delta in deltas: perturbed = copy(base); perturbed[param] *= (1+delta)`. Produces N×7 grid points instead of 7. |
| 2 | G-OFF-030 | `b5_sensitivity.py:59-62` | Compute PBO on perturbation grid results, not base_returns. |
| 3 | G-CMD-002 | `b6_reports.py` | Add RPT-12 "Alpha Decomposition" to REPORT_TYPES and generators dict. Implement: decompose PnL into base strategy, regime conditioning, AIM modifiers, Kelly sizing effects. Data sources: D03, D02, D05, D12. |

### Session 4.2 — Version Rollback

| # | Finding | File | Change |
|---|---------|------|--------|
| 1 | G-OFF-046 | `version_snapshot.py:51-79` | Implement `rollback_to_version(component_id, version_id, admin_user_id)`: load target from D18, run pseudotrader comparison (requires Phase 1 complete), send HIGH notification for admin approval, snapshot current before restoring, run regression tests, revert if tests fail, log to AdminDecisionLog. |
| 2 | G-OFF-047 | `version_snapshot.py:23` | Enforce MAX_VERSIONS=50: prune oldest snapshots on write. Add cold_storage migration for versions older than 90 days. |
| 3 | G-OFF-048 | `version_snapshot.py:51-79` | Add `get_current_state(component_id)` that loads live state from D01/D02/D05/D12 so callers don't need to pass state dicts. |

**Dependencies:** Session 4.2 depends on Phase 1 completion (pseudotrader must be working for rollback comparison).

**CRITICALs resolved:** G-OFF-029, G-CMD-002, G-OFF-046 (3)

---

## Phase 5 — Offline HIGH Fixes

**Goal:** Fix all 20 HIGH-severity gaps in P3-Offline.

### Session 5.1 — B1 AIM Blocks (5 findings)

| # | Finding | File | Summary |
|---|---------|------|---------|
| 1 | G-OFF-002 | b1_aim16_hmm.py:40 | Enforce 240 minimum observation count before training |
| 2 | G-OFF-003 | b1_aim16_hmm.py:43 | Include SMOOTHING_ALPHA in output state for online inference |
| 3 | G-OFF-004 | b1_drift_detection.py:269-319 | Set retrain flag in P3-D01 on drift detection |
| 4 | G-OFF-025 | b4_injection.py:142-149 | Add PARALLEL_TRACK upper bound (ratio ≤ 1.2) |
| 5 | G-OFF-032 | b6_auto_expansion.py:234-263 | Implement walk-forward train/validate split in GA fitness |

### Session 5.2 — B2 Decay Detection (4 findings)

| # | Finding | File | Summary |
|---|---------|------|---------|
| 1 | G-OFF-009 | b2_bocpd.py:142-156 | Persist run_length_posterior and NIG priors to P3-D04 |
| 2 | G-OFF-010 | b2_cusum.py + orchestrator.py | Add init-time bootstrap calibration alongside quarterly |
| 3 | G-OFF-011 | orchestrator.py:51 | Call from_dict() deserializers on startup to restore detector state |
| 4 | G-OFF-049 | bootstrap.py:80-211 | Initialize D02 (aim_meta_weights) in bootstrap |

### Session 5.3 — B7-B9 Kelly/CB/Diagnostic (6 findings)

| # | Finding | File | Summary |
|---|---------|------|---------|
| 1 | G-OFF-039 | b8_kelly_update.py:108-116 | Replace 1/√N proxy with compute_estimation_variance(P3-D05[u]) |
| 2 | G-OFF-040 | b8_cb_params.py:134-207 | Compute and store L_star = -r̄/β_b in D25 |
| 3 | G-OFF-041 | b8_cb_params.py:134-207 | Add cold_start field to D25 writes; implement two-tier threshold |
| 4 | G-OFF-033 | b6_auto_expansion.py:269-275 | Per-candidate OOS for PBO computation |
| 5 | G-OFF-017 | b3_pseudotrader.py | SHA256 deterministic tick stream generator |
| 6 | G-OFF-018 | b3_pseudotrader.py | LEGACY vs IDEAL mode parameter with labelled results |

---

## Phase 6 — Online HIGH Fixes

**Goal:** Fix all 14 HIGH-severity gaps in P3-Online.

### Session 6.1 — Sizing Pipeline (7 findings)

| # | Finding | File | Summary |
|---|---------|------|---------|
| 1 | G-ONL-004 | b1_features.py:863-864 | Implement _get_overnight_range data source (or document unavailability) |
| 2 | G-ONL-005 | b1_features.py:965-972 | Implement options data pipeline or mark AIM-02/03 as DATA_UNAVAILABLE |
| 3 | G-ONL-006 | b1_features.py:938-940 | Implement _get_trailing_pcr or deactivate AIM-02 pcr_z |
| 4 | G-ONL-018 | b4_kelly_sizing.py:252-260 | Move sizing override to pre-TSM position (between L6 and L7) |
| 5 | G-ONL-019 | b4_kelly_sizing.py:190-193 | Use spec formula `strategy_sl * point_value + expected_fee` as primary |
| 6 | G-ONL-021 | b5b_quality_gate.py:49-77 | Implement spec metric `dollar_per_contract = score / contracts` |
| 7 | G-ONL-013 | aim_compute.py:175-178 | Return session_budget_weights from run_aim_aggregation() |

### Session 6.2 — Circuit Breaker + Signal Output (7 findings)

| # | Finding | File | Summary |
|---|---------|------|---------|
| 1 | G-ONL-024 | b5c_circuit_breaker.py:296-325 | Replace trade-count ceiling with dollar-budget check |
| 2 | G-ONL-025 | b5c_circuit_breaker.py:375-437 | Replace analytical Sharpe with rolling_basket_sharpe(lookback=60d) |
| 3 | G-ONL-029 | b6_signal_output.py:94-134 | Reduce signal blob to 6 fields at source (or document internal-only channel) |
| 4 | G-ONL-030 | b6_signal_output.py | Implement anti-copy jitter: ±30s time, ±1 micro size |
| 5 | G-ONL-032 | b7_position_monitor.py:134 | Fix time-exit to use timezone-aware datetime |
| 6 | G-ONL-036 | b7_shadow_monitor.py:165-170 | Add 3-attempt exponential backoff retry to publish_to_stream |
| 7 | G-ONL-048 | main.py:107-110 | Wire crash recovery checkpoint branching (coordinated with Phase 3) |

---

## Phase 7 — Command HIGH Fixes

**Goal:** Fix all 15 HIGH-severity gaps in P3-Command.

### Session 7.1 — Notifications + Incidents (7 findings)

| # | Finding | File | Summary |
|---|---------|------|---------|
| 1 | G-CMD-010 | b7_notifications.py:241-256 | Route LOW priority to log-only, not GUI |
| 2 | G-CMD-011 | b7_notifications.py | Implement email channel (or document deferral) |
| 3 | G-CMD-012 | b7_notifications.py:449 | Fix $1,$2 → %s placeholder syntax for QuestDB |
| 4 | G-CMD-014 | b9_incident_response.py:41 | Route P1 to ADMIN+DEV, ALL channels, quiet hours override |
| 5 | G-CMD-015 | b9_incident_response.py | Implement escalation timers: P1=5min, P2=30min, P3=4hr, P4=next day |
| 6 | G-CMD-008 | b3_api_adapter.py:432-438 | Replace notify_fn() with create_incident() on API failure |
| 7 | G-CMD-013 | b8_reconciliation.py:73 | Change gate from topstep_optimisation to scaling_plan_active |

### Session 7.2 — Compliance + API (8 findings)

| # | Finding | File | Summary |
|---|---------|------|---------|
| 1 | G-CMD-009 | b3_api_adapter.py:468-471 | Implement compliance_check(signal) with max_contracts + instrument_permitted |
| 2 | G-CMD-018 | b12_compliance_gate.py | Add instrument_permitted check per signal |
| 3 | G-CMD-019 | b12_compliance_gate.py | Add max_contracts check per signal with EXCEEDS_MAX_CONTRACTS rejection |
| 4 | G-CMD-005 | api.py (13 locations) | Replace hardcoded "primary_user" with request.state.user_id from JWT |
| 5 | G-CMD-006 | api.py | Add AuditLog table writes (user_id, timestamp, action, old_value, new_value) |
| 6 | G-CMD-007 | api.py | Add /auth/refresh endpoint for JWT silent refresh |
| 7 | G-CMD-016 | b10_data_validation.py | Wire create_incident() for completeness failures |
| 8 | G-CMD-017 | b10_data_validation.py | Wire create_incident() for format/schema failures |

---

## Phase 8 — Cross-Cutting Sweeps

**Goal:** Systematic codebase-wide fixes for patterns that span all 3 processes.

### Session 8.1 — Timezone + Heartbeat

| # | Area | Scope | Change |
|---|------|-------|--------|
| 1 | datetime.now() | 68+ occurrences, 25+ files | Replace with `now_et()` from shared/constants.py. Priority: HIGH-risk items first (B7 time-exit, B4 Kelly, shadow monitor), then sweep remaining. |
| 2 | Heartbeat | captain-offline/main.py + orchestrator.py | Add periodic heartbeat to CH_STATUS (30s interval, matching Command pattern). |
| 3 | Heartbeat | captain-online/orchestrator.py | Add periodic heartbeat alongside stage transitions. Publish on idle intervals between sessions. |

### Session 8.2 — Primary User + LATEST ON

| # | Area | Scope | Change |
|---|------|-------|--------|
| 1 | primary_user | 29 occurrences across codebase | Replace hard assignments with dynamic user_id from JWT/signal context. Keep env-var defaults in bootstrap scripts only. |
| 2 | LATEST ON | b5c_circuit_breaker.py, b2_gui_data_server.py | Replace _seen set workarounds and missing dedup with proper QuestDB LATEST ON PARTITION BY clauses. |

---

## Phase 9 — MEDIUM/LOW Polish

**Goal:** Address remaining 93 MEDIUM + 40 LOW findings. These can be done in parallel with live operation.

### Grouping (by effort, not by session)

**Quick MEDIUM fixes (< 30 min each):**
- G-OFF-005, 006, 007, 012, 013, 014 — AIM lifecycle/CUSUM minor fixes
- G-ONL-001, 002, 003, 007, 012, 014, 015, 016 — Data ingestion/AIM minor
- G-CMD-020, 022, 032, 033, 037, 039, 045, 047 — Field names, caching, naming

**Medium MEDIUM fixes (1-2 hours each):**
- G-OFF-026, 027, 028, 030, 031, 034, 035 — Injection/sensitivity/expansion
- G-OFF-036, 037, 038, 042, 043, 044, 050 — TSM/CB/diagnostic
- G-ONL-020, 022, 023, 026, 027, 031, 033, 034, 037, 039, 044-047 — Various
- G-CMD-021-031, 034-036, 038-050 — Various command blocks

**LOW findings (defer indefinitely or fix opportunistically):**
- 40 findings across all programs — polish, optimization, non-essential

---

## Dependency Graph

```
Phase 0 ──────────────────────────────────────────────── (no deps, start here)
    │
    ├── Phase 1 (pseudotrader) ─────────────┐
    │                                        │
    ├── Phase 2 (fill monitor + data) ──┐    │
    │                                   │    │
    ├── Phase 3 (crash recovery)        │    │
    │                                   │    │
    │                          Phase 4 ─┴────┘ (session 4.2 needs Phase 1)
    │
    ├── Phase 5 (offline HIGH) ─── can start after Phase 1
    ├── Phase 6 (online HIGH) ─── can start after Phase 0
    ├── Phase 7 (command HIGH) ── can start after Phase 2
    │
    ├── Phase 8 (cross-cutting) ── can start anytime, ideally after 5-7
    └── Phase 9 (MEDIUM/LOW) ──── ongoing, no blocking deps
```

**Parallelization opportunities:**
- Phases 1, 2, 3 can run in parallel (different processes, no file overlap)
- Phases 5, 6, 7 can run in parallel (different processes)
- Phase 8 should run after 5-7 to avoid merge conflicts on shared files
- Phase 9 is always-available filler work

---

## CRITICAL Resolution Tracker

| # | Finding | Phase | Session | Status |
|---|---------|-------|---------|--------|
| 1 | G-ONL-017 (Kelly L4 formula) | 0 | 0.1 | PENDING |
| 2 | G-ONL-028 / G-XCT-015 (GUI WebSocket) | 0 | 0.1 | PENDING |
| 3 | G-OFF-015 (pseudotrader unwired) | 1 | 1.1 | PENDING |
| 4 | G-OFF-016 (no pipeline replay) | 1 | 1.2 | PENDING |
| 5 | G-ONL-042 (fill slippage) | 2 | 2.1 | PENDING |
| 6 | G-CMD-003 (data feed monitoring) | 2 | 2.2 | PENDING |
| 7 | G-CMD-004 (balance incident) | 2 | 2.2 | PENDING |
| 8 | G-XCT-012 (crash recovery) | 3 | 3.1 | PENDING |
| 9 | G-OFF-029 (sensitivity per-param) | 4 | 4.1 | PENDING |
| 10 | G-CMD-002 (RPT-12) | 4 | 4.1 | PENDING |
| 11 | G-OFF-046 (version rollback) | 4 | 4.2 | PENDING |

**Deferred (not in tracker):**
- DEC-11: G-OFF-001 (HMM TVTP) — V2
- DEC-12: G-CMD-001 (RBAC) — V2 multi-user

---

## Execution Protocol

**Before each session:**
1. Read the relevant spec via `mcp__obsidian__get_note` (start with `_claude/SPEC_INDEX.md`)
2. Read the current code files listed in the session table
3. Confirm the change plan against spec requirements
4. Implement one block at a time (CLAUDE.md rule)

**After each session:**
1. Run unit tests: `PYTHONPATH=./:./captain-online:./captain-offline:./captain-command python3 -B -m pytest tests/ --ignore=tests/test_integration_e2e.py --ignore=tests/test_pipeline_e2e.py --ignore=tests/test_pseudotrader_account.py --ignore=tests/test_offline_feedback.py --ignore=tests/test_stress.py --ignore=tests/test_account_lifecycle.py -v`
2. Update this document: mark session COMPLETE, note any scope changes
3. Update GAP_ANALYSIS.md: mark resolved findings as `[RESOLVED]`
4. Commit with message: `fix(scope): description — resolves G-XXX-NNN`
5. Update CRITICAL Resolution Tracker above

**Escalation rule:** If a fix requires changing a FROZEN file or deviating from spec, STOP and ask Nomaan.
