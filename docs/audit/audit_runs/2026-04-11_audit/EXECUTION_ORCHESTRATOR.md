# Execution Orchestrator — Gap Analysis Fix Plan

**Created:** 2026-04-11
**Source:** GAP_ANALYSIS.md (202 gaps, 12 CRITICAL after DEC-11/DEC-12)
**Constraint:** One block at a time per the CLAUDE.md rules; read spec before implementing
**Decisions:** DEC-04 REVOKED (pseudotrader now mandatory); DEC-11 (defer TVTP); DEC-12 (defer RBAC)

---

## How to Use This Document

Each session below contains a **Passover Prompt** — a self-contained block you paste into a fresh Claude Code context. The prompt tells Claude:
1. What files to read first (spec + code)
2. What the goal is and what to change
3. How to verify the work
4. How to mark completion (update this doc + GAP_ANALYSIS.md + commit)

**Workflow per session:**
1. Open a fresh Claude Code context in `~/captain-system`
2. Copy the passover prompt block for the session
3. Paste it as your first message
4. Claude executes the session
5. Verify the commit landed, then move to the next session

**Important:** Sessions within the same phase are sequential (1.1 → 1.2 → 1.3). Phases with no dependency can run in parallel — see the dependency graph at the bottom.

---

## Phase Summary

| Phase | Title | Scope | Sessions | CRITICALs Resolved | Status |
|-------|-------|-------|----------|---------------------|--------|
| 0 | Quick Wins | Kelly L4 formula + GUI WebSocket sanitize | 1 | 2 | COMPLETE |
| 1 | Pseudotrader Wiring [USER PRIORITY] | Wire B3 into orchestrator, implement replay | 3 | 2 | COMPLETE |
| 2 | Fill Monitoring + Data Integrity [USER PRIORITY] | Slippage monitor, data feed checks, incidents | 2 | 3 | COMPLETE |
| 3 | Crash Recovery + Shared Infra | Journal branching, Redis recovery, QuestDB pool | 2 | 1 | COMPLETE |
| 4 | Remaining CRITICALs | Sensitivity fix, RPT-12, version rollback | 2 | 3 | COMPLETE |
| 5 | Offline HIGH Fixes | B1-B9 HIGH gaps (20 findings) | 3 | 3 | COMPLETE |
| 6 | Online HIGH Fixes | B1-B7 HIGH gaps (14 findings) | 2 | 0 | PENDING |
| 7 | Command HIGH Fixes | Notifications, compliance, api.py (15 findings) | 2 | 0 | PENDING |
| 8 | Cross-Cutting Sweeps | datetime, primary_user, heartbeat, LATEST ON | 2 | 0 | PENDING |
| 9 | MEDIUM/LOW Polish | Remaining 93 MEDIUM + 40 LOW | Ongoing | 0 | PENDING |
| **TOTAL** | | | **~19 sessions** | **11** + 1 overlap | |

**Note:** 12th CRITICAL (G-XCT-015) overlaps with G-ONL-028 resolved in Phase 0.

---

## Session Passover Prompts

---

### Session 0.1 — Kelly L4 Formula Fix + GUI WebSocket Sanitization

````
## Execution Session 0.1 — Quick Wins: Kelly L4 + GUI Sanitization

You are executing Session 0.1 of the Captain System gap analysis fix plan.

### Context
Captain System is a 3-process Docker trading pipeline. A 6-session gap analysis audit
found 202 gaps (12 CRITICAL). This session fixes the 2 easiest CRITICALs.

### Before You Start — Read These Files
1. Spec: `mcp__obsidian__get_note("System 1/Direct Information/33 - Kelly Criterion and Bet-Sizing")` — find PG-24 L4 (robust fallback formula)
2. Spec: `mcp__obsidian__get_note("System 1/Direct Information/20 - P3 Command - Signal Routing and Execution")` — find PG-26 (signal sanitization / PROHIBITED_FIELDS)
3. Code: `captain-online/captain_online/blocks/b4_kelly_sizing.py` — lines 130-145 (current L4 formula)
4. Code: `captain-command/captain_command/blocks/b1_core_routing.py` — lines 75-90 (gui_push_fn path)
5. Audit: `docs/audit/audit_runs/2026-04-11_audit/GAP_ANALYSIS.md` — search for G-ONL-017 and G-ONL-028

### Task 1: Fix G-ONL-017 — Kelly L4 Robust Formula (CRITICAL)
**Problem:** Kelly sizing L4 "robust fallback" uses the wrong formula. When distributional
uncertainty is high, the system should use `f_robust = mu / (mu^2 + var)` if mu > 0, else 0.
The current code delegates to a distributional-robust path in b1_features.py (lines 468-481)
that does not match the spec formula.

**Fix:**
- In `b4_kelly_sizing.py`, find the L4 robust fallback branch
- Replace the existing formula with: `f_robust = mu / (mu**2 + var) if mu > 0 else 0`
- Remove or bypass the delegation to b1_features.py distributional-robust path
- Ensure L1-L3 and L5-L7 are NOT changed (they are correct)

### Task 2: Fix G-ONL-028 / G-XCT-015 — GUI WebSocket Sanitization (CRITICAL)
**Problem:** The signal object published to the GUI WebSocket contains proprietary fields
(aim_breakdown, regime_probs, kelly_params, etc.) that are visible in browser DevTools.
The spec defines PROHIBITED_FIELDS that must be stripped before GUI transmission.

**Fix:**
- In `b1_core_routing.py`, before the `gui_push_fn()` call, add a sanitization step
- Strip prohibited fields: aim_breakdown, regime_probs, kelly_params, model_weights,
  feature_vector, raw_scores (verify the full list against the spec PG-26)
- Create a `sanitise_for_gui(signal)` function that returns a copy with only display-safe fields
- The Redis channel signal (captain:signals) should remain UNCHANGED — only the GUI path is sanitized

### Verification
1. Run: `PYTHONPATH=./:./captain-online:./captain-offline:./captain-command python3 -B -m pytest tests/ --ignore=tests/test_integration_e2e.py --ignore=tests/test_pipeline_e2e.py --ignore=tests/test_pseudotrader_account.py --ignore=tests/test_offline_feedback.py --ignore=tests/test_stress.py --ignore=tests/test_account_lifecycle.py -v`
2. Verify Kelly L4 formula matches spec
3. Verify GUI push no longer includes prohibited fields

### When Done
1. In `docs/audit/audit_runs/2026-04-11_audit/GAP_ANALYSIS.md`:
   - Change G-ONL-017 status from `[GAP]` to `[RESOLVED]`
   - Change G-ONL-028 status from `[GAP]` to `[RESOLVED]`
   - Change G-XCT-015 status from `[GAP]` to `[RESOLVED]`
2. In `docs/audit/audit_runs/2026-04-11_audit/EXECUTION_ORCHESTRATOR.md`:
   - Change Phase 0 status from PENDING to COMPLETE
   - Change Session 0.1 CRITICALs 1 and 2 in the tracker from PENDING to RESOLVED
3. Commit: `fix(online+command): Kelly L4 robust formula + GUI WebSocket sanitization — resolves G-ONL-017, G-ONL-028, G-XCT-015`
````

**CRITICALs resolved:** G-ONL-017, G-ONL-028/G-XCT-015 (2 unique)

---

### Session 1.1 — Pseudotrader Orchestrator Integration

````
## Execution Session 1.1 — Pseudotrader Orchestrator Integration [USER PRIORITY]

You are executing Session 1.1 of the Captain System gap analysis fix plan.
This is the highest-priority fix — the pseudotrader is the safety gate for parameter
self-modification. Without it, the system updates its own parameters with no validation.

### Context
Captain System's Offline process (strategic brain) updates trading parameters (AIM weights,
Kelly fractions, EWMA stats) based on trade outcomes. The pseudotrader is supposed to
validate proposed parameter changes by replaying recent trades with the new params and
comparing performance. Currently, B3 pseudotrader exists as code but is NEVER CALLED
by the orchestrator — it's completely unwired. This was DEC-04 (deferred post-live) which
has been REVOKED. It must be wired in now.

