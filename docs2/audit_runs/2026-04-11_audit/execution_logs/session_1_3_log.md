            # Execution Log — Session 1.3: Account-Aware Replay + Depth Fixes

            | Field | Value |
            |-------|-------|
            | **Phase** | 1 |
            | **Started** | 2026-04-11 11:27:21 ET |
            | **CRITICALs** | None |
            | **Git HEAD (before)** | `8560b90` |
            | **Worktree** | `/home/nomaan/captain-system` |
            | **Status** | RUNNING |

            ---

            ## Passover Prompt

            <details>
            <summary>Click to expand (3591 chars)</summary>

            ```
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
            ```

            </details>

            ---

            ## Execution Output

            ```
Session 1.3 is complete. Here's a summary of what was done:

## Session 1.3 Complete — Phase 1 Done

### Changes to `b3_pseudotrader.py` (+338 lines)

| Gap | Fix | Spec |
|-----|-----|------|
| **G-OFF-019** | Added `fetch_active_accounts()` (queries D08 for active TSM accounts) and `run_pseudotrader_all_accounts()` (runs replay per account, aggregates ADOPT/REJECT — overall ADOPT only if ALL accounts pass) | Doc 28 §5 |
| **G-OFF-020** | Added `if running_balance <= 0: break` with bankruptcy flag in both `run_account_aware_replay()` and `run_cb_pseudotrader()` — halts replay and logs warning | Doc 28 §4 |
| **G-OFF-021** | Rewrote `run_cb_pseudotrader()` with `account_config` parameter implementing the 11-step per-day loop: SOD reset, MDD pre-check, DLL check, trading hours, size constraint (scaling), then CB layers 1-4, post-trade balance update, consistency check, capital unlock | Doc 28 §4, Doc 32 PG-09B |
| **G-OFF-022** | Added `n_trials` parameter to `run_pseudotrader()`, passed through to `_compute_dsr()` | Doc 32 PG-09 §4 |
| **G-OFF-023** | CB pseudotrader now computes actual DSR from skew/kurtosis of CB daily P&L (was hardcoded 0.0) | Doc 32 PG-09B |

### Tests: 126 passing (7 new)
- `test_bankruptcy_halts_replay` — verifies balance depletion stops replay
- `test_no_account_config_unconstrained` — CB replay backward compatible
- `test_dll_blocks_in_cb_replay` — DLL enforcement in CB path
- `test_mdd_breach_halts_cb_replay` — MDD stops CB replay permanently
- `test_dsr_computed_not_zero` — DSR computed, not hardcoded
- `test_no_active_accounts_fallback` — D08 empty falls back gracefully
- `test_multiple_accounts_iteration` — each account gets its own replay

```

---

## Post-Execution State

| Field | Value |
|-------|-------|
| **Status** | **COMPLETED** |
| **Completed** | 2026-04-11 11:37:16 ET |
| **Duration** | 9m 55s |
| **Git HEAD (after)** | `2c73a9c` |
| **Commit** | `2c73a9c` |
