            # Execution Log — Session 0.1: Kelly L4 Formula Fix + GUI WebSocket Sanitization

            | Field | Value |
            |-------|-------|
            | **Phase** | 0 |
            | **Started** | 2026-04-11 10:24:38 ET |
            | **CRITICALs** | G-ONL-017, G-ONL-028, G-XCT-015 |
            | **Git HEAD (before)** | `8465886` |
            | **Worktree** | `/home/nomaan/captain-system` |
            | **Status** | RUNNING |

            ---

            ## Passover Prompt

            <details>
            <summary>Click to expand (3489 chars)</summary>

            ```
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
            ```

            </details>

            ---

            ## Execution Output

            ```
Session 0.1 complete. Commit `3a474ba`.

**What was done:**

1. **G-ONL-017 (Kelly L4)** — `b4_kelly_sizing.py:132-144`: Replaced the delegation to `b1_features.py`'s `compute_robust_kelly` (which computed `1/upper`, algebraically unrelated to spec) with the correct inline formula `f_robust = mu / (mu² + var) if mu > 0 else 0`. L1-L3 and L5-L7 untouched.

2. **G-ONL-028 / G-XCT-015 (GUI sanitization)** — `b1_core_routing.py:100-109`: Added `sanitise_for_gui()` that strips all 9 `PROHIBITED_EXTERNAL_FIELDS` (`aim_breakdown`, `combined_modifier`, `regime_probs`, `kelly_params`, `aim_weights`, `strategy_logic`, `ewma_states`, `decay_states`, `sensitivity_results`) before the WebSocket push. The Redis channel signal remains unchanged for internal process consumption.

3. **95/95 tests pass**, zero regressions.

4. **Audit docs updated** — G-ONL-017, G-ONL-028, G-XCT-015 marked `[RESOLVED]`; Phase 0 marked `COMPLETE` in the execution orchestrator.

```

---

## Post-Execution State

| Field | Value |
|-------|-------|
| **Status** | **COMPLETED** |
| **Completed** | 2026-04-11 10:30:14 ET |
| **Duration** | 5m 36s |
| **Git HEAD (after)** | `3a474ba` |
| **Commit** | `3a474ba` |