### Before You Start — Read These Files
1. Spec: `mcp__obsidian__get_note("System 1/Direct Information/28 - Pseudotrader")` — full pseudotrader system design
2. Spec: `mcp__obsidian__get_note("System 1/Direct Information/32 - Offline Pseudocode")` — find PG-09/09B/09C (pseudotrader pseudocode)
3. Code: `captain-offline/captain_offline/blocks/orchestrator.py` — the ENTIRE file (understand all event handlers)
4. Code: `captain-offline/captain_offline/blocks/b3_pseudotrader.py` — the ENTIRE file (understand current API)
5. Code: `captain-offline/captain_offline/blocks/b1_dma_update.py` — DMA update that writes D02 (one of the paths needing the gate)
6. Code: `captain-offline/captain_offline/blocks/b8_kelly_update.py` — Kelly update that writes D12 (another path)
7. Audit: `docs/audit/audit_runs/2026-04-11_audit/GAP_ANALYSIS.md` — search for G-OFF-015

### Task: Fix G-OFF-015 — Wire Pseudotrader Into Orchestrator (CRITICAL)
**Problem:** `b3_pseudotrader.py` has `run_pseudotrader()` and `run_cb_pseudotrader()` functions
but the orchestrator NEVER imports or calls them. Parameter updates (D02, D05, D12) are
written directly with no validation.

**Fix:**
1. Import `run_pseudotrader` from `b3_pseudotrader` in the orchestrator
2. Identify the 3 event paths where parameters are updated:
   (a) Post-DMA update (D02 aim_meta_weights)
   (b) Post-Kelly update (D12 kelly_params)
   (c) Injection comparison (B4 — may already be partially wired)
3. For each path, add a pre-commit gate:
   - Capture the PROPOSED new parameter values
   - Call `run_pseudotrader(current_params, proposed_params, ...)`
   - If result is REJECT: discard proposed update, log rejection reason, publish NOTIFY
   - If result is ACCEPT: proceed with the write
