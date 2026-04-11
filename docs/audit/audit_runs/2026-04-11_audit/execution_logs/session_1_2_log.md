            # Execution Log — Session 1.2: Signal Replay Integration

            | Field | Value |
            |-------|-------|
            | **Phase** | 1 |
            | **Started** | 2026-04-11 11:16:05 ET |
            | **CRITICALs** | G-OFF-016 |
            | **Git HEAD (before)** | `3a474ba` |
            | **Worktree** | `/home/nomaan/captain-system` |
            | **Status** | RUNNING |

            ---

            ## Passover Prompt

            <details>
            <summary>Click to expand (2986 chars)</summary>

            ```
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
            ```

            </details>

            ---

            ## Execution Output

            ```
Session 1.2 is complete. Here's the summary:

**Commit `8560b90`** — 3 files changed, 180 insertions, 9 deletions

### What was done

**G-OFF-016 (CRITICAL) — RESOLVED**: Added `captain_online_replay()` wrapper that uses `shared/replay_engine`'s `run_replay()` and `run_whatif()` for full B1-B6 pipeline replay per spec Doc 32 PG-09. Modified `run_pseudotrader()` so the **primary path** fetches trading days from D03, replays baseline with current params, then replays proposed via `run_whatif()` with cached bars (zero API calls for the second pass). The pre-computed P&L path is retained as a labeled **FAST FALLBACK** — `b4_injection.py` continues to call it positionally without any changes needed.

**G-OFF-024 (MEDIUM) — RESOLVED**: Added `fetch_d03_trade_outcomes()` that queries `p3_d03_trade_outcome_log` in QuestDB. This provides the historical window of trading days for the replay path and serves as the actual trade outcome data source per spec.

### Verification
- Python AST parse: OK
- 95 unit tests: all pass (0.78s)
- Backward compatible: `b4_injection.py` positional call `run_pseudotrader(asset_id, type, baseline, proposed)` works unchanged via the fallback path

```

---

## Post-Execution State

| Field | Value |
|-------|-------|
| **Status** | **COMPLETED** |
| **Completed** | 2026-04-11 11:27:16 ET |
| **Duration** | 11m 10s |
| **Git HEAD (after)** | `8560b90` |
| **Commit** | `8560b90` |
