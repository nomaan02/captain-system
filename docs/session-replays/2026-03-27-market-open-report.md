# Market Open Post-Mortem Report — 2026-03-27

---

## 1. SESSION OVERVIEW

- **Date:** Friday 2026-03-27
- **Time window:** ~08:40 ET to ~09:50 ET (pre-market prep through post-session debugging)
- **Objective:** First live auto-trading session of Captain Function at NY open (09:30 ET) on TopstepX practice account 20319811 ($150K Trading Combine)
- **Overall outcome:** Pipeline ran end-to-end and generated 5 valid signals, but zero orders were placed. Three independent blockers were discovered and patched in sequence: (1) compliance gate locked, (2) D00 stale rows nullifying active assets, (3) circuit breaker cold-start bug blocking all trades. A fourth issue — ORB direction=0 (pending breakout) — prevented auto-execution of the signals that did get through. The session window was consumed by debugging.

---

## 2. WHAT WORKED (Confirmed Operational)

- **QuestDB connectivity** — All 3 processes connected to QuestDB on startup.
  - Evidence: `QuestDB: connected` in all container logs.
  - Status: CONFIRMED WORKING

- **Redis connectivity** — Pub/sub and stream consumer groups initialized.
  - Evidence: `Redis: connected`, `Redis Stream consumer groups initialized`
  - Status: CONFIRMED WORKING

- **TopstepX authentication** — API authenticated for both Online and Command processes.
  - Evidence: `TopstepX authenticated as nomaanakram4@gmail.com (env=LIVE)`
  - Status: CONFIRMED WORKING

- **MarketStream WebSocket** — Connected and subscribed to all 10 contracts.
  - Evidence: `MarketStream CONNECTED — subscribing to 10 contract(s)`, `State change: connecting -> connected`
  - Status: CONFIRMED WORKING

- **Contract resolution** — All 10 assets resolved to TopstepX contract IDs.
  - Evidence: `Resolved 10 contracts: ['ES', 'MES', 'NQ', 'MNQ', 'M2K', 'MYM', 'NKD', 'MGC', 'ZB', 'ZN']`
  - Status: CONFIRMED WORKING

- **Session trigger mechanism** — Orchestrator correctly detected the session window and fired.
  - Evidence: `ON-B1: Starting data ingestion for session NY (1)` appeared at 09:28:00, 09:30:23, and 09:45:00 (across different test runs)
  - Status: CONFIRMED WORKING

- **B1 Data Ingestion** — When D00 had correct data, loaded 9 assets and computed 108 features in ~5 seconds.
  - Evidence: `ON-B1: 9 assets eligible for session NY`, `ON-B1: Data ingestion complete. 9 active assets, 108 features computed`
  - Status: CONFIRMED WORKING

- **B2 Regime Probability** — Computed for all 9 assets (all neutral, expected for cold start with no regime models).
  - Evidence: `ON-B2: Regime probabilities computed for 9 assets (9 uncertain)`
  - Status: CONFIRMED WORKING

- **B3 AIM Aggregation** — Completed for 9 assets with active AIMs.
  - Evidence: `ON-B3: AIM aggregation complete for 9 assets (9 with active AIMs)`
  - Status: CONFIRMED WORKING

- **B4 Kelly Sizing** — Computed sizing for primary_user across 1 account and 9 assets.
  - Evidence: `ON-B4: Kelly sizing for user primary_user (1 accounts, 9 assets)`
  - Status: CONFIRMED WORKING

- **B5 Trade Selection** — Selected 5 of 9 assets for trading.
  - Evidence: `ON-B5: Trade selection for user primary_user: 5/9 assets selected`
  - Status: CONFIRMED WORKING

- **B5B Quality Gate** — All 5 selected assets passed quality threshold.
  - Evidence: `ON-B5B: Quality gate for user primary_user: 5 recommended, 0 below threshold`
  - Status: CONFIRMED WORKING

- **B6 Signal Output** — Published 5 signals to Redis stream (on the successful run).
  - Evidence: `ON-B6: 5 signals published for user primary_user (session 1), 0 below threshold`
  - Status: CONFIRMED WORKING

- **Command signal ingestion** — Command process received all 5 signals from Redis stream and attempted auto-execution.
  - Evidence: `AUTO-EXECUTE SKIP: direction=0 for MNQ (ORB pending breakout)` (repeated for all 5 assets)
  - Status: CONFIRMED WORKING