4. Add a fast-path threshold: skip pseudotrader when `abs(proposed - current) < epsilon`
   for all parameters (trivial changes don't need validation)
5. Add error handling: if pseudotrader crashes, do NOT write the update (fail-safe, not fail-open)

### Verification
1. Run unit tests (see test command in CLAUDE.md)
2. Verify orchestrator imports and calls pseudotrader
3. Verify all 3 parameter-update paths are gated

### When Done
1. In GAP_ANALYSIS.md: Change G-OFF-015 from `[GAP]` to `[RESOLVED]`
2. In EXECUTION_ORCHESTRATOR.md: Mark Session 1.1 as COMPLETE in Phase Summary
3. In EXECUTION_ORCHESTRATOR.md: Mark CRITICAL #3 (G-OFF-015) as RESOLVED in tracker
4. Commit: `fix(offline): wire pseudotrader into orchestrator as pre-commit gate — resolves G-OFF-015`
````

**CRITICALs resolved:** G-OFF-015 (1)

---

### Session 1.2 — Signal Replay Integration [COMPLETE]

````
## Execution Session 1.2 — Pseudotrader Signal Replay Integration [USER PRIORITY]

You are executing Session 1.2 of the Captain System gap analysis fix plan.
**Prerequisite:** Session 1.1 must be complete (pseudotrader wired into orchestrator).

### Context
The pseudotrader validates parameter changes by replaying recent trades. Currently it
accepts pre-computed P&L lists instead of actually replaying the signal pipeline. The
spec requires it to use `SignalReplayEngine` to replay B1-B6 with proposed params and
compare outcomes. It also needs to read from P3-D03 (trade_outcome_log in QuestDB)
instead of pre-computed JSON files.

### Before You Start — Read These Files
1. Spec: `mcp__obsidian__get_note("System 1/Direct Information/28 - Pseudotrader")` — sections 1-2 (replay flow)
2. Spec: `mcp__obsidian__get_note("System 1/Direct Information/32 - Offline Pseudocode")` — PG-09 section 1-2
3. Code: `captain-offline/captain_offline/blocks/b3_pseudotrader.py` — lines 441-512 (current pre-computed path)
4. Code: `shared/replay_engine.py` — SignalReplayEngine class (this is what pseudotrader should use)
5. Code: `shared/bar_cache.py` — bar data caching for replay
6. Audit: `docs/audit/audit_runs/2026-04-11_audit/GAP_ANALYSIS.md` — search for G-OFF-016 and G-OFF-024

### Task 1: Fix G-OFF-016 — Replace Pre-computed P&L With Replay (CRITICAL)
**Problem:** `b3_pseudotrader.py` lines 441-512 accept pre-computed P&L lists. The spec
requires actual pipeline replay using `SignalReplayEngine`.

**Fix:**
- Implement `captain_online_replay(day, using=params)` wrapper function that:
  (a) Loads historical day's bar data from bar_cache
  (b) Replays B1-B6 (data ingestion → regime → AIM → Kelly → quality gate → signal output)
     with the given params substituted at the appropriate stages
  (c) Returns the signal + theoretical trade outcome
- Make this the PRIMARY path in `run_pseudotrader()`
- Keep the pre-computed P&L path as a labeled FAST FALLBACK (not the default)

### Task 2: Fix G-OFF-024 — Use D03 Trade Outcome Log (MEDIUM)
**Problem:** Pseudotrader never queries P3-D03 (trade_outcome_log in QuestDB). It uses
pre-computed data or JSON files.

**Fix:**
- Wire D03 as the data source for historical trade outcomes
- Query pattern: `SELECT * FROM trade_outcome_log WHERE user_id = $1 AND asset = $2 ORDER BY timestamp DESC LIMIT $3`
- Use these real outcomes for comparison when validating proposed parameter changes

### Verification
1. Run unit tests
2. Verify `captain_online_replay()` exists and is called by `run_pseudotrader()`
3. Verify D03 query is wired in

### When Done
1. In GAP_ANALYSIS.md: Change G-OFF-016 from `[GAP]` to `[RESOLVED]`, G-OFF-024 from `[GAP]` to `[RESOLVED]`
2. In EXECUTION_ORCHESTRATOR.md: Mark Session 1.2 as COMPLETE
3. In EXECUTION_ORCHESTRATOR.md: Mark CRITICAL #4 (G-OFF-016) as RESOLVED in tracker
4. Commit: `fix(offline): pseudotrader signal replay via SignalReplayEngine + D03 data source — resolves G-OFF-016, G-OFF-024`
````

**CRITICALs resolved:** G-OFF-016 (1)

---

### Session 1.3 — Account-Aware Replay + Depth Fixes [COMPLETE]

````
## Execution Session 1.3 — Pseudotrader Account-Aware Replay + Depth Fixes

You are executing Session 1.3 of the Captain System gap analysis fix plan.
**Prerequisite:** Sessions 1.1 and 1.2 must be complete.

### Context
The pseudotrader now has pipeline replay (Session 1.2) and is wired into the orchestrator
(Session 1.1). This session adds account-awareness (different account types have different
constraints) and fixes depth issues (bankruptcy checks, DSR computation, CB pseudotrader).

### Before You Start — Read These Files
1. Spec: `mcp__obsidian__get_note("System 1/Direct Information/28 - Pseudotrader")` — sections 4-5 (account constraints, bankruptcy), section 7-8 (SHA256 ticks, LEGACY/IDEAL — deferred to Phase 5)
2. Spec: `mcp__obsidian__get_note("System 1/Direct Information/32 - Offline Pseudocode")` — PG-09B (CB pseudotrader: 11-step per-day replay loop)
3. Code: `captain-offline/captain_offline/blocks/b3_pseudotrader.py` — lines 169-438 (main pseudotrader) and lines 619-755 (CB pseudotrader)
4. Audit: `docs/audit/audit_runs/2026-04-11_audit/GAP_ANALYSIS.md` — search for G-OFF-019 through G-OFF-023

### Task 1: Fix G-OFF-021 — CB Pseudotrader Account Constraints (HIGH)
**Problem:** `run_cb_pseudotrader()` (lines 619-755) ignores DLL/MDD/scaling/hours account
constraints. The spec (Doc 28 PG-09B) defines an 11-step per-day replay loop.

**Fix:**
- Add `account_config` input parameter to `run_cb_pseudotrader()`
- Implement the 11-step per-day loop: SOD reset, DLL check, MDD check, hours enforcement,
  size constraint, consistency check, capital unlock (read exact steps from PG-09B)
- Each step that fails should mark the day as constrained and continue to next day

### Task 2: Fix G-OFF-019 — Per-Account-Type Iteration (HIGH)
**Problem:** Pseudotrader runs with a single account_config. Spec requires iterating all
active accounts from D08 (tsm_state), replaying each with its own constraints.

**Fix:**
- Load all active accounts from D08: `SELECT * FROM tsm_state WHERE status = 'ACTIVE'`
- For each account, run replay with that account's specific constraints
- Aggregate results across accounts for the ACCEPT/REJECT decision

### Task 3: Fix G-OFF-020 — Bankruptcy Check (HIGH)
**Problem:** No bankruptcy check. If running_balance goes to 0 or below during replay,
replay continues with nonsensical results.

**Fix:**
- Add `if running_balance <= 0: break` with an account failure event logged
- Live accounts with mdd_limit=None must still be protected

### Task 4: Fix G-OFF-022 — DSR n_trials (MEDIUM)
**Problem:** `b3_pseudotrader.py:475` hardcodes n_trials=1 in the Deflated Sharpe Ratio
computation. This defeats the multiple-testing correction purpose.

**Fix:** Pass actual number of candidates tested as n_trials.

### Task 5: Fix G-OFF-023 — CB Pseudotrader DSR (MEDIUM)
**Problem:** CB pseudotrader computes PBO but hardcodes dsr=0.0 instead of computing it.

**Fix:** Compute actual DSR using the same method as the main pseudotrader.

### Verification
1. Run unit tests
2. Verify account iteration loads from D08
3. Verify bankruptcy check exists
4. Verify DSR is computed (not hardcoded)

### When Done
1. In GAP_ANALYSIS.md: Change G-OFF-019, G-OFF-020, G-OFF-021, G-OFF-022, G-OFF-023 from `[GAP]` to `[RESOLVED]`
2. In EXECUTION_ORCHESTRATOR.md: Mark Session 1.3 and Phase 1 as COMPLETE
3. Commit: `fix(offline): account-aware pseudotrader replay + bankruptcy + DSR — resolves G-OFF-019 to G-OFF-023`

**Note:** G-OFF-017 (SHA256 tick stream) and G-OFF-018 (LEGACY/IDEAL modes) are deferred to Phase 5 — they are HIGH, not CRITICAL.
````

**CRITICALs resolved (Phase 1 total):** G-OFF-015, G-OFF-016 (2)

---

### Session 2.1 — Fill Slippage Monitor

````
## Execution Session 2.1 — Fill Slippage Monitoring [USER PRIORITY]

You are executing Session 2.1 of the Captain System gap analysis fix plan.
**No prerequisites** — can run in parallel with Phase 1 or Phase 3.

### Context
Captain System's Online process monitors live positions but has NO fill quality tracking.
The spec (PG-29) requires 5 slippage metrics computed at session end. The capacity
evaluation block (B9) exists but only has a capacity planning model — it's missing the
fill monitoring side entirely.

### Before You Start — Read These Files
1. Spec: `mcp__obsidian__get_note("System 1/Direct Information/33 - Kelly Criterion and Bet-Sizing")` — find PG-29 (capacity evaluation / fill quality metrics)
2. Code: `captain-online/captain_online/blocks/b9_capacity_evaluation.py` — the ENTIRE file
3. Code: `captain-online/captain_online/blocks/b7_position_monitor.py` — understand how fills are recorded
4. Code: `captain-online/captain_online/blocks/b6_signal_output.py` — understand signal price data
5. Code: `shared/constants.py` — find `now_et()` or timezone utilities
6. Audit: `docs/audit/audit_runs/2026-04-11_audit/GAP_ANALYSIS.md` — search for G-ONL-042, G-ONL-043, G-ONL-044

### Task 1: Fix G-ONL-042 — Implement Fill Quality Metrics (CRITICAL)
**Problem:** No fill slippage monitoring exists. Slippage is invisible until P&L erodes.

**Fix:**
Add `compute_fill_quality(user_id, session_id)` to `b9_capacity_evaluation.py`:
- `fill_quality = mean(abs(fill.price - expected.price))` — average fill deviation
- `slippage_bps = fill_quality / mean(expected_prices) * 10000` — slippage in basis points
- `avg_fill_time` — average time from signal to fill
- `fill_rate = fills / signals` — what fraction of signals got filled
- `volume_participation = our_volume / market_volume` — market impact footprint

Data sources:
- Fills: B7 position_monitor records in D03 (trade_outcome_log) have fill data
- Signal prices: B6 output cached in orchestrator context
- Market volume: B1 data ingestion bars

Keep the existing `compute_capacity_model()` function — it serves a different purpose.
Both should be called at session end.

### Task 2: Fix G-ONL-043 — Slippage Alert (HIGH)
**Problem:** No notification when slippage exceeds threshold.

**Fix:**
- After computing metrics, if `slippage_bps > slippage_threshold` (read threshold from D17 system params or default 50bps), publish NOTIFY with priority="MEDIUM" to CH_ALERTS

### Task 3: Fix G-ONL-044 — Code Quality in B9 (MEDIUM)
**Problem:** B9 uses naive `datetime.now()`, `LIKE %s` queries, and missing `LATEST ON`.

**Fix:**
- Replace `datetime.now()` with `now_et()` from shared constants
- Fix `LIKE %s` query to proper parameterized WHERE clause
- Add `LATEST ON` to D17 system_params query

### Verification
1. Run unit tests
2. Verify `compute_fill_quality()` exists and returns all 5 metrics
3. Verify alert fires on high slippage
4. Verify no `datetime.now()` remains in the file

### When Done
1. In GAP_ANALYSIS.md: Change G-ONL-042, G-ONL-043, G-ONL-044 from `[GAP]` to `[RESOLVED]`
2. In EXECUTION_ORCHESTRATOR.md: Mark Session 2.1 as COMPLETE, CRITICAL #5 as RESOLVED
3. Commit: `fix(online): fill slippage monitoring with 5 spec metrics + alert — resolves G-ONL-042, G-ONL-043, G-ONL-044`
````

**CRITICALs resolved:** G-ONL-042 (1)

---

### Session 2.2 — Data Feed Monitoring + Balance Incident

````
## Execution Session 2.2 — Data Feed Monitoring + Balance Reconciliation Incident

You are executing Session 2.2 of the Captain System gap analysis fix plan.
**Prerequisite:** Session 2.1 should be complete (same block area).

### Context
Captain Command has data validation (B10) and reconciliation (B8) blocks that are mostly
implemented but missing incident creation. When data goes stale or balances mismatch,
the system should create formal incidents — not just return dicts or show GUI notifications.

### Before You Start — Read These Files
1. Spec: `mcp__obsidian__get_note("System 1/Direct Information/34 - P3 Command - Monitoring and Compliance")` — find PG-41 (data validation) and PG-39 (reconciliation)
2. Code: `captain-command/captain_command/blocks/b10_data_validation.py` — the ENTIRE file
3. Code: `captain-command/captain_command/blocks/b8_reconciliation.py` — focus on lines 100-115 (balance mismatch handling)
4. Code: `captain-command/captain_command/blocks/b9_incident_response.py` — understand `create_incident()` API
5. Audit: `docs/audit/audit_runs/2026-04-11_audit/GAP_ANALYSIS.md` — search for G-CMD-003, G-CMD-004, G-CMD-016, G-CMD-017, G-CMD-043

### Task 1: Fix G-CMD-003 — Data Feed Freshness Monitoring (CRITICAL)
**Problem:** No monitoring for stale data feeds. If market data stops flowing, the system
continues generating signals from stale data.

**Fix:**
In `b10_data_validation.py`, add `monitor_data_freshness()`:
- Periodically check last data timestamp per asset
- If `now - last_data > max_staleness`, call `create_incident("DATA_STALENESS", "P3_MEDIUM", ...)`
- Import `create_incident` from b9_incident_response

### Task 2: Fix G-CMD-016/017 — Completeness + Format Validation (HIGH)
**Problem:** Data validation exists but doesn't create incidents on failure.

**Fix:**
- Add `validate_completeness(data)`: check required fields exist, call `create_incident()` on failure
- Add `validate_format(data)`: schema validation, call `create_incident()` on failure

### Task 3: Fix G-CMD-043 — Wire B9 Incident Response (HIGH)
**Problem:** B10 returns dicts instead of creating incidents.

**Fix:** Replace dict returns with `create_incident()` calls. Import B9.

### Task 4: Fix G-CMD-004 — Balance Mismatch Incident (CRITICAL)
**Problem:** `b8_reconciliation.py:109-111` sends GUI notification on balance mismatch
but doesn't create a formal incident with audit trail.

**Fix:**
- Add `create_incident("RECONCILIATION", "P2_HIGH", "FINANCE", f"Balance mismatch for {ac}...")`
- Import `create_incident` from b9_incident_response
- Keep GUI notification as secondary alert (don't remove it)

### Verification
1. Run unit tests
2. Verify `monitor_data_freshness()` exists and calls `create_incident()`
3. Verify `b8_reconciliation.py` creates incident on mismatch

### When Done
1. In GAP_ANALYSIS.md: Change G-CMD-003, G-CMD-004, G-CMD-016, G-CMD-017, G-CMD-043 from `[GAP]` to `[RESOLVED]`
2. In EXECUTION_ORCHESTRATOR.md: Mark Session 2.2 and Phase 2 as COMPLETE
3. Mark CRITICALs #6 (G-CMD-003) and #7 (G-CMD-004) as RESOLVED in tracker
4. Commit: `fix(command): data feed monitoring + balance incident creation — resolves G-CMD-003, G-CMD-004, G-CMD-016, G-CMD-017, G-CMD-043`
````

**CRITICALs resolved (Phase 2 total):** G-ONL-042, G-CMD-003, G-CMD-004 (3)

---

### Session 3.1 — Crash Recovery Branching

````
## Execution Session 3.1 — Crash Recovery Branching

You are executing Session 3.1 of the Captain System gap analysis fix plan.
**No prerequisites** — can run in parallel with Phases 1 and 2.

### Context
Captain System has a SQLite WAL crash recovery journal (`shared/journal.py`) that records
checkpoints during execution. On restart, each process reads the last checkpoint — but then
ignores it and does a full fresh start. The journal is effectively write-only. This means
every crash causes a full restart cycle instead of resuming from the last known state.

### Before You Start — Read These Files
1. Code: `shared/journal.py` — understand the journal API (write_checkpoint, get_last_checkpoint, etc.)
2. Code: `captain-offline/captain_offline/main.py` — find the crash recovery section (lines ~125-135)
3. Code: `captain-online/captain_online/main.py` — find the crash recovery section (lines ~105-115)
4. Code: `captain-command/captain_command/main.py` — find the crash recovery section (lines ~300-310)
5. Audit: `docs/audit/audit_runs/2026-04-11_audit/GAP_ANALYSIS.md` — search for G-XCT-012 and G-SHR-018

### Task: Fix G-XCT-012 — Implement Crash Recovery Branching (CRITICAL)
**Problem:** All 3 main.py files read the last journal checkpoint on startup but don't branch
on it. They always do a full fresh start regardless of the checkpoint state.

**Fix in `captain-offline/main.py`:**
- After reading `last = journal.get_last_checkpoint()`, branch on `last["checkpoint"]` and `last["next_action"]`
- Key checkpoints:
  - `WEEKLY_START` → resume weekly scheduled tasks (skip re-init)
  - `TRADE_OUTCOME` → resume learning pipeline from the trade that was being processed
  - `None` / missing → normal fresh start (existing behavior)

**Fix in `captain-online/main.py`:**
- Branch on checkpoint:
  - `STREAMS_STARTED` → skip re-auth and stream setup, resume monitoring
  - `SESSION_ACTIVE` → resume signal pipeline mid-session
  - `SESSION_COMPLETE` → wait for next session (skip current session processing)
  - `None` → normal fresh start

**Fix in `captain-command/main.py`:**
- Branch on checkpoint:
  - `ORCHESTRATOR_STARTED` → skip init phase, resume orchestrator loop
  - `RECONCILIATION` → resume SOD reset and reconciliation
  - `None` → normal fresh start

**Important:** `shared/journal.py` itself needs no changes (G-SHR-018 is resolved by
fixing the consumers). The fix is entirely in the 3 main.py files.

### Verification
1. Run unit tests
2. Verify each main.py has branching logic after get_last_checkpoint()
3. Verify the "None" case preserves existing fresh-start behavior (no regression)

### When Done
1. In GAP_ANALYSIS.md: Change G-XCT-012 from `[GAP]` to `[RESOLVED]`, G-SHR-018 from `[GAP]` to `[RESOLVED]`
2. In EXECUTION_ORCHESTRATOR.md: Mark Session 3.1 as COMPLETE, CRITICAL #8 as RESOLVED
3. Commit: `fix(all): crash recovery checkpoint branching in all 3 processes — resolves G-XCT-012, G-SHR-018`
````

**CRITICALs resolved:** G-XCT-012 (1)

---

### Session 3.2 — Shared Module Reliability

````
## Execution Session 3.2 — Shared Module Reliability

You are executing Session 3.2 of the Captain System gap analysis fix plan.
**No strict prerequisite** — but best run after Session 3.1 (same infrastructure area).

### Context
The shared/ directory contains modules used by all 3 processes. Several have reliability
gaps: Redis has no pending message recovery, QuestDB uses per-call connections with no
pooling, vault has no thread safety, account lifecycle misses a total balance check, and
journal has no cleanup or thread safety for its init flag.

### Before You Start — Read These Files
1. Code: `shared/redis_client.py` — understand current connection and pub/sub pattern
2. Code: `shared/questdb_client.py` — understand current connection pattern
3. Code: `shared/vault.py` — understand store_api_key() flow
4. Code: `shared/account_lifecycle.py` — find end_of_day check
5. Code: `shared/journal.py` — find _initialized flag usage
6. Audit: `docs/audit/audit_runs/2026-04-11_audit/GAP_ANALYSIS.md` — search for G-SHR-002 through G-SHR-020

### Task 1: Fix G-SHR-002/003 — Redis Pending Message Recovery (HIGH)
**Problem:** Redis Streams consumer groups don't recover pending messages on restart.
Messages acknowledged by the stream but not processed by the consumer are lost.

**Fix:**
- Add `recover_pending(stream, group, consumer)` using XPENDING + XCLAIM
- Call on startup for each consumer group
- On startup: read with ID "0" first (pending messages), then switch to ">" (new messages)

### Task 2: Fix G-SHR-004 — QuestDB Connection Pooling (HIGH)
**Problem:** Every QuestDB query opens a new psycopg2 connection then closes it. Under
load this causes connection churn and occasional failures.

**Fix:**
- Replace per-call `psycopg2.connect()` with `psycopg2.pool.SimpleConnectionPool(minconn=1, maxconn=5)`
- Add `connect_timeout=10` to connection parameters
- Add retry with exponential backoff (3 attempts, starting at 0.5s)

### Task 3: Fix G-SHR-015 — Vault Thread Safety (HIGH)
**Problem:** `store_api_key()` does load→modify→save without any locking. Concurrent
calls can lose data.

**Fix:**
- Add `threading.Lock` around the load→modify→save sequence in `store_api_key()`
- Consider `fcntl.flock` for cross-process safety if multiple containers access the same vault file

### Task 4: Fix G-SHR-012 — Account Lifecycle Balance Check (HIGH)
**Problem:** LIVE stage total balance check missing. If balance hits 0, system keeps trading.

**Fix:**
- Add total balance check: `if balance <= 0: trigger failure event`
- Add to end_of_day alongside daily DD check

### Task 5: Fix G-SHR-019/020 — Journal Cleanup + Thread Safety (MEDIUM)
**Problem:** Journal entries accumulate forever. The `_initialized` flag has no thread safety.

**Fix:**
- Add journal cleanup: retain last 1000 entries per component, prune on startup
- Add `threading.Lock` around `_initialized` flag check-and-set

### Verification
1. Run unit tests
2. Verify Redis `recover_pending()` exists
3. Verify QuestDB uses connection pool
4. Verify vault has threading lock

### When Done
1. In GAP_ANALYSIS.md: Change G-SHR-002, G-SHR-003, G-SHR-004, G-SHR-012, G-SHR-015, G-SHR-019, G-SHR-020 from `[GAP]` to `[RESOLVED]`
2. In EXECUTION_ORCHESTRATOR.md: Mark Session 3.2 and Phase 3 as COMPLETE
3. Commit: `fix(shared): Redis recovery, QuestDB pooling, vault threading, journal cleanup — resolves G-SHR-002 to G-SHR-020`
````

**CRITICALs resolved (Phase 3 total):** G-XCT-012 (1)

---

### Session 4.1 — Sensitivity Fix + RPT-12 ✅ COMPLETE

````
## Execution Session 4.1 — Sensitivity Per-Parameter Perturbation + RPT-12 Alpha Decomposition

You are executing Session 4.1 of the Captain System gap analysis fix plan.
**Prerequisite:** Phase 0 must be complete.

### Context
Two CRITICAL gaps remain in the analytical tools:
1. Sensitivity analysis perturbs ALL parameters simultaneously instead of one-at-a-time,
   so you can't isolate which parameter causes fragility.
2. RPT-12 "Alpha Decomposition" report is completely missing — there's no way to attribute
   returns to individual strategy components.

### Before You Start — Read These Files
1. Spec: `mcp__obsidian__get_note("System 1/Direct Information/31 - Offline Pseudocode Part 2")` — find sensitivity analysis spec
2. Spec: `mcp__obsidian__get_note("System 1/Direct Information/34 - P3 Command - Monitoring and Compliance")` — find RPT-12 spec
3. Code: `captain-offline/captain_offline/blocks/b5_sensitivity.py` — lines 59-62 (PBO) and lines 169-177 (perturbation loop)
4. Code: `captain-command/captain_command/blocks/b6_reports.py` — REPORT_TYPES dict and generator functions
5. Audit: `docs/audit/audit_runs/2026-04-11_audit/GAP_ANALYSIS.md` — search for G-OFF-029, G-OFF-030, G-CMD-002

### Task 1: Fix G-OFF-029 — Per-Parameter Perturbation (CRITICAL)
**Problem:** `b5_sensitivity.py:169-177` applies all perturbations at once. This means you
can't tell which parameter is fragile — all move together.

**Fix:**
Restructure the perturbation loop:
```python
for param in base_params:
    for delta in deltas:
        perturbed = copy(base_params)
        perturbed[param] *= (1 + delta)
        result = evaluate(perturbed)
        grid.append((param, delta, result))
```
This produces N×len(deltas) grid points instead of just len(deltas).

### Task 2: Fix G-OFF-030 — PBO on Perturbation Grid (MEDIUM)
**Problem:** `b5_sensitivity.py:59-62` computes PBO on base_returns instead of the
perturbation grid results.

**Fix:** Compute PBO on the perturbation grid results from Task 1.

### Task 3: Fix G-CMD-002 — RPT-12 Alpha Decomposition (CRITICAL)
**Problem:** RPT-12 is missing entirely from `b6_reports.py`. The system cannot attribute
returns to individual strategy components.

**Fix:**
- Add "RPT-12" to REPORT_TYPES dict
- Implement alpha decomposition generator:
  - Decompose P&L into: base strategy return, regime conditioning effect, AIM modifier effect, Kelly sizing effect
  - Data sources: D03 (trade outcomes), D02 (AIM weights), D05 (EWMA stats), D12 (Kelly params)
  - Output: per-component attribution with percentage breakdown

### Verification
1. Run unit tests
2. Verify sensitivity produces N×7 grid (not just 7 points)
3. Verify RPT-12 appears in REPORT_TYPES

### When Done
1. In GAP_ANALYSIS.md: Change G-OFF-029, G-OFF-030, G-CMD-002 from `[GAP]` to `[RESOLVED]`
2. In EXECUTION_ORCHESTRATOR.md: Mark Session 4.1 as COMPLETE
3. Mark CRITICALs #9 (G-OFF-029) and #10 (G-CMD-002) as RESOLVED in tracker
4. Commit: `fix(offline+command): per-param sensitivity grid + RPT-12 alpha decomposition — resolves G-OFF-029, G-OFF-030, G-CMD-002`
````

**CRITICALs resolved:** G-OFF-029, G-CMD-002 (2)

---

### Session 4.2 — Version Rollback

````
## Execution Session 4.2 — Version Rollback Implementation

You are executing Session 4.2 of the Captain System gap analysis fix plan.
**Prerequisite:** Phase 1 must be COMPLETE (pseudotrader is needed for rollback comparison).

### Context
The version_snapshot module records parameter snapshots but has no rollback capability.
When a parameter update causes degradation, there's no automated way to revert to a
known-good version. The rollback must use the pseudotrader (now wired from Phase 1) to
compare current vs target version before committing the revert.

### Before You Start — Read These Files
1. Spec: `mcp__obsidian__get_note("System 1/Direct Information/31 - Offline Pseudocode Part 2")` — find version management / rollback spec
2. Code: `captain-offline/captain_offline/blocks/version_snapshot.py` — the ENTIRE file (focus on lines 23 and 51-79)
3. Code: `captain-offline/captain_offline/blocks/b3_pseudotrader.py` — understand the API for comparison (from Phase 1)
4. Audit: `docs/audit/audit_runs/2026-04-11_audit/GAP_ANALYSIS.md` — search for G-OFF-046, G-OFF-047, G-OFF-048

### Task 1: Fix G-OFF-046 — Implement rollback_to_version (CRITICAL)
**Problem:** `version_snapshot.py:51-79` has no rollback capability. The function either
doesn't exist or is a stub.

**Fix:**
Implement `rollback_to_version(component_id, version_id, admin_user_id)`:
1. Load target version from D18 (version_snapshots table)
2. Load current live state using `get_current_state(component_id)` (Task 3)
3. Run pseudotrader comparison: `run_pseudotrader(current_state, target_version_state)`
4. If pseudotrader says REJECT: abort rollback, log reason, notify admin
5. If ACCEPT: snapshot current state first (for undo), then restore target version to live tables (D01/D02/D05/D12)
6. Send HIGH notification for audit trail
7. Run regression tests after restore; revert if tests fail

### Task 2: Fix G-OFF-047 — MAX_VERSIONS Enforcement (HIGH)
**Problem:** `version_snapshot.py:23` defines MAX_VERSIONS=50 but never enforces it.
Snapshots accumulate without bound.

**Fix:**
- On each new snapshot write, count existing versions for that component
- If count >= MAX_VERSIONS, prune oldest snapshots
- Add cold_storage migration for versions older than 90 days (move to archive table)

### Task 3: Fix G-OFF-048 — get_current_state Helper (HIGH)
**Problem:** `version_snapshot.py:51-79` requires callers to pass state dicts manually.
There's no helper to load the current live state.

**Fix:**
Implement `get_current_state(component_id)`:
- Load live state from the appropriate table based on component_id:
  - AIM weights → D02 (aim_meta_weights)
  - Kelly params → D12 (kelly_params)
  - EWMA stats → D05 (ewma_states)
  - AIM models → D01 (aim_model_states)
- Return as a standardized dict matching the version snapshot format

### Verification
1. Run unit tests
2. Verify `rollback_to_version()` calls pseudotrader for comparison
3. Verify MAX_VERSIONS is enforced on write
4. Verify `get_current_state()` loads from correct tables

### When Done
1. In GAP_ANALYSIS.md: Change G-OFF-046, G-OFF-047, G-OFF-048 from `[GAP]` to `[RESOLVED]`
2. In EXECUTION_ORCHESTRATOR.md: Mark Session 4.2 and Phase 4 as COMPLETE
3. Mark CRITICAL #11 (G-OFF-046) as RESOLVED in tracker — ALL CRITICALs NOW RESOLVED
4. Commit: `fix(offline): version rollback with pseudotrader comparison + MAX_VERSIONS enforcement — resolves G-OFF-046, G-OFF-047, G-OFF-048`
````

**CRITICALs resolved (Phase 4 total):** G-OFF-029, G-CMD-002, G-OFF-046 (3)

---

### Session 5.1 — Offline B1 AIM Block Fixes [COMPLETE]

````
## Execution Session 5.1 — Offline B1 AIM Block HIGH Fixes

You are executing Session 5.1 of the Captain System gap analysis fix plan.
**Prerequisite:** Phase 1 should be complete (pseudotrader changes touch B3 in same process).

### Context
5 HIGH-severity findings in the Offline B1 AIM blocks: HMM observation minimum, smoothing
alpha, drift retrain flag, injection ratio bound, and auto-expansion walk-forward split.

### Before You Start — Read These Files
1. Spec: `mcp__obsidian__get_note("System 1/Direct Information/22 - AIM-16 HMM Regime Detection")` — sections 6 and 7
2. Spec: `mcp__obsidian__get_note("System 1/Direct Information/32 - Offline Pseudocode")` — PG-04 (drift), PG-03 (injection)
3. Code: `captain-offline/captain_offline/blocks/b1_aim16_hmm.py` — lines 40-43 (obs count, smoothing)
4. Code: `captain-offline/captain_offline/blocks/b1_drift_detection.py` — lines 269-319 (drift response)
5. Code: `captain-offline/captain_offline/blocks/b4_injection.py` — lines 142-149 (PARALLEL_TRACK)
6. Code: `captain-offline/captain_offline/blocks/b6_auto_expansion.py` — lines 234-263 (GA fitness)
7. Audit: search GAP_ANALYSIS.md for G-OFF-002, G-OFF-003, G-OFF-004, G-OFF-025, G-OFF-032

### Tasks
| # | Finding | Fix |
|---|---------|-----|
| 1 | G-OFF-002 | Enforce 240 minimum observation count before HMM training (HIGH) |
| 2 | G-OFF-003 | Include SMOOTHING_ALPHA in HMM output state for online inference (HIGH) |
| 3 | G-OFF-004 | Set retrain flag in P3-D01 on drift detection, not just weight reduction (HIGH) |
| 4 | G-OFF-025 | Add PARALLEL_TRACK upper bound: ratio must be ≤ 1.2 (HIGH) |
| 5 | G-OFF-032 | Implement walk-forward train/validate split in GA fitness function (HIGH) |

### Verification
Run unit tests. Verify each fix matches the spec reference listed.

### When Done
1. In GAP_ANALYSIS.md: Change all 5 findings from `[GAP]` to `[RESOLVED]`
2. In EXECUTION_ORCHESTRATOR.md: Mark Session 5.1 as COMPLETE
3. Commit: `fix(offline): B1 AIM block HIGH fixes — HMM obs min, smoothing, drift retrain, injection bound, walk-forward — resolves G-OFF-002 to G-OFF-032`
````

---

### Session 5.2 — Offline B2 Decay Detection Fixes [COMPLETE]

````
## Execution Session 5.2 — Offline B2 Decay Detection HIGH Fixes

You are executing Session 5.2 of the Captain System gap analysis fix plan.

### Context
4 HIGH-severity findings in the Offline B2 decay detection blocks: BOCPD state persistence,
CUSUM bootstrap calibration at init, detector state restoration on startup, and D02 bootstrap.

### Before You Start — Read These Files
1. Spec: `mcp__obsidian__get_note("System 1/Direct Information/32 - Offline Pseudocode")` — PG-05 (BOCPD), PG-06 (CUSUM), PG-07 (calibration)
2. Code: `captain-offline/captain_offline/blocks/b2_bocpd.py` — lines 142-156, 177-184
3. Code: `captain-offline/captain_offline/blocks/b2_cusum.py` — constructor and orchestrator wiring
4. Code: `captain-offline/captain_offline/blocks/orchestrator.py` — line 51, lines 154-166
5. Code: `scripts/bootstrap_production.py` — lines 80-211 (D02 init)
6. Audit: search GAP_ANALYSIS.md for G-OFF-009, G-OFF-010, G-OFF-011, G-OFF-049

### Tasks
| # | Finding | Fix |
|---|---------|-----|
| 1 | G-OFF-009 | Persist run_length_posterior and NIG priors to P3-D04 after each BOCPD update (HIGH) |
| 2 | G-OFF-010 | Add bootstrap calibration at init time alongside quarterly recalibration (HIGH) |
| 3 | G-OFF-011 | Call from_dict() deserializers on startup to restore detector state from D04 (HIGH) |
| 4 | G-OFF-049 | Initialize D02 (aim_meta_weights) in bootstrap_production.py (HIGH) |

### Verification
Run unit tests. Verify BOCPD state persists to D04 and restores on startup.

### When Done
1. In GAP_ANALYSIS.md: Change all 4 findings from `[GAP]` to `[RESOLVED]`
2. In EXECUTION_ORCHESTRATOR.md: Mark Session 5.2 as COMPLETE
3. Commit: `fix(offline): B2 decay detection — BOCPD persistence, CUSUM init calibration, state restore — resolves G-OFF-009 to G-OFF-049`
````

---

### Session 5.3 — Offline B7-B9 Kelly/CB/Diagnostic Fixes ✅ COMPLETE

````
## Execution Session 5.3 — Offline B7-B9 Kelly/CB/Diagnostic + Remaining B3 HIGH Fixes

You are executing Session 5.3 of the Captain System gap analysis fix plan.

### Context
6 HIGH-severity findings: Kelly estimation variance, CB L_star computation, CB cold_start
field, per-candidate OOS for PBO, pseudotrader SHA256 tick stream, and LEGACY/IDEAL modes.

### Before You Start — Read These Files
1. Spec: `mcp__obsidian__get_note("System 1/Direct Information/32 - Offline Pseudocode")` — PG-12 (Kelly update), PG-13 (CB params)
2. Spec: `mcp__obsidian__get_note("System 1/Direct Information/28 - Pseudotrader")` — sections 7-8 (SHA256, LEGACY/IDEAL)
3. Code: `captain-offline/captain_offline/blocks/b8_kelly_update.py` — lines 108-116
4. Code: `captain-offline/captain_offline/blocks/b8_cb_params.py` — lines 134-207
5. Code: `captain-offline/captain_offline/blocks/b6_auto_expansion.py` — lines 269-275
6. Code: `captain-offline/captain_offline/blocks/b3_pseudotrader.py` — full file (SHA256 + modes)
7. Audit: search GAP_ANALYSIS.md for G-OFF-039, G-OFF-040, G-OFF-041, G-OFF-033, G-OFF-017, G-OFF-018

### Tasks
| # | Finding | Fix |
|---|---------|-----|
| 1 | G-OFF-039 | Replace 1/sqrt(N) proxy with compute_estimation_variance(P3-D05[u]) (HIGH) |
| 2 | G-OFF-040 | Compute and store L_star = -r_bar/beta_b in D25 circuit breaker params (HIGH) |
| 3 | G-OFF-041 | Add cold_start field to D25 writes; implement two-tier CB threshold (HIGH) |
| 4 | G-OFF-033 | Per-candidate OOS for PBO computation in auto-expansion (HIGH) |
| 5 | G-OFF-017 | SHA256 deterministic tick stream generator for synthetic regression tests (HIGH) |
| 6 | G-OFF-018 | LEGACY vs IDEAL mode parameter with mode-labelled results (HIGH) |

### Verification
Run unit tests. Focus on Kelly update and CB params tests.

### When Done
1. In GAP_ANALYSIS.md: Change all 6 findings from `[GAP]` to `[RESOLVED]`
2. In EXECUTION_ORCHESTRATOR.md: Mark Session 5.3 and Phase 5 as COMPLETE
3. Commit: `fix(offline): Kelly variance, CB L_star/cold_start, PBO OOS, pseudotrader SHA256+modes — resolves G-OFF-017 to G-OFF-041`
````

---

### Session 6.1 — Online Sizing Pipeline Fixes

````
## Execution Session 6.1 — Online Sizing Pipeline HIGH Fixes

You are executing Session 6.1 of the Captain System gap analysis fix plan.
**Prerequisite:** Phase 0 must be complete.

### Context
7 HIGH-severity findings in the Online signal pipeline: missing data sources for features
(overnight range, options data, PCR), Kelly sizing override position, loss-per-contract
formula, quality gate metric, and AIM session budget weights.

### Before You Start — Read These Files
1. Spec: `mcp__obsidian__get_note("System 1/Direct Information/33 - Kelly Criterion and Bet-Sizing")` — sizing layers, quality gate
2. Spec: `mcp__obsidian__get_note("System 1/Direct Information/23 - AIM Scoring")` — AIM aggregation, session budget
3. Code: `captain-online/captain_online/blocks/b1_features.py` — lines 863-864, 938-972
4. Code: `captain-online/captain_online/blocks/b4_kelly_sizing.py` — lines 190-193, 252-260
5. Code: `captain-online/captain_online/blocks/b5b_quality_gate.py` — lines 49-77
6. Code: `shared/aim_compute.py` — lines 175-178
7. Audit: search GAP_ANALYSIS.md for G-ONL-004 to G-ONL-021

### Tasks
| # | Finding | Fix |
|---|---------|-----|
| 1 | G-ONL-004 | Implement _get_overnight_range data source or document unavailability (HIGH) |
| 2 | G-ONL-005 | Implement options data pipeline or mark AIM-02/03 as DATA_UNAVAILABLE (HIGH) |
| 3 | G-ONL-006 | Implement _get_trailing_pcr or deactivate AIM-02 pcr_z feature (HIGH) |
| 4 | G-ONL-018 | Move sizing override to pre-TSM position (between L6 and L7) (HIGH) |
| 5 | G-ONL-019 | Use spec formula: strategy_sl * point_value + expected_fee (HIGH) |
| 6 | G-ONL-021 | Implement dollar_per_contract = score / contracts in quality gate (HIGH) |
| 7 | G-ONL-013 | Return session_budget_weights from run_aim_aggregation() (HIGH) |

### Verification
Run unit tests. Verify sizing pipeline layer order and formula correctness.

### When Done
1. In GAP_ANALYSIS.md: Change all 7 findings from `[GAP]` to `[RESOLVED]`
2. In EXECUTION_ORCHESTRATOR.md: Mark Session 6.1 as COMPLETE
3. Commit: `fix(online): sizing pipeline — features data, Kelly override/formula, quality gate, AIM budget — resolves G-ONL-004 to G-ONL-021`
````

---

### Session 6.2 — Online Circuit Breaker + Signal Output Fixes

````
## Execution Session 6.2 — Online Circuit Breaker + Signal Output HIGH Fixes

You are executing Session 6.2 of the Captain System gap analysis fix plan.

### Context
7 HIGH-severity findings: CB dollar-budget check, rolling basket Sharpe, signal blob reduction,
anti-copy jitter, timezone-aware time-exit, shadow monitor retry, and crash recovery wiring.

### Before You Start — Read These Files
1. Spec: `mcp__obsidian__get_note("System 1/Direct Information/33 - Kelly Criterion and Bet-Sizing")` — CB layers
2. Spec: `mcp__obsidian__get_note("System 1/Direct Information/20 - P3 Command - Signal Routing and Execution")` — signal output
3. Code: `captain-online/captain_online/blocks/b5c_circuit_breaker.py` — lines 296-325, 375-437
4. Code: `captain-online/captain_online/blocks/b6_signal_output.py` — lines 94-134
5. Code: `captain-online/captain_online/blocks/b7_position_monitor.py` — line 134
6. Code: `captain-online/captain_online/blocks/b7_shadow_monitor.py` — lines 165-170
7. Code: `captain-online/captain_online/main.py` — lines 107-110
8. Audit: search GAP_ANALYSIS.md for G-ONL-024 to G-ONL-048

### Tasks
| # | Finding | Fix |
|---|---------|-----|
| 1 | G-ONL-024 | Replace trade-count ceiling with dollar-budget check in CB (HIGH) |
| 2 | G-ONL-025 | Replace analytical Sharpe with rolling_basket_sharpe(lookback=60d) (HIGH) |
| 3 | G-ONL-029 | Reduce signal blob to 6 spec fields at source (HIGH) |
| 4 | G-ONL-030 | Implement anti-copy jitter: +/-30s time, +/-1 micro size (HIGH) |
| 5 | G-ONL-032 | Fix time-exit to use timezone-aware datetime (HIGH) |
| 6 | G-ONL-036 | Add 3-attempt exponential backoff retry to shadow monitor publish (HIGH) |
| 7 | G-ONL-048 | Wire crash recovery checkpoint branching — coordinated with Phase 3 (HIGH) |

**Note:** Task 7 may already be partially done if Phase 3 Session 3.1 ran first.
Check `captain-online/main.py` for existing checkpoint branching before implementing.

### Verification
Run unit tests. Verify CB uses dollar budget, signal has 6 fields, time-exit is tz-aware.

### When Done
1. In GAP_ANALYSIS.md: Change all 7 findings from `[GAP]` to `[RESOLVED]`
2. In EXECUTION_ORCHESTRATOR.md: Mark Session 6.2 and Phase 6 as COMPLETE
3. Commit: `fix(online): CB dollar-budget, signal reduction, anti-copy jitter, tz-fix, retry — resolves G-ONL-024 to G-ONL-048`
````

---

### Session 7.1 — Command Notifications + Incidents Fixes

````
## Execution Session 7.1 — Command Notifications + Incidents HIGH Fixes

You are executing Session 7.1 of the Captain System gap analysis fix plan.
**Prerequisite:** Phase 2 should be complete (incident response wiring overlaps).

### Context
7 HIGH-severity findings in Command notification and incident systems: LOW priority routing,
email channel, QuestDB placeholder syntax, P1 incident routing, escalation timers, API
failure incidents, and reconciliation gate.

### Before You Start — Read These Files
1. Spec: `mcp__obsidian__get_note("System 1/Direct Information/34 - P3 Command - Monitoring and Compliance")` — notification routing, incident response, escalation
2. Code: `captain-command/captain_command/blocks/b7_notifications.py` — lines 241-256, 449
3. Code: `captain-command/captain_command/blocks/b9_incident_response.py` — line 41
4. Code: `captain-command/captain_command/blocks/b3_api_adapter.py` — lines 432-438
5. Code: `captain-command/captain_command/blocks/b8_reconciliation.py` — line 73
6. Audit: search GAP_ANALYSIS.md for G-CMD-008 to G-CMD-015

### Tasks
| # | Finding | Fix |
|---|---------|-----|
| 1 | G-CMD-010 | Route LOW priority to log-only, not GUI (HIGH) |
| 2 | G-CMD-011 | Implement email channel or document deferral (HIGH) |
| 3 | G-CMD-012 | Fix $1,$2 placeholder syntax to %s for QuestDB (HIGH) |
| 4 | G-CMD-014 | Route P1 incidents to ADMIN+DEV, ALL channels, quiet hours override (HIGH) |
| 5 | G-CMD-015 | Implement escalation timers: P1=5min, P2=30min, P3=4hr, P4=next day (HIGH) |
| 6 | G-CMD-008 | Replace notify_fn() with create_incident() on API failure (HIGH) |
| 7 | G-CMD-013 | Change reconciliation gate from topstep_optimisation to scaling_plan_active (HIGH) |

### Verification
Run unit tests. Verify notification routing and escalation logic.

### When Done
1. In GAP_ANALYSIS.md: Change all 7 findings from `[GAP]` to `[RESOLVED]`
2. In EXECUTION_ORCHESTRATOR.md: Mark Session 7.1 as COMPLETE
3. Commit: `fix(command): notification routing, escalation timers, incident creation, recon gate — resolves G-CMD-008 to G-CMD-015`
````

---

### Session 7.2 — Command Compliance + API Fixes

````
## Execution Session 7.2 — Command Compliance + API HIGH Fixes

You are executing Session 7.2 of the Captain System gap analysis fix plan.

### Context
8 HIGH-severity findings in Command compliance gate and API layer: compliance checks,
instrument/max-contracts validation, hardcoded primary_user in API, audit logging, JWT
refresh, and data validation incident wiring.

### Before You Start — Read These Files
1. Spec: `mcp__obsidian__get_note("System 1/Direct Information/34 - P3 Command - Monitoring and Compliance")` — compliance gate, audit logging
2. Spec: `mcp__obsidian__get_note("System 1/Direct Information/20 - P3 Command - Signal Routing and Execution")` — API requirements
3. Code: `captain-command/captain_command/blocks/b12_compliance_gate.py` — full file
4. Code: `captain-command/captain_command/api.py` — search for "primary_user" (13 locations)
5. Code: `captain-command/captain_command/blocks/b10_data_validation.py` — incident wiring
6. Audit: search GAP_ANALYSIS.md for G-CMD-005 to G-CMD-019

### Tasks
| # | Finding | Fix |
|---|---------|-----|
| 1 | G-CMD-009 | Implement compliance_check(signal) with max_contracts + instrument_permitted (HIGH) |
| 2 | G-CMD-018 | Add instrument_permitted check per signal in compliance gate (HIGH) |
| 3 | G-CMD-019 | Add max_contracts check with EXCEEDS_MAX_CONTRACTS rejection (HIGH) |
| 4 | G-CMD-005 | Replace 13 hardcoded "primary_user" in api.py with request.state.user_id from JWT (HIGH) |
| 5 | G-CMD-006 | Add AuditLog table writes (user_id, timestamp, action, old_value, new_value) (HIGH) |
| 6 | G-CMD-007 | Add /auth/refresh endpoint for JWT silent refresh (HIGH) |
| 7 | G-CMD-016 | Wire create_incident() for completeness failures in data validation (HIGH) |
| 8 | G-CMD-017 | Wire create_incident() for format/schema failures in data validation (HIGH) |

**Note:** Tasks 7-8 may overlap with Phase 2 Session 2.2. Check if already resolved.

### Verification
Run unit tests. Verify no "primary_user" hardcodes remain in api.py.

### When Done
1. In GAP_ANALYSIS.md: Change all 8 findings from `[GAP]` to `[RESOLVED]`
2. In EXECUTION_ORCHESTRATOR.md: Mark Session 7.2 and Phase 7 as COMPLETE
3. Commit: `fix(command): compliance checks, API user_id, audit log, JWT refresh — resolves G-CMD-005 to G-CMD-019`
````

---

### Session 8.1 — Timezone + Heartbeat Cross-Cutting Sweep

````
## Execution Session 8.1 — datetime.now() Sweep + Heartbeat Fix

You are executing Session 8.1 of the Captain System gap analysis fix plan.
**Best run after Phases 5-7** to avoid merge conflicts with files they modify.

### Context
Two cross-cutting issues affect all 3 processes:
1. 68+ occurrences of naive `datetime.now()` instead of `now_et()` (timezone-aware ET)
2. Offline and Online processes don't publish heartbeats to CH_STATUS — only Command does

### Before You Start — Read These Files
1. Code: `shared/constants.py` — find `now_et()` helper function
2. Run: `grep -rn "datetime.now()" captain-offline/ captain-online/ captain-command/ shared/` to get full list
3. Code: `captain-command/captain_command/main.py` — find the heartbeat pattern (this is the working reference)
4. Code: `captain-offline/captain_offline/main.py` — verify no heartbeat exists
5. Code: `captain-online/captain_online/blocks/orchestrator.py` — verify no heartbeat exists
6. Audit: search GAP_ANALYSIS.md for G-XCT-001 through G-XCT-006

### Task 1: datetime.now() Sweep (68+ occurrences)
**Priority order for replacement:**
1. HIGH-risk: B7 time-exit, B4 Kelly sizing, shadow monitor (wrong timezone = wrong trade timing)
2. MEDIUM-risk: orchestrator event timestamps, journal writes
3. LOW-risk: logging, debug, non-critical timestamps

Replace ALL `datetime.now()` with `now_et()` from shared/constants.py. If `now_et()` doesn't
exist, create it: `def now_et(): return datetime.now(ZoneInfo("America/New_York"))`

### Task 2: Offline Heartbeat
Add periodic heartbeat to CH_STATUS in captain-offline (30s interval matching Command pattern).
Publish on: idle between events, during long-running operations.

### Task 3: Online Heartbeat
Add periodic heartbeat to CH_STATUS in captain-online orchestrator.
Publish on: idle intervals between sessions, alongside stage transitions.

### Verification
1. Run: `grep -rn "datetime.now()" captain-offline/ captain-online/ captain-command/ shared/` — should return 0 hits
2. Run unit tests
3. Verify heartbeat publishing exists in all 3 processes

### When Done
1. In GAP_ANALYSIS.md: Change G-XCT-001 through G-XCT-006 from `[GAP]` to `[RESOLVED]`
2. In EXECUTION_ORCHESTRATOR.md: Mark Session 8.1 as COMPLETE
3. Commit: `fix(all): replace 68+ datetime.now() with now_et() + add heartbeats to offline/online — resolves G-XCT-001 to G-XCT-006`
````

---

### Session 8.2 — Primary User + LATEST ON Cross-Cutting Sweep

````
## Execution Session 8.2 — primary_user Sweep + LATEST ON Fix

You are executing Session 8.2 of the Captain System gap analysis fix plan.

### Context
Two cross-cutting issues:
1. 29 occurrences of hardcoded "primary_user" across the codebase — should use dynamic user_id
2. Missing QuestDB LATEST ON in circuit breaker and GUI data server queries

### Before You Start — Read These Files
1. Run: `grep -rn '"primary_user"' captain-offline/ captain-online/ captain-command/ shared/` to get full list
2. Code: `captain-online/captain_online/blocks/b5c_circuit_breaker.py` — find _seen set workaround
3. Code: `captain-command/captain_command/blocks/b2_gui_data_server.py` — find missing dedup
4. Audit: search GAP_ANALYSIS.md for G-XCT-007 through G-XCT-011

### Task 1: primary_user Sweep (29 occurrences)
Replace hardcoded "primary_user" with dynamic user_id from the appropriate source:
- In API routes: `request.state.user_id` from JWT (Phase 7 may have started this)
- In signal processing: `signal["user_id"]` from the signal payload
- In orchestrator contexts: `user_id` parameter passed from the calling function
- In bootstrap scripts ONLY: keep env-var defaults (`os.getenv("BOOTSTRAP_USER_ID", "primary_user")`)

**Important:** Do NOT remove "primary_user" from bootstrap/seed scripts — those are the
legitimate default for single-instance deployment.

### Task 2: LATEST ON Fixes
- `b5c_circuit_breaker.py`: Replace the `_seen` set workaround with proper `LATEST ON timestamp PARTITION BY user_id` in QuestDB queries
- `b2_gui_data_server.py`: Add `LATEST ON` to queries that are missing dedup

### Verification
1. Run: `grep -rn '"primary_user"' captain-offline/ captain-online/ captain-command/` — should only appear in bootstrap scripts
2. Run unit tests
3. Verify LATEST ON in CB and GUI data server queries

### When Done
1. In GAP_ANALYSIS.md: Change G-XCT-007 through G-XCT-011 from `[GAP]` to `[RESOLVED]`
2. In EXECUTION_ORCHESTRATOR.md: Mark Session 8.2 and Phase 8 as COMPLETE
3. Commit: `fix(all): replace 29 hardcoded primary_user + add LATEST ON to CB/GUI queries — resolves G-XCT-007 to G-XCT-011`
````

---

### Phase 9 — MEDIUM/LOW Polish (No Passover Prompts)

Phase 9 covers 93 MEDIUM + 40 LOW findings. These are not session-structured because:
- They have no blocking dependencies
- They can be done in any order
- They can be picked up opportunistically alongside live operation

**Grouping by effort:**

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
    ├── Phase 5 (offline HIGH) ─── COMPLETE
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
| 1 | G-ONL-017 (Kelly L4 formula) | 0 | 0.1 | RESOLVED |
| 2 | G-ONL-028 / G-XCT-015 (GUI WebSocket) | 0 | 0.1 | RESOLVED |
| 3 | G-OFF-015 (pseudotrader unwired) | 1 | 1.1 | RESOLVED |
| 4 | G-OFF-016 (no pipeline replay) | 1 | 1.2 | RESOLVED |
| 5 | G-ONL-042 (fill slippage) | 2 | 2.1 | RESOLVED |
| 6 | G-CMD-003 (data feed monitoring) | 2 | 2.2 | RESOLVED |
| 7 | G-CMD-004 (balance incident) | 2 | 2.2 | RESOLVED |
| 8 | G-XCT-012 (crash recovery) | 3 | 3.1 | RESOLVED |
| 9 | G-OFF-029 (sensitivity per-param) | 4 | 4.1 | RESOLVED |
| 10 | G-CMD-002 (RPT-12) | 4 | 4.1 | RESOLVED |
| 11 | G-OFF-046 (version rollback) | 4 | 4.2 | RESOLVED |

**Deferred (not in tracker):**
- DEC-11: G-OFF-001 (HMM TVTP) — V2
- DEC-12: G-CMD-001 (RBAC) — V2 multi-user

---

## Execution Protocol

**Before each session:**
1. Open a fresh Claude Code context in `~/captain-system`
2. Copy-paste the session's passover prompt
3. Claude reads the listed specs and code files
4. Claude implements the changes per the task list

**After each session (automated by the passover prompt):**
1. Run unit tests: `PYTHONPATH=./:./captain-online:./captain-offline:./captain-command python3 -B -m pytest tests/ --ignore=tests/test_integration_e2e.py --ignore=tests/test_pipeline_e2e.py --ignore=tests/test_pseudotrader_account.py --ignore=tests/test_offline_feedback.py --ignore=tests/test_stress.py --ignore=tests/test_account_lifecycle.py -v`
2. Update this document: mark session COMPLETE, note any scope changes
3. Update GAP_ANALYSIS.md: mark resolved findings as `[RESOLVED]`
4. Commit with message: `fix(scope): description — resolves G-XXX-NNN`
5. Update CRITICAL Resolution Tracker above

**Escalation rule:** If a fix requires changing a FROZEN file or deviating from spec, STOP and ask Nomaan.
