            # Execution Log — Session 1.1: Pseudotrader Orchestrator Integration

            | Field | Value |
            |-------|-------|
            | **Phase** | 1 |
            | **Started** | 2026-04-11 10:30:16 ET |
            | **CRITICALs** | G-OFF-015 |
            | **Git HEAD (before)** | `3a474ba` |
            | **Worktree** | `/home/nomaan/captain-system/.audit-worktrees/phase-1-pseudotrader` |
            | **Status** | RUNNING |

            ---

            ## Passover Prompt

            <details>
            <summary>Click to expand (3345 chars)</summary>

            ```
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
            ```

            </details>

            ---

            ## Execution Output

            ```
Session 1.1 is complete. Here's the summary:

## G-OFF-015 Resolved — Pseudotrader Wired Into Orchestrator

### What was broken
The pseudotrader (`b3_pseudotrader.py`) had full replay comparison logic but was **never called** by the orchestrator. DMA weight updates (D02) and Kelly/EWMA updates (D05/D12) were committed directly — the system self-modified trading parameters with zero validation.

### What was fixed (3 files changed, 231 insertions)

**`orchestrator.py`** — New pre-commit gate:
- `_pseudotrader_gate()` calls `run_signal_replay_comparison()` before any parameter write. Returns ADOPT/REJECT.
- Fail-safe: if pseudotrader crashes, update is **rejected** (never fail-open)
- Epsilon fast-path: trivial changes (max |delta| < 1e-4) skip the replay and commit directly
- Applied to both `_handle_trade_outcome` and `_handle_signal_outcome`

**`b1_dma_update.py`** — Added `commit=False` dry-run mode:
- Computes proposed D02 weights without writing to DB
- Returns `{current_weights, proposed_weights}` for the gate to evaluate

**`b8_kelly_update.py`** — Added `commit=False` dry-run mode:
- Computes proposed EWMA and Kelly fractions without writing to D05/D12
- Correctly uses proposed EWMA for the trigger cell when computing Kelly

### All 3 parameter-update paths gated
| Path | Gate |
|------|------|
| DMA → D02 | `_pseudotrader_gate("AIM_WEIGHT_CHANGE")` |
| Kelly → D05/D12 | `_pseudotrader_gate("KELLY_UPDATE")` |
| Injection → B4 | Already internal (`run_pseudotrader` called by `b4_injection.py`) |

### Verification
- 95 unit tests pass
- GAP_ANALYSIS.md: G-OFF-015 marked `[RESOLVED]`
- EXECUTION_ORCHESTRATOR.md: Session 1.1 marked COMPLETE, CRITICAL #3 RESOLVED

```

---

## Post-Execution State

| Field | Value |
|-------|-------|
| **Status** | **COMPLETED** |
| **Completed** | 2026-04-11 10:39:06 ET |
| **Duration** | 8m 50s |
| **Git HEAD (after)** | `28e6161` |
| **Commit** | `28e6161` |