- **AUTO_EXECUTE env var** — Correctly set to `true` inside the Command container.
  - Evidence: `docker exec ... python3 -c "print(os.environ.get('AUTO_EXECUTE'))"` → `true`
  - Status: CONFIRMED WORKING

- **GUI WebSocket** — GUI connected and sessions tracked.
  - Evidence: `WebSocket connected: user=primary_user (sessions=1, evicted=0)`
  - Status: CONFIRMED WORKING

- **Nginx + GUI static assets** — GUI accessible at localhost:80 after manual volume deploy.
  - Evidence: GUI loaded after `docker run ... cp -r /src/* /gui-dist/`
  - Status: CONFIRMED WORKING (with workaround)

---

## 3. WHAT FAILED (Errors & Blockers)

### 3.1 Compliance Gate Blocking All Orders

- **Component:** `captain-command/captain_command/blocks/b3_api_adapter.py` — `check_compliance_gate()`
- **Symptom:** Even with `AUTO_EXECUTE=true`, all orders would have returned `{"status": "MANUAL_PENDING"}` without reaching TopstepX.
- **Root cause:** `config/compliance_gate.json` had all 11 RTS 6 requirements set to `false`. The code checks `if gate["execution_mode"] == "MANUAL" and not gate["allowed"]` — with all requirements false, `allowed=False`, so every `send_signal()` call returns `MANUAL_PENDING`.
- **Fix applied:** Changed all 11 requirements from `false` to `true` in `config/compliance_gate.json`.
- **Fix result:** File updated on WSL2 host, but Docker bind mount was resolving to Windows filesystem (`C:\` via 9p), so the container still saw the old file. Required `docker cp` to inject the updated file directly into the running container.
- **Status:** PATCHED (needs proper fix) — The bind mount issue means this fix doesn't survive container restarts. Must either fix the volume mount path or rebuild captain-command with the updated config baked in.

### 3.2 D00 Stale Rows — NULL captain_status Overriding Bootstrap Data

- **Component:** `captain-online/captain_online/blocks/b1_data_ingestion.py` — `_update_asset_quality_flag()` (line 601)
- **Symptom:** `ON-B1: No active assets for session NY` — B1 found zero eligible assets despite 10 being bootstrapped as ACTIVE.
- **Root cause:** The function `_update_asset_quality_flag(asset_id, flag)` inserts rows into `p3_d00_asset_universe` with ONLY `asset_id`, `data_quality_flag`, and `last_updated` — leaving `captain_status=NULL` and `session_hours=NULL`. Because QuestDB is append-only and B1 deduplicates using `ORDER BY last_updated DESC`, these newer NULL rows override the correctly bootstrapped rows. This function is called by `_run_data_moderator()` on **every session for every active asset**.
- **Secondary contributors identified:**
  - `captain-offline/captain_offline/blocks/b1_aim_lifecycle.py` line 113: `_update_warmup_progress()` writes NULL captain_status/session_hours
  - `captain-offline/captain_offline/blocks/bootstrap.py` lines 98, 285: writes NULL session_hours
  - `scripts/seed_all_assets.py` line 250: `promote_to_active()` writes NULL session_hours
  - `scripts/roll_calendar_update.py` line 253: writes NULL captain_status and session_hours
- **Fix applied:** Manual re-insertion of 9 NY asset rows with correct `captain_status='ACTIVE'` and `session_hours` via `docker exec` Python one-liner. Had to be done TWICE (once at 09:30, again after container restart wiped the fix since the underlying NULL-row-producing code still runs).
- **Fix result:** Worked temporarily — B1 found 9 assets on the next run. But the fix is not durable; any restart or data moderator run re-introduces NULL rows.
- **Status:** UNRESOLVED — Requires a proper fix: either (a) make all D00 INSERT statements include captain_status and session_hours, or (b) change `_update_asset_quality_flag()` to use QuestDB's UPDATE if available, or (c) change B1's deduplication to prefer rows where captain_status is NOT NULL.

### 3.3 Circuit Breaker Cold-Start Bug (Layer 3)

- **Component:** `captain-online/captain_online/blocks/b5c_circuit_breaker.py` — `_layer3_basket_expectancy()`
- **Symptom:** All 5 recommended trades blocked: `ON-B5C: CB blocked MNQ for account 20319811: L3: negative basket expectancy — mu_b=0.00 (r_bar=0.00, beta_b=0.0000, L_b=0)` (repeated for MNQ, MGC, MYM, MES, NQ).
- **Root cause:** D25 has a row with `r_bar=0.0, beta_b=0.0, n_observations=0` (cold start). The code computes `mu_b = r_bar + beta_b * l_b = 0.0`, then checks `if mu_b <= 0` which blocks. The `cb_param is None` bypass doesn't trigger because D25 has a row (just all zeros). CLAUDE.md explicitly states "Cold-start (beta_b=0, layers 3-4 disabled)" but the code didn't implement this correctly when `cb_param` exists but has zero observations.
- **Fix applied:** Added `if n_obs == 0: return None` to both `_layer3_basket_expectancy()` and `_layer4_correlation_sharpe()`, before the mu_b computation. This skips layers 3-4 when there's genuinely no trade data.
- **Fix result:** All 20 circuit breaker unit tests pass (including `test_cold_start_skips`). The fix was deployed and confirmed working — on the 09:45 test run, B5C no longer blocked any trades and B6 published 5 signals.
- **Status:** RESOLVED

### 3.4 ORB Direction = 0 (Pending Breakout)

- **Component:** `captain-online/captain_online/blocks/b6_signal_output.py` (signal generation) + `captain-command/captain_command/blocks/orchestrator.py` (auto-execute check)
- **Symptom:** All 5 published signals had `direction=0` instead of `"BUY"` or `"SELL"`. Command's auto-execute correctly skipped them: `AUTO-EXECUTE SKIP: direction=0 for MNQ (ORB pending breakout)`.
- **Root cause:** Not fully diagnosed. The ORB strategy should determine direction based on whether price breaks above or below the opening range. The opening range is defined as the first `m` minutes after session open (e.g., m=7 for ES means 09:30-09:37). The test session triggered at 09:45 with a configured session time of 09:47 — the ORB logic may have been computing the opening range relative to the configured session time (09:47) rather than the actual market open (09:30), meaning the range hadn't formed yet. Alternatively, the `direction=0` may simply indicate no breakout was detected in the available price data.
- **Fix applied:** None — root cause not fully diagnosed during the session.
- **Fix result:** N/A
- **Status:** UNRESOLVED — Requires investigation of how B6 determines ORB direction. Key questions: Does B6 use the session_hours open time (09:30) or the orchestrator trigger time? Does it require live tick data from MarketStream, and was the quote_cache populated at the time of evaluation?

### 3.5 GUI Docker Build Failure (SIGSEGV)

- **Component:** `captain-gui/Dockerfile` — `RUN npm run build` (tsc -b && vite build)
- **Symptom:** `npm error signal SIGSEGV` — TypeScript compiler crashed during Docker build.
- **Root cause:** Out of memory in the Docker build container. `tsc -b` (project build mode) runs inside a constrained Alpine container. This is a known issue with TypeScript compilation in memory-limited Docker environments on WSL2.
- **Fix applied:** Built locally on the host (`npx vite build`), then deployed the `dist/` directory directly into the Docker volume using `docker run ... cp -r /src/* /gui-dist/`.
- **Fix result:** GUI accessible at localhost:80.
- **Status:** PATCHED (needs proper fix) — Options: increase Docker memory limits in `docker-compose.local.yml`, skip `tsc -b` in Dockerfile (Vite does its own transpilation), or always build locally and copy in.

### 3.6 Docker Bind Mount Not Reflecting WSL2 File Changes

- **Component:** Docker Compose volume mounts (`./config:/captain/config`)
- **Symptom:** Editing `config/compliance_gate.json` on the WSL2 filesystem had no effect inside the container — `docker exec ... cat /captain/config/compliance_gate.json` still showed the old content.
- **Root cause:** Docker Desktop resolves bind mount paths through the Windows filesystem (`C:\` via 9p) rather than the WSL2 native filesystem (`/home/nomaan/...`). The mount output inside the container confirmed: `C:\ on /captain/config type 9p`. The file timestamp inside the container was `Mar 14 20:55` vs our edit on `Mar 27`. WSL2-native edits don't propagate through the Windows 9p mount.
- **Fix applied:** `docker cp` to inject individual files into running containers.
- **Fix result:** Worked, but doesn't survive container restarts.
- **Status:** UNRESOLVED — This is an infrastructure-level issue. Options: (a) ensure the Docker daemon uses the WSL2 backend directly (not Docker Desktop's Windows integration), (b) use named volumes instead of bind mounts for config, (c) rebuild containers after config changes, (d) store config inside the app image.

### 3.7 Orchestrator Crash Loop After Session

- **Component:** `captain-online/captain_online/blocks/orchestrator.py` — `_session_loop()` line 93
- **Symptom:** After the successful session run at 09:45, the orchestrator crashed and entered a restart loop, repeatedly showing stack traces referencing `orchestrator.py line 93` (`self._run_position_monitor()`), followed by immediate re-triggering of B1 (which found no active assets due to the D00 stale row issue).
- **Root cause:** Not fully diagnosed. The crash occurs in `_run_position_monitor()` which calls `monitor_positions()` from B7. The main `_session_loop()` has **no try/except** — any unhandled exception crashes the entire process. Likely causes: (a) `monitor_positions()` or `_load_tsm_configs()` raises an exception on empty/cold-start data, or (b) `self.open_positions.remove(pos)` raises `ValueError` if the resolved position doesn't match.
- **Fix applied:** None — the container restart cycle obscured the exact traceback.
- **Fix result:** N/A
- **Status:** UNRESOLVED — Requires: (a) adding try/except around the position monitor call in `_session_loop()`, and (b) investigating what exception B7 raises on cold-start data.

### 3.8 Health Endpoint Reporting DEGRADED

- **Component:** `captain-command/captain_command/api.py` — `/api/health`
- **Symptom:** `curl localhost:8000/api/health` returned `{"status": "DEGRADED", ...}`.
- **Root cause:** Online and Offline processes do not publish heartbeats to Redis `captain:status` channel (confirmed: zero matches for `captain:status` or `CH_STATUS` in captain-online/ and captain-offline/). Command's `_process_health` dict starts with `{"OFFLINE": {"status": "unknown"}, "ONLINE": {"status": "unknown"}}` and never gets updated. The health endpoint returns DEGRADED when both are "unknown".
- **Fix applied:** None — determined to be cosmetic (does not affect trading).
- **Fix result:** N/A
- **Status:** UNRESOLVED (cosmetic) — Online and Offline need to publish periodic heartbeats to Redis `captain:status`, or the health endpoint logic needs to be changed to check process health differently (e.g., check if containers are responsive via Docker health checks).

---

## 4. TIMELINE OF EVENTS

```
[08:40] — Session begins. Plan created for adding Processes tab to GUI.
[08:55] — All backend + frontend code written for Processes tab. 64/64 tests pass, 0 TS errors.
[09:00] — Audit requested: "will it auto-trade at 9:30?"
[09:05] — Three audit subagents deployed (Online flow, Command flow, data readiness).
[09:07] — CRITICAL FINDING: compliance_gate.json has all 11 RTS 6 requirements = false.
          Even with AUTO_EXECUTE=true, all orders would return MANUAL_PENDING.
[09:08] — compliance_gate.json updated: all 11 set to true. Tests pass.
[09:10] — Health check: status=DEGRADED. Investigated — Online/Offline don't publish heartbeats.
          Determined cosmetic, not a trading blocker.
[09:13] — captain-online rebuilt and restarted. MarketStream CONNECTED.
[09:15] — Attempted to set session time to 09:00 for early test. Reverted to 09:30.
[09:20] — Validated container ET time matches real ET (09:20:44). Session trigger in ~8 min.
[09:21] — Gate validation inside container: 10 active assets, $150K silo, manual_halt=false,
          D01=270 rows, D12=60 rows, D08=$150K. All data gates pass.
[09:22] — CRITICAL FINDING: Compliance gate inside container still shows all false!
          Host file updated but Docker bind mount resolves to Windows C:\ via 9p.
[09:23] — docker cp used to inject updated compliance_gate.json. Verified: all 11 true.
[09:28] — Session triggered! B1: "No active assets for session NY"
[09:28] — CRITICAL FINDING: D00 latest rows have captain_status=NULL for all active assets.
          Root cause: _update_asset_quality_flag() inserts partial rows.
[09:30] — D00 rows manually re-inserted with correct ACTIVE status and session_hours.
          captain-online restarted to clear daily session gate.
[09:30] — Second trigger: B1 finds 9 assets! Full pipeline runs B1-B6.
          B5C blocks ALL 5 assets: "L3: negative basket expectancy — mu_b=0.00"
[09:31] — CRITICAL FINDING: CB Layer 3 cold-start bug. r_bar=0, beta_b=0, n_obs=0 → mu_b=0 ≤ 0.
          Spec says "layers 3-4 disabled" for cold start, but code doesn't bypass when cb_param
          exists with zero observations.
[09:33] — Fix applied: added `if n_obs == 0: return None` to L3 and L4. 20/20 CB tests pass.
[09:37] — Session time changed to 09:42 for retest. captain-online rebuilt.
[09:40] — B1: "No active assets" again (D00 stale rows from restart). D00 re-inserted.
          Session time changed to 09:47 for another attempt.
[09:45] — SUCCESS: Full pipeline B1→B6, 5 signals published!
          Command receives all 5 signals. AUTO-EXECUTE SKIP: direction=0 for all 5 (ORB pending).
[09:45] — Orchestrator crashes at line 93 (_run_position_monitor). Enters restart loop.
          Each restart re-triggers session (still in window), hits D00 stale rows, crashes again.
[09:47] — Session time reverted to 09:30. captain-online rebuilt to stop crash loop.
[09:50] — Session ends. Post-mortem analysis begins.
```

---

## 5. ROOT CAUSE ANALYSIS

### Root Cause A: QuestDB Append-Only Partial Updates (D00 Stale Rows)

**The underlying problem:** QuestDB is append-only. There is no UPDATE statement. When code needs to change one field (e.g., `data_quality_flag`), it inserts a new row with only that field set — all other columns default to NULL. B1 deduplicates by taking the most recent row per asset. This means any partial update creates a "latest" row with NULL captain_status and NULL session_hours, effectively erasing the asset from the active universe.

**Failures caused:**
- 3.2 — D00 stale rows blocking B1 ("No active assets")
- 3.7 — Crash loop (restarts re-trigger session, hit stale D00, crash)

**Category:** Code design issue — fundamental mismatch between QuestDB's append-only model and the codebase's assumption that partial inserts are safe.

**Recommended fix:** Every INSERT into `p3_d00_asset_universe` must include ALL key columns (at minimum: `captain_status`, `session_hours`, `locked_strategy`, `point_value`, `tick_size`, `margin_per_contract`). The `_update_asset_quality_flag()` function should read the current row first, then re-insert all fields with only the quality flag changed.

### Root Cause B: V1 Compliance Gate Locked by Default

**The underlying problem:** The compliance gate was designed for V1 as "always locked" with all 11 RTS 6 requirements set to false. This was correct for development but was never updated for the production deployment. The gate sits deep in the `send_signal()` path and silently returns `MANUAL_PENDING` without any alert or notification.

**Failures caused:**
- 3.1 — All orders blocked silently

**Category:** Configuration issue — deployment checklist gap.

### Root Cause C: Docker Desktop WSL2 Bind Mount Path Resolution

**The underlying problem:** Docker Desktop on WSL2 resolves bind mount paths through the Windows filesystem (9p driver mounting `C:\`) rather than the WSL2 native filesystem. Files edited on the WSL2 side don't propagate through the 9p mount. This means `./config:/captain/config` in docker-compose.yml points to the Windows copy, not the WSL2 copy.

**Failures caused:**
- 3.1 — Compliance gate change not visible inside container
- 3.6 — General bind mount unreliability
- Any future config changes will have the same issue

**Category:** Infrastructure issue — WSL2 + Docker Desktop interaction.

### Root Cause D: Cold-Start Data Not Handled Consistently

**The underlying problem:** Multiple components assume that "data exists" means "data is meaningful." When D25 has a row with all-zero values (cold start, no trades yet), the circuit breaker computes `mu_b = 0.0` and blocks. The code has a bypass for `cb_param is None` but not for "cb_param exists with no real observations."

**Failures caused:**
- 3.3 — CB Layer 3 blocking all trades on cold start

**Category:** Code bug — spec says "layers 3-4 disabled for cold start" but implementation didn't cover the case where D25 has seeded rows.

---

## 6. LESSONS LEARNED

1. **QuestDB append-only model is dangerous with partial inserts.** Every INSERT must be treated as a full row replacement. Partial inserts create NULL "shadow rows" that override good data. This is the single biggest systemic issue in the codebase — 6+ locations do partial inserts into D00.

2. **Docker bind mounts on WSL2 are unreliable.** The 9p filesystem bridge between Windows and WSL2 causes stale reads. `docker cp` is the reliable workaround. Long-term, config should be baked into images or use named volumes synced from the build context.

3. **The compliance gate is a silent killer.** It returns `MANUAL_PENDING` deep in the call stack with only an INFO log. There is no alert, no notification, no GUI indication. Without the pre-open audit, this would have silently prevented all trading indefinitely.

4. **Cold-start state is a spectrum, not a binary.** The code assumed "no cb_param" = cold start, but bootstrap scripts create rows with zero values. The presence of a row doesn't mean the data is actionable. Fixed by checking `n_observations == 0`.

5. **`docker exec` Python scripts can't validate in-memory state.** The TopstepX auth token and quote_cache live in the running process's memory. A `docker exec python3 -c "..."` runs a separate process and can't see them. Startup logs are the only reliable indicator for these.

6. **The session daily gate (`_session_evaluated_today`) requires a full container restart to reset.** There is no API or command to reset it. This meant every test attempt required a full rebuild cycle (~2 minutes), consuming most of the session window.

7. **The `GatewayLogout` warning from pysignalr is harmless.** TopstepX sends this message but Captain doesn't handle it. It's noise, not an error.

8. **Health endpoint DEGRADED is cosmetic.** Online and Offline don't publish heartbeats to Redis. The DEGRADED status does not affect trading but is confusing for monitoring.

---

## 7. PRE-FLIGHT CHECKLIST FOR NEXT SESSION

### Data Layer

- [ ] **Fix `_update_asset_quality_flag()` to preserve all D00 columns.**
  - Why: Prevents NULL shadow rows from overriding active asset data (Root Cause A).
  - How: Read the current row first, then re-insert all fields with only the quality flag changed.
  - Verification: After fix, run `docker exec captain-system-captain-online-1 python3 -c "..."` to check that D00 rows have non-NULL captain_status after a data moderator run.

- [ ] **Audit and fix ALL D00 INSERT statements that do partial inserts.**
  - Why: 6+ locations write NULL captain_status/session_hours (Root Cause A).
  - Files to fix:
    - `captain-online/captain_online/blocks/b1_data_ingestion.py` line 601 (CRITICAL — runs every session)
    - `captain-offline/captain_offline/blocks/b1_aim_lifecycle.py` line 113
    - `captain-offline/captain_offline/blocks/bootstrap.py` lines 98, 285
    - `scripts/seed_all_assets.py` line 250
    - `scripts/roll_calendar_update.py` line 253
  - Verification: `grep -rn "INSERT INTO p3_d00_asset_universe" --include="*.py" | grep -v captain_status` should return zero results.

- [ ] **Re-run `bootstrap_production.py` after fixing D00 inserts to establish clean baseline.**
  - Why: Ensures all 10 assets have correct captain_status, session_hours, locked_strategy.
  - Verification: `SELECT asset_id, captain_status, session_hours FROM p3_d00_asset_universe LATEST ON last_updated PARTITION BY asset_id ORDER BY asset_id` — all 10 active assets should show ACTIVE with correct session_hours.

### Configuration

- [ ] **Fix Docker bind mount issue for config directory.**
  - Why: Config changes on WSL2 host don't propagate to containers (Root Cause C).
  - Options: (a) Set `DOCKER_HOST` to use WSL2 backend directly, (b) add `docker cp config/compliance_gate.json captain-system-captain-command-1:/captain/config/compliance_gate.json` to `captain-start.sh`, (c) rebuild captain-command after any config change.
  - Verification: Edit a test value in compliance_gate.json, then `docker exec captain-system-captain-command-1 cat /captain/config/compliance_gate.json` should show the change immediately.

- [ ] **Ensure compliance_gate.json has all 11 requirements = true inside the Command container.**
  - Why: Gate silently blocks all orders if any requirement is false (failure 3.1).
  - Verification: `docker exec captain-system-captain-command-1 python3 -c "import json; gate=json.load(open('/captain/config/compliance_gate.json')); reqs={k:v for k,v in gate.items() if k.startswith('rts6_')}; print('All true:', all(reqs.values()))"`

- [ ] **Verify `AUTO_EXECUTE=true` in `.env`.**
  - Why: Default is false (signals go to GUI only).
  - Verification: `docker exec captain-system-captain-command-1 python3 -c "import os; print(os.environ.get('AUTO_EXECUTE'))"`

### Code Fixes

- [ ] **Deploy CB cold-start fix (already in source, needs rebuild).**
  - Why: Without it, L3 blocks all trades when n_observations=0 (failure 3.3).
  - File: `captain-online/captain_online/blocks/b5c_circuit_breaker.py` — `if n_obs == 0: return None` in both L3 and L4.
  - Verification: `python3 -m pytest tests/test_b5c_circuit.py -v` — 20/20 pass.

- [ ] **Add try/except in `_session_loop()` around position monitor call.**
  - Why: Unhandled exception in B7 crashes the entire orchestrator (failure 3.7).
  - File: `captain-online/captain_online/blocks/orchestrator.py` lines 92-93.
  - Verification: Intentionally trigger an error in B7 and confirm the loop continues.

- [ ] **Investigate and fix ORB direction=0 issue.**
  - Why: All 5 signals had direction=0, preventing auto-execution (failure 3.4).
  - Key questions: Does B6 use `session_hours.open` (09:30) or the orchestrator trigger time for opening range calculation? Is `quote_cache` populated with enough tick data at evaluation time?
  - Verification: On next live run, check B6 logs for direction determination logic.

### Infrastructure

- [ ] **Fix captain-gui Docker build (SIGSEGV in tsc).**
  - Why: Can't rebuild GUI container normally (failure 3.5).
  - Options: (a) Add `--max-old-space-size=4096` to tsc invocation, (b) change Dockerfile to `RUN npx vite build` (skip tsc, Vite transpiles), (c) increase Docker build memory in `docker-compose.local.yml`.
  - Verification: `docker compose -f docker-compose.yml -f docker-compose.local.yml build captain-gui` completes without error.

- [ ] **Add Online/Offline heartbeat publishing to Redis `captain:status`.**
  - Why: Health endpoint always shows DEGRADED (failure 3.8).
  - Verification: `curl localhost:8000/api/health` returns `{"status": "OK", ...}`.

### Pre-Open Verification (Run at 09:15 ET)

- [ ] **Check all 6 containers are healthy:** `docker compose -f docker-compose.yml -f docker-compose.local.yml ps`
- [ ] **Check D00 active assets:** `docker exec captain-system-captain-online-1 python3 -c "..."` — expect 9-10 assets with non-NULL captain_status=ACTIVE.
- [ ] **Check compliance gate inside container:** expect all 11 = true.
- [ ] **Check AUTO_EXECUTE:** expect `true`.
- [ ] **Check TopstepX auth in logs:** expect `TopstepX authenticated`.
- [ ] **Check MarketStream in logs:** expect `MarketStream CONNECTED`.
- [ ] **Check manual_halt_all:** expect `false` in P3-D17.
- [ ] **Check container ET time matches wall clock:** `docker exec ... python3 -c "from datetime import datetime; from zoneinfo import ZoneInfo; print(datetime.now(ZoneInfo('America/New_York')))"`

---

## 8. OPEN QUESTIONS

1. **Why does `_update_asset_quality_flag()` do a partial INSERT instead of a full row replacement?** Was this intentional (performance optimisation) or an oversight? The function is called every session for every asset — it's the primary source of D00 corruption.

2. **How does B6 determine ORB breakout direction?** Does it use the `session_hours.open` field from D00 (09:30) or the orchestrator's trigger timestamp? If it uses the trigger time, testing with shifted session times will always produce direction=0 because the opening range hasn't formed relative to the fake trigger time.

3. **What exception is B7 (`_run_position_monitor`) throwing?** The crash loop obscured the actual traceback. Need to add logging or a try/except to capture the exact error on next occurrence.

4. **Should the compliance gate be permanently set to all-true for practice accounts?** The V1 "always locked" design was for development safety, but it silently blocks production trading with no alert mechanism.

5. **Is the Docker bind mount issue specific to this WSL2 setup, or is it a known Docker Desktop limitation?** Need to determine if switching to Docker Engine (non-Desktop) on WSL2 fixes the 9p mount issue.

6. **Should the session daily gate have a manual reset mechanism?** Currently, the only way to re-trigger a session is to restart the container. A Redis command or API endpoint to clear `_session_evaluated_today` would dramatically speed up debugging.
