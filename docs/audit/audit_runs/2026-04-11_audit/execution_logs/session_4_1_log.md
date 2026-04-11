            # Execution Log — Session 4.1: Sensitivity Fix + RPT-12

            | Field | Value |
            |-------|-------|
            | **Phase** | 4 |
            | **Started** | 2026-04-11 11:41:15 ET |
            | **CRITICALs** | G-OFF-029, G-CMD-002 |
            | **Git HEAD (before)** | `2c73a9c` |
            | **Worktree** | `/home/nomaan/captain-system` |
            | **Status** | RUNNING |

            ---

            ## Passover Prompt

            <details>
            <summary>Click to expand (3082 chars)</summary>

            ```
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
            ```

            </details>

            ---

            ## Execution Output

            ```
Session 4.1 complete. Here's what was done:

### G-OFF-029 (CRITICAL) — Per-Parameter Perturbation
**b5_sensitivity.py**: Restructured the perturbation loop from uniform (all params at once, 7 points) to one-at-a-time (N_params x 7 points). Each parameter (sl_multiplier, tp_multiplier) is now perturbed independently while others hold at baseline. `_backtest_perturbed` takes a new `param_name` argument to perturb only that parameter. Grid results now include `"param"` field.

### G-OFF-030 (MEDIUM) — PBO on Perturbation Grid  
**b5_sensitivity.py**: PBO now computed on the returns from the best-performing grid configuration instead of the unperturbed `base_returns`. DSR `n_trials` updated to use `N_params x 7` (total grid size) instead of just 7.

### G-CMD-002 (CRITICAL) — RPT-12 Alpha Decomposition
**b6_reports.py**: Added RPT-12 to `REPORT_TYPES` dict and `generators` map. Implemented `_rpt12_alpha_decomposition` which decomposes trade P&L into four components:
- **Base strategy**: raw 1-contract signal quality
- **Regime effect**: edge deviation from EWMA baseline (via D05)
- **AIM effect**: position scaling from combined modifier (from D03)
- **Kelly effect**: multi-contract sizing contribution

Output includes per-trade rows with absolute P&L and percentage attribution, plus a TOTAL summary row.

All 95 unit tests pass. Tracking documents updated. Commit: `4a7e258`.

```

---

## Post-Execution State

| Field | Value |
|-------|-------|
| **Status** | **COMPLETED** |
| **Completed** | 2026-04-11 11:52:29 ET |
| **Duration** | 11m 14s |
| **Git HEAD (after)** | `4a7e258` |
| **Commit** | `4a7e258` |
